"""Bounded, read-only voucher recovery. Absence NEVER authorizes another import.

The same comparison runs in the connector and API. Tally-generated metadata is
ignored; every supplied accounting/inventory allocation is compared instead.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

try:
    import requests
except (
    ModuleNotFoundError
):  # API verifies evidence without connector HTTP dependencies.
    requests = None

MAX_BYTES = 2 * 1024 * 1024
MAX_PROOF_BYTES = 256 * 1024


class ReconciliationError(ValueError):
    pass


def safe_xml(data):
    if isinstance(data, str):
        data = data.encode()
    if (
        len(data) > MAX_BYTES
        or b"\x00" in data
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ReconciliationError(
            "Unsafe or oversized Tally response; posting remains on hold."
        )
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ReconciliationError(
            "Unreadable Tally response; posting remains on hold."
        ) from exc
    stack, count = [(root, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > 32 or count > 20000:
            raise ReconciliationError(
                "Tally response is too complex; manual review required."
            )
        stack.extend((child, depth + 1) for child in node)
    return root


def reference_from_plan(plan):
    reference = str(plan.get("posting_reference") or "")
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", reference):
        raise ReconciliationError(
            "Legacy posting has no durable reference. Preserve recovery files and contact support."
        )
    return reference


def company_identity(url, name):
    # Connector-only imports must not become API startup dependencies.
    try:
        from .tally_master_sync import read_collection, MasterSyncError
    except ImportError:
        from tally_master_sync import read_collection, MasterSyncError
    try:
        matches = [r for r in read_collection(url, "companies") if r["name"] == name]
    except MasterSyncError as exc:
        raise ReconciliationError(str(exc)) from exc
    if len(matches) != 1 or not matches[0]["guid"]:
        raise ReconciliationError(
            "The exact Tally company is not uniquely available. Posting remains on hold."
        )
    return {"name": name, "guid": matches[0]["guid"]}


def lookup_request(plan):
    reference = reference_from_plan(plan)
    root = ET.Element("ENVELOPE")
    header = ET.SubElement(root, "HEADER")
    for tag, value in (
        ("VERSION", "1"),
        ("TALLYREQUEST", "Export"),
        ("TYPE", "Collection"),
        ("ID", "SiftEntryRecovery"),
    ):
        ET.SubElement(header, tag).text = value
    desc = ET.SubElement(ET.SubElement(root, "BODY"), "DESC")
    variables = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(variables, "SVCURRENTCOMPANY").text = plan["company"]
    ET.SubElement(variables, "SVEXPORTFORMAT").text = "$$SysName:XML"
    message = ET.SubElement(ET.SubElement(desc, "TDL"), "TDLMESSAGE")
    collection = ET.SubElement(
        message, "COLLECTION", NAME="SiftEntryRecovery", ISINITIALIZE="Yes"
    )
    ET.SubElement(collection, "TYPE").text = "Voucher"
    ET.SubElement(collection, "NATIVEMETHOD").text = "*"
    ET.SubElement(collection, "FILTER").text = "SiftEntryRecoveryReference"
    # Only a validated, server-generated UUID enters the formula, never invoice text.
    ET.SubElement(
        message, "SYSTEM", TYPE="Formulae", NAME="SiftEntryRecoveryReference"
    ).text = f'$GUID = "{reference}" OR $RemoteGUID = "{reference}"'
    return ET.tostring(root, encoding="utf-8")


def _text(node, tag):
    values = node.findall(tag)
    if len(values) > 1:
        raise ReconciliationError("Duplicate voucher fields; manual review required.")
    return (values[0].text or "").strip() if values else ""


def _number(value):
    # Tally may add padding and decimal zeroes. Do not normalize currency or signs.
    match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*(.*?)\s*", value)
    if not match:
        raise ReconciliationError("Unsupported amount or quantity in Tally export.")
    try:
        number = Decimal(match[1])
    except InvalidOperation as exc:
        raise ReconciliationError("Invalid number in Tally export.") from exc
    return str(number.normalize()), match[2]


GROUPS = {
    "ledgers": ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"),
    "inventory": (
        "ALLINVENTORYENTRIES.LIST",
        "INVENTORYENTRIES.LIST",
        "INVENTORYALLOCATIONS.LIST",
    ),
    "accounting": ("ACCOUNTINGALLOCATIONS.LIST",),
    "batches": ("BATCHALLOCATIONS.LIST",),
    "bills": ("BILLALLOCATIONS.LIST",),
}
TEXT_FIELDS = (
    "LEDGERNAME",
    "STOCKITEMNAME",
    "GODOWNNAME",
    "DESTINATIONGODOWNNAME",
    "BATCHNAME",
    "NAME",
    "BILLTYPE",
    "ISDEEMEDPOSITIVE",
)
NUMBER_FIELDS = ("AMOUNT", "ACTUALQTY", "BILLEDQTY", "RATE")


def _allocation(node):
    result = {k: _text(node, k) for k in TEXT_FIELDS if _text(node, k)}
    result.update({k: _number(_text(node, k)) for k in NUMBER_FIELDS if _text(node, k)})
    for key, tags in GROUPS.items():
        children = [child for tag in tags for child in node.findall(tag)]
        if children:
            result[key] = sorted(
                (_allocation(c) for c in children),
                key=lambda x: json.dumps(x, sort_keys=True),
            )
    return result


def accounting_signature(voucher):
    # We do not claim equivalence for allocation families this product cannot
    # currently preview. Unknown financial allocations require a human check.
    for tag in (
        "CATEGORYALLOCATIONS.LIST",
        "COSTCENTREALLOCATIONS.LIST",
        "BANKALLOCATIONS.LIST",
    ):
        if voucher.find(".//" + tag) is not None:
            raise ReconciliationError(
                "Unsupported financial allocations require manual review."
            )
    return {
        "header": {
            k: _text(voucher, k)
            for k in ("DATE", "VOUCHERTYPENAME", "PARTYLEDGERNAME", "REFERENCE")
        },
        "entries": {
            key: sorted(
                (_allocation(c) for tag in tags for c in voucher.findall(tag)),
                key=lambda x: json.dumps(x, sort_keys=True),
            )
            for key, tags in GROUPS.items()
        },
    }


def verify_voucher(plan, voucher_xml):
    if len(voucher_xml.encode()) > MAX_PROOF_BYTES:
        raise ReconciliationError(
            "Voucher exceeds recovery evidence limit; manual review required."
        )
    actual = safe_xml(voucher_xml)
    expected = safe_xml(plan["xml"]).find(".//VOUCHER")
    reference = reference_from_plan(plan)
    if (
        actual.tag != "VOUCHER"
        or expected is None
        or expected.get("REMOTEID") != reference
    ):
        raise ReconciliationError("Voucher or approved reference is invalid.")
    identities = {
        actual.get("REMOTEID"),
        _text(actual, "GUID"),
        _text(actual, "REMOTEGUID"),
    }
    if reference not in identities:
        raise ReconciliationError(
            "Tally voucher reference does not match the approved posting."
        )
    marker = f"[SiftEntry:{reference}]"
    if marker not in _text(actual, "NARRATION"):
        raise ReconciliationError(
            "Tally voucher is missing the approved recovery marker."
        )
    if any(_text(actual, tag) != "No" for tag in ("ISCANCELLED", "ISOPTIONAL")):
        raise ReconciliationError(
            "Voucher is cancelled, optional, or its state cannot be verified."
        )
    if accounting_signature(actual) != accounting_signature(expected):
        raise ReconciliationError(
            "Tally entry differs from the approved accounting plan. Manual review required; do not repost."
        )
    external_id = _text(actual, "MASTERID") or _text(actual, "GUID")
    if not external_id:
        raise ReconciliationError("Tally did not expose a saved voucher identity.")
    return {
        "external_id": external_id,
        "voucher_number": _text(actual, "VOUCHERNUMBER"),
        "voucher_sha256": hashlib.sha256(voucher_xml.encode()).hexdigest(),
    }


def lookup_voucher(url, plan, company):
    if requests is None:
        raise ReconciliationError(
            "Connector HTTP support is missing. Reinstall; do not repost."
        )
    if (
        not company
        or company.get("name") != plan.get("company")
        or not company.get("guid")
    ):
        raise ReconciliationError(
            "No pinned company identity for this posting. Manual review required."
        )
    if company_identity(url, company["name"]) != company:
        raise ReconciliationError(
            "Tally company identity changed. Open the original company; do not repost."
        )
    try:
        with requests.post(
            url,
            data=lookup_request(plan),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise ReconciliationError(
                    "Tally lookup failed; posting remains on hold."
                )
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise ReconciliationError(
                        "Tally lookup is too large; posting remains on hold."
                    )
    except requests.RequestException as exc:
        raise ReconciliationError(
            "Tally lookup was interrupted; posting remains on hold."
        ) from exc
    root = safe_xml(bytes(content))
    collections = root.findall("./BODY/DATA/COLLECTION")
    if (
        root.tag != "ENVELOPE"
        or root.findtext("./HEADER/STATUS") != "1"
        or len(collections) != 1
        or root.find(".//LINEERROR") is not None
        or any(n.tag != "VOUCHER" for n in collections[0])
    ):
        raise ReconciliationError(
            "Tally did not return a complete voucher collection; posting remains on hold."
        )
    if company_identity(url, company["name"]) != company:
        raise ReconciliationError(
            "Company changed during lookup; posting remains on hold."
        )
    vouchers = list(collections[0])
    if len(root.findall(".//VOUCHER")) != len(vouchers):
        raise ReconciliationError(
            "Ambiguous voucher collection; posting remains on hold."
        )
    if len(vouchers) != 1:
        raise ReconciliationError(
            "No unique matching voucher was found. This is NOT permission to retry; contact support."
        )
    proof = ET.tostring(vouchers[0], encoding="unicode")
    return {**verify_voucher(plan, proof), "voucher_xml": proof, "company": company}
