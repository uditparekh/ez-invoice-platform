"""TallyPrime XML integration for EZ-Invoice."""

from __future__ import annotations

import html
import io
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import streamlit as st
from tally_connector_client import (
    connector_health,
    connector_test_tally,
    load_connector_settings,
    save_connector_settings,
    send_xml_batch_to_connector,
)

try:
    import requests
except ImportError:  # pragma: no cover - Streamlit shows a user-facing warning.
    requests = None


_TALLY_SETTINGS_FILE = Path(__file__).with_name("tally_settings.json")


def _config_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def _load_settings() -> Dict[str, Any]:
    defaults = {
        "url": _config_value("TALLY_URL", "http://localhost:9000"),
        "company": _config_value("TALLY_COMPANY", ""),
        "voucher_type": _config_value("TALLY_VOUCHER_TYPE", "Purchase"),
        "purchase_ledger": _config_value("TALLY_PURCHASE_LEDGER", "Purchase Accounts"),
        "tax_ledger": _config_value("TALLY_TAX_LEDGER", ""),
    }
    try:
        if _TALLY_SETTINGS_FILE.exists():
            with _TALLY_SETTINGS_FILE.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                defaults.update({k: v for k, v in saved.items() if v is not None})
    except Exception:
        pass
    return defaults


def _save_settings(settings: Dict[str, Any]) -> bool:
    try:
        with _TALLY_SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
        return True
    except Exception:
        return False


def _xml(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _amount(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_tally_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return datetime.now().strftime("%Y%m%d")
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8 and digits[:4].isdigit():
        return digits
    return datetime.now().strftime("%Y%m%d")


def _invoice_parts(payload: Dict[str, Any]) -> Dict[str, Any]:
    inv = payload.get("INVOICE", {})
    header = inv.get("INVOICE HEADER", {})
    seller = inv.get("SELLER", {})
    payment = inv.get("PAYMENT", {}).get("ELECTRONIC", {})
    rows = inv.get("LINE ITEMS", {}).get("ROWS", []) or []
    total = _amount(header.get("INVOICE AMOUNT") or payment.get("AMOUNT"))
    if not total:
        total = sum(_amount(row.get("AMOUNT")) for row in rows)
    return {
        "invoice": inv,
        "header": header,
        "vendor": seller.get("NAME") or "Unknown Supplier",
        "rows": rows,
        "total": total,
        "currency": payment.get("CURRENCY", "INR"),
    }


def _line_ledger(row: Dict[str, Any], default_ledger: str) -> str:
    """Choose the exact Tally ledger for a voucher line.

    Platform categories such as Materials, Freight, or Services are useful for
    analytics, but they are not guaranteed to exist as Tally ledgers. For live
    posting, use only an explicit Tally ledger mapping; otherwise fall back to
    the configured purchase/expense ledger.
    """
    tally_ledger = str(row.get("TALLY_LEDGER") or "").strip()
    if tally_ledger:
        return tally_ledger
    return default_ledger


def _line_category_note(row: Dict[str, Any]) -> str:
    for key in ("CLIENT_CATEGORY", "PLATFORM_CATEGORY", "SUBCATEGORY", "CATEGORY"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_ledger_entries(
    payload: Dict[str, Any],
    settings: Dict[str, Any],
    classifier=None,
) -> str:
    parts = _invoice_parts(payload)
    rows = parts["rows"]
    default_ledger = settings.get("purchase_ledger") or "Purchase Accounts"
    tax_ledger = settings.get("tax_ledger") or ""
    if classifier:
        try:
            rows = classifier.classify_invoice_rows(rows)
        except Exception:
            pass

    ledger_totals: Dict[str, float] = {}
    tax_total = 0.0
    for row in rows:
        amount = _amount(row.get("EXTENDED AMOUNT") or row.get("AMOUNT"))
        tax_total += _amount(row.get("TAX AMOUNT"))
        ledger = _line_ledger(row, default_ledger)
        ledger_totals[ledger] = ledger_totals.get(ledger, 0.0) + amount

    if not ledger_totals and parts["total"]:
        ledger_totals[default_ledger] = parts["total"]

    if tax_total:
        tax_target = tax_ledger or default_ledger
        ledger_totals[tax_target] = ledger_totals.get(tax_target, 0.0) + tax_total

    entries = []
    vendor_amount = parts["total"] or sum(ledger_totals.values())
    inv_no = parts["header"].get("INVOICE NO.", "")
    entries.append(
        f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_xml(parts["vendor"])}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
        <AMOUNT>{vendor_amount:.2f}</AMOUNT>
        <BILLALLOCATIONS.LIST>
          <NAME>{_xml(inv_no or "EZ-Invoice")}</NAME>
          <BILLTYPE>New Ref</BILLTYPE>
          <AMOUNT>{vendor_amount:.2f}</AMOUNT>
        </BILLALLOCATIONS.LIST>
      </ALLLEDGERENTRIES.LIST>"""
    )

    for ledger, amount in ledger_totals.items():
        entries.append(
            f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_xml(ledger)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <ISPARTYLEDGER>No</ISPARTYLEDGER>
        <AMOUNT>-{amount:.2f}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>"""
        )
    return "".join(entries)


def build_tally_xml(payload: Dict[str, Any], settings: Optional[Dict[str, Any]] = None, classifier=None) -> str:
    """Build an accounting purchase voucher XML import for TallyPrime."""

    settings = settings or current_settings()
    parts = _invoice_parts(payload)
    header = parts["header"]
    invoice_no = str(header.get("INVOICE NO.", "") or "EZ-Invoice")
    invoice_date = _to_tally_date(header.get("INVOICE DATE", ""))
    voucher_type = settings.get("voucher_type") or "Purchase"
    company = settings.get("company") or ""
    static_company = f"<SVCURRENTCOMPANY>{_xml(company)}</SVCURRENTCOMPANY>" if company else ""
    narration = "Imported by EZ-Invoice"
    po_no = header.get("PO NO./CONTRACT NO.", "")
    if po_no and po_no != "N/A":
        narration += " | PO: " + str(po_no)

    ledger_entries = _build_ledger_entries(payload, settings, classifier=classifier)
    return f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        {static_company}
      </STATICVARIABLES>
    </DESC>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="{_xml(voucher_type)}" ACTION="Create" OBJVIEW="Accounting Voucher View">
          <DATE>{invoice_date}</DATE>
          <VOUCHERTYPENAME>{_xml(voucher_type)}</VOUCHERTYPENAME>
          <VOUCHERNUMBER>{_xml(invoice_no)}</VOUCHERNUMBER>
          <REFERENCE>{_xml(invoice_no)}</REFERENCE>
          <REFERENCEDATE>{invoice_date}</REFERENCEDATE>
          <PARTYLEDGERNAME>{_xml(parts["vendor"])}</PARTYLEDGERNAME>
          <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>
          <ISINVOICE>No</ISINVOICE>
          <NARRATION>{_xml(narration)}</NARRATION>{ledger_entries}
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _parse_tally_response(text: str) -> Dict[str, Any]:
    result = {
        "created": 0,
        "altered": 0,
        "errors": 0,
        "line_error": "",
        "voucher_number": "",
        "raw": text,
    }
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        result["line_error"] = text[:500]
        result["errors"] = 1
        return result
    for tag, key in [
        ("CREATED", "created"),
        ("ALTERED", "altered"),
        ("ERRORS", "errors"),
        ("VCHNUMBER", "voucher_number"),
        ("LINEERROR", "line_error"),
    ]:
        node = root.find(".//" + tag)
        if node is not None and node.text is not None:
            if key in ("created", "altered", "errors"):
                try:
                    result[key] = int(float(node.text.strip()))
                except ValueError:
                    result[key] = 0
            else:
                result[key] = node.text.strip()
    return result


def _connector_failure_details(result: Dict[str, Any]) -> str:
    """Return the actionable per-voucher Tally errors from a connector response."""
    details: List[str] = []
    for item in result.get("results", []) or []:
        if item.get("success"):
            continue
        invoice_id = str(item.get("invoice_id") or "invoice")
        parsed = item.get("response") or {}
        message = str(item.get("message") or "").strip()
        line_error = str(parsed.get("line_error") or "").strip()
        if line_error and line_error not in message:
            message = (message + " | " if message else "") + line_error
        if not message:
            message = str(result.get("message") or "Tally rejected this voucher")
        details.append(invoice_id + ": " + message)
    if not details:
        return str(result.get("message") or "Unknown connector error")
    if len(details) > 4:
        details = details[:4] + ["+" + str(len(details) - 4) + " more failed voucher(s)"]
    return "; ".join(details)


def current_settings() -> Dict[str, Any]:
    if "tally_settings" not in st.session_state:
        st.session_state["tally_settings"] = _load_settings()
    return dict(st.session_state["tally_settings"])


def current_connector_settings() -> Dict[str, Any]:
    if "tally_connector_settings" not in st.session_state:
        st.session_state["tally_connector_settings"] = load_connector_settings()
    return dict(st.session_state["tally_connector_settings"])


def tally_is_connected() -> bool:
    settings = current_settings()
    connector_settings = current_connector_settings()
    return bool(connector_settings.get("enabled") or (settings.get("url") and settings.get("company")))


def send_to_tally(payload: Dict[str, Any], classifier=None, dry_run: bool = False) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests not installed", "response": None}
    settings = current_settings()
    connector_settings = current_connector_settings()
    xml = build_tally_xml(payload, settings=settings, classifier=classifier)
    invoice_no = _invoice_parts(payload)["header"].get("INVOICE NO.", "invoice")
    if connector_settings.get("enabled"):
        result = send_xml_batch_to_connector(
            [{"invoice_id": str(invoice_no or "invoice"), "xml": xml}],
            settings=connector_settings,
            dry_run=dry_run,
        )
        if result.get("success"):
            action = "dry-run accepted" if dry_run else "posted"
            return {"success": True, "message": "Connector " + action + " Tally voucher: " + str(invoice_no), "response": result}
        detail = _connector_failure_details(result)
        return {
            "success": False,
            "message": "Connector import failed: " + detail,
            "response": result,
        }

    if dry_run:
        return {"success": True, "message": "Dry run generated valid Tally XML: " + str(invoice_no), "response": {"dry_run": True}}

    url = (settings.get("url") or "").strip()
    if not url:
        return {"success": False, "message": "Set the Tally URL first.", "response": None}
    try:
        response = requests.post(url, data=xml.encode("utf-8"), headers={"Content-Type": "application/xml"}, timeout=20)
    except Exception as exc:
        return {"success": False, "message": "Tally connection failed: " + str(exc), "response": None}

    parsed = _parse_tally_response(response.text)
    if response.status_code == 200 and parsed["errors"] == 0 and (parsed["created"] or parsed["altered"]):
        action = "created" if parsed["created"] else "altered"
        voucher = parsed.get("voucher_number") or _invoice_parts(payload)["header"].get("INVOICE NO.", "")
        return {"success": True, "message": "Tally voucher " + action + ": " + str(voucher), "response": parsed}
    detail = parsed.get("line_error") or response.text[:300]
    return {
        "success": False,
        "message": "Tally import failed (" + str(response.status_code) + "): " + str(detail),
        "response": parsed,
    }


def send_tally_batch(
    payloads: Dict[str, Dict[str, Any]],
    classifier=None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    settings = current_settings()
    connector_settings = current_connector_settings()
    results: Dict[str, Any] = {}
    if connector_settings.get("enabled"):
        vouchers = []
        name_by_invoice_id: Dict[str, str] = {}
        for fname, data in payloads.items():
            payload = data.get("payload", {})
            parts = _invoice_parts(payload)
            invoice_id = str(parts["header"].get("INVOICE NO.", "") or fname)
            xml = build_tally_xml(payload, settings=settings, classifier=classifier)
            vouchers.append({"invoice_id": invoice_id, "xml": xml})
            name_by_invoice_id[invoice_id] = fname
        batch_result = send_xml_batch_to_connector(vouchers, settings=connector_settings, dry_run=dry_run)
        for item in batch_result.get("results", []) or []:
            fname = name_by_invoice_id.get(str(item.get("invoice_id", "")), str(item.get("invoice_id", "")))
            results[fname] = {
                "success": bool(item.get("success")),
                "message": item.get("message", batch_result.get("message", "")),
                "response": item,
            }
        for fname in payloads:
            results.setdefault(
                fname,
                {
                    "success": bool(batch_result.get("success")),
                    "message": batch_result.get("message", "Connector batch completed."),
                    "response": batch_result,
                },
            )
        batch_message = str(batch_result.get("message", ""))
        if not batch_result.get("success"):
            batch_message = "Connector import failed: " + _connector_failure_details(batch_result)
        return {"success": bool(batch_result.get("success")), "message": batch_message, "results": results, "response": batch_result}

    for fname, data in payloads.items():
        results[fname] = send_to_tally(data.get("payload", {}), classifier=classifier, dry_run=dry_run)
    return {"success": all(r.get("success") for r in results.values()), "message": "Batch completed", "results": results}


def make_tally_zip(payloads: Dict[str, Dict[str, Any]], classifier=None) -> io.BytesIO:
    buf = io.BytesIO()
    settings = current_settings()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in payloads.items():
            base = fname.rsplit(".", 1)[0]
            xml = build_tally_xml(data["payload"], settings=settings, classifier=classifier)
            zf.writestr(base + "_tally.xml", xml)
    buf.seek(0)
    return buf


def _test_connection(url: str) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests not installed"}
    try:
        response = requests.get(url, timeout=6)
        text = response.text.strip()
        if response.status_code == 200 and text:
            return {"success": True, "message": "Tally responded on " + url + ": " + text[:120]}
        if response.status_code == 200:
            return {"success": True, "message": "Tally responded on " + url}
    except Exception:
        return {"success": False, "message": "Tally port check failed. Open TallyPrime, load the company, and confirm port 9000 is enabled."}
    return {"success": False, "message": "HTTP " + str(response.status_code) + ": " + response.text[:160]}


def tally_sidebar(show_heading: bool = True) -> None:
    if show_heading:
        st.markdown("### TallyPrime Setup")
    settings = current_settings()
    connector_settings = current_connector_settings()
    with st.expander("2. Local Connector", expanded=True):
        st.markdown(
            '<div class="connector-help">Run the connector in a second Command Prompt on the same Windows computer as TallyPrime. Keep TallyPrime open with the company loaded.</div>',
            unsafe_allow_html=True,
        )
        use_connector = st.checkbox(
            "Use local connector on this computer",
            value=bool(connector_settings.get("enabled")),
            key="tally_connector_enabled",
        )
        connector_url = st.text_input(
            "Connector URL",
            value=connector_settings.get("url", "http://127.0.0.1:8765"),
            key="tally_connector_url",
        )
        workspace_id = st.text_input(
            "Workspace ID used by the connector",
            value=connector_settings.get("workspace_id", "client-test"),
            key="tally_connector_workspace",
        )
        connector_token = st.text_input(
            "Connector token",
            value=connector_settings.get("token", ""),
            type="password",
            key="tally_connector_token",
        )
        new_connector_settings = {
            "enabled": bool(use_connector),
            "url": connector_url.strip(),
            "workspace_id": workspace_id.strip() or "client-test",
            "token": connector_token.strip(),
        }
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Save Connector", key="tally_connector_save", use_container_width=True):
                st.session_state["tally_connector_settings"] = new_connector_settings
                if save_connector_settings(new_connector_settings):
                    st.success("Connector settings saved.")
                else:
                    st.warning("Settings saved for this session, but local persistence failed.")
        with c2:
            if st.button("Test Connector", key="tally_connector_health", use_container_width=True):
                st.session_state["tally_connector_settings"] = new_connector_settings
                result = connector_health(new_connector_settings)
                if result.get("success"):
                    st.success("Connector online: " + result.get("workspace_id", "workspace"))
                else:
                    st.warning(result.get("message", "Connector is not reachable. Start tally_connector_agent.py and keep that window open."))
        with c3:
            if st.button("Test Tally via Connector", key="tally_connector_tally", use_container_width=True):
                st.session_state["tally_connector_settings"] = new_connector_settings
                result = connector_test_tally(new_connector_settings)
                if result.get("success"):
                    st.success(result.get("message", "Tally responded."))
                else:
                    st.warning(result.get("message", "Tally did not respond. Confirm TallyPrime is open, company is loaded, and port 9000 is enabled."))
        st.caption("Connector default: http://127.0.0.1:8765. Tally default: http://localhost:9000.")

    with st.expander("3. Tally Voucher Settings", expanded=True):
        st.markdown(
            '<div class="connector-help">These values are written into the voucher XML sent to Tally. The company name should match the company currently open in TallyPrime.</div>',
            unsafe_allow_html=True,
        )
        url = st.text_input("Tally URL", value=settings.get("url", "http://localhost:9000"), key="tally_url")
        company = st.text_input(
            "Tally company name",
            value=settings.get("company", ""),
            placeholder="Example: NEEL ENTERPRISE",
            key="tally_company",
        )
        voucher_type = st.text_input("Voucher type", value=settings.get("voucher_type", "Purchase"), key="tally_voucher_type")
        purchase_ledger = st.text_input(
            "Purchase/expense ledger",
            value=settings.get("purchase_ledger", "Purchase Accounts"),
            key="tally_purchase_ledger",
        )
        tax_ledger = st.text_input("Tax ledger", value=settings.get("tax_ledger", ""), key="tally_tax_ledger")

        new_settings = {
            "url": url.strip(),
            "company": company.strip(),
            "voucher_type": voucher_type.strip() or "Purchase",
            "purchase_ledger": purchase_ledger.strip() or "Purchase Accounts",
            "tax_ledger": tax_ledger.strip(),
        }
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save Tally Settings", key="tally_save_settings", use_container_width=True):
                st.session_state["tally_settings"] = new_settings
                if _save_settings(new_settings):
                    st.success("Tally settings saved.")
                else:
                    st.warning("Settings saved for this session, but local persistence failed.")
        with c2:
            if st.button("Test Tally Port", key="tally_test_connection", use_container_width=True):
                st.session_state["tally_settings"] = new_settings
                result = _test_connection(new_settings["url"])
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.warning(result["message"])

    st.caption("Uses TallyPrime XML over HTTP. Keep TallyPrime open with HTTP Server enabled on port 9000.")
