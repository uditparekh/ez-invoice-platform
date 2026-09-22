"""Bounded, read-only Tally exports. No import, claim, or posting code lives here."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import requests

MAX_XML_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
COLLECTIONS = {
    "companies": ("Company", "COMPANY", ("Name", "GUID")),
    "ledgers": ("Ledger", "LEDGER", ("Name", "GUID", "Parent")),
    "stock_items": ("StockItem", "STOCKITEM", ("Name", "GUID", "BaseUnits")),
    "units": ("Unit", "UNIT", ("Name", "GUID")),
    "godowns": ("Godown", "GODOWN", ("Name", "GUID", "Parent")),
    "voucher_types": ("VoucherType", "VOUCHERTYPE", ("Name", "GUID", "Parent")),
}


class MasterSyncError(RuntimeError):
    """Safe, actionable message; never includes raw XML or credentials."""


def export_request(kind: str, company: str = "") -> bytes:
    object_type, _, methods = COLLECTIONS[kind]
    if kind != "companies" and not company:
        raise MasterSyncError("Choose a company before reading masters.")
    root = ET.Element("ENVELOPE")
    header = ET.SubElement(root, "HEADER")
    for key, value in (
        ("VERSION", "1"),
        ("TALLYREQUEST", "Export"),
        ("TYPE", "Collection"),
        ("ID", "SiftEntryMasterExport"),
    ):
        ET.SubElement(header, key).text = value
    desc = ET.SubElement(ET.SubElement(root, "BODY"), "DESC")
    variables = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(variables, "SVEXPORTFORMAT").text = "$$SysName:XML"
    if company:
        ET.SubElement(variables, "SVCURRENTCOMPANY").text = company
    message = ET.SubElement(ET.SubElement(desc, "TDL"), "TDLMESSAGE")
    collection = ET.SubElement(
        message, "COLLECTION", NAME="SiftEntryMasterExport", ISINITIALIZE="Yes"
    )
    ET.SubElement(collection, "TYPE").text = object_type
    for method in methods:
        ET.SubElement(collection, "NATIVEMETHOD").text = method
    return ET.tostring(root, encoding="utf-8")


def parse_export(content: bytes, kind: str) -> list[dict]:
    if (
        len(content) > MAX_XML_BYTES
        or b"<!DOCTYPE" in content.upper()
        or b"<!ENTITY" in content.upper()
    ):
        raise MasterSyncError(
            "Tally export is oversized or contains unsupported XML. No snapshot was saved."
        )
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise MasterSyncError(
            "Tally returned invalid XML. No snapshot was saved."
        ) from exc
    collections = root.findall("./BODY/DATA/COLLECTION")
    if (
        root.tag != "ENVELOPE"
        or root.findtext("./HEADER/STATUS") != "1"
        or len(collections) != 1
        or root.findall(".//LINEERROR")
    ):
        raise MasterSyncError(
            "Tally did not confirm a complete master export. Check the open company and permissions."
        )
    _, tag, _ = COLLECTIONS[kind]
    rows, names = [], set()
    for node in collections[0]:
        if node.tag != tag:
            raise MasterSyncError(
                "Tally returned an unexpected master type. No snapshot was saved."
            )
        name = (
            node.get("NAME")
            or node.findtext("NAME")
            or node.findtext("./LANGUAGENAME.LIST/NAME.LIST/NAME")
            or ""
        )
        row = {
            "name": name,
            "guid": node.findtext("GUID") or "",
            "parent": node.findtext("PARENT") or "",
            "base_units": node.findtext("BASEUNITS") or "",
        }
        if (
            not name.strip()
            or name in names
            or any(
                len(value) > 512 or any(ord(c) < 32 for c in value)
                for value in row.values()
            )
        ):
            raise MasterSyncError(
                "Tally returned duplicate or unsupported master names. No snapshot was saved."
            )
        names.add(name)
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise MasterSyncError(
                "This company exceeds the master sync limit. Contact support; no partial snapshot was saved."
            )
    return sorted(rows, key=lambda row: row["name"].casefold())


def read_collection(tally_url: str, kind: str, company: str = "") -> list[dict]:
    try:
        with requests.post(
            tally_url,
            data=export_request(kind, company),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise MasterSyncError(
                    "Tally rejected the export. Check its HTTP port and company permissions."
                )
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_XML_BYTES:
                    raise MasterSyncError(
                        "Tally export exceeds the size limit. No partial snapshot was saved."
                    )
        return parse_export(bytes(content), kind)
    except requests.RequestException as exc:
        raise MasterSyncError(
            "Cannot read Tally masters. Keep Tally open and check its HTTP port, then try again."
        ) from exc


def read_snapshot(tally_url: str, company: str) -> dict:
    def identity():
        matches = [
            row
            for row in read_collection(tally_url, "companies")
            if row["name"] == company
        ]
        if len(matches) != 1 or not matches[0]["guid"].strip():
            raise MasterSyncError(
                "The configured company must be open and expose a unique GUID. Check its exact name; no snapshot was saved."
            )
        return {"name": matches[0]["name"], "guid": matches[0]["guid"]}

    before = identity()
    masters = {
        kind: read_collection(tally_url, kind, company)
        for kind in COLLECTIONS
        if kind != "companies"
    }
    if identity() != before:
        raise MasterSyncError(
            "Tally company identity changed during sync. No snapshot was saved; try again."
        )
    snapshot = {"company": before, "masters": masters}
    if (
        sum(len(rows) for rows in masters.values()) > MAX_ROWS
        or len(json.dumps(snapshot, ensure_ascii=True).encode()) > MAX_SNAPSHOT_BYTES
    ):
        raise MasterSyncError(
            "This company exceeds the snapshot limit. Contact support; no partial snapshot was saved."
        )
    return snapshot
