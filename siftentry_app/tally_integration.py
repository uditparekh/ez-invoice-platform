"""TallyPrime XML integration for SiftEntry."""

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

try:
    import streamlit as st
except ModuleNotFoundError:  # headless API/worker containers install requirements-api.txt only
    st = None


class _HeadlessStreamlit:
    """Minimal stand-in so shared helpers work without Streamlit installed.

    The FastAPI backend imports build_tally_xml/send_to_tally from this
    module; those paths only touch st.secrets and st.session_state, which
    this shim provides as plain dicts. UI functions are never called headless.
    """

    def __init__(self):
        self.session_state = {}
        self.query_params = {}
        self.secrets = {}

    def __getattr__(self, name):
        def _noop(*_args, **_kwargs):
            return None

        return _noop


if st is None:
    st = _HeadlessStreamlit()
try:
    from .tally_connector_client import (
        connector_health,
        connector_test_tally,
        load_connector_settings,
        save_connector_settings,
        send_xml_batch_to_connector,
    )
except ImportError:  # pragma: no cover - supports running the file directly.
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


TALLY_SETUP_PROFILES: Dict[str, Dict[str, str]] = {
    "generic": {
        "label": "Generic / manual setup",
        "company": "",
        "voucher_type": "Purchase",
        "posting_mode": "Accounting Voucher",
        "purchase_ledger": "Purchase Accounts",
        "tax_ledger": "",
        "stock_item_name": "",
        "stock_item_hsn": "",
        "stock_item_uom": "",
        "godown_name": "",
        "tcs_ledger": "",
        "round_off_ledger": "",
    },
    "india_gst_item_invoice": {
        "label": "India GST item invoice template",
        "company": "",
        "voucher_type": "Purchase",
        "posting_mode": "Item Invoice",
        "purchase_ledger": "",
        "tax_ledger": "",
        "stock_item_name": "",
        "stock_item_hsn": "",
        "stock_item_uom": "",
        "godown_name": "",
        "tcs_ledger": "",
        "round_off_ledger": "",
    },
}


def _profile_defaults(profile_id: str) -> Dict[str, str]:
    profile = TALLY_SETUP_PROFILES.get(profile_id) or TALLY_SETUP_PROFILES["generic"]
    return {key: value for key, value in profile.items() if key != "label"}


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
        "setup_profile": _config_value("TALLY_SETUP_PROFILE", "generic"),
        "url": _config_value("TALLY_URL", "http://localhost:9000"),
        "company": _config_value("TALLY_COMPANY", ""),
        "voucher_type": _config_value("TALLY_VOUCHER_TYPE", "Purchase"),
        "posting_mode": _config_value("TALLY_POSTING_MODE", "Accounting Voucher"),
        "purchase_ledger": _config_value("TALLY_PURCHASE_LEDGER", "Purchase Accounts"),
        "tax_ledger": _config_value("TALLY_TAX_LEDGER", ""),
        "stock_item_name": _config_value("TALLY_STOCK_ITEM_NAME", ""),
        "stock_item_hsn": _config_value("TALLY_STOCK_ITEM_HSN", ""),
        "stock_item_uom": _config_value("TALLY_STOCK_ITEM_UOM", ""),
        "godown_name": _config_value("TALLY_GODOWN_NAME", ""),
        "tcs_ledger": _config_value("TALLY_TCS_LEDGER", ""),
        "round_off_ledger": _config_value("TALLY_ROUND_OFF_LEDGER", ""),
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


def _fmt_amount(value: Any) -> str:
    return f"{_amount(value):.2f}"


def _fmt_qty(value: Any) -> str:
    number = _amount(value)
    if abs(number - round(number)) < 0.0001:
        return str(int(round(number)))
    return f"{number:.4f}".rstrip("0").rstrip(".")


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
        "currency": payment.get("CURRENCY", "USD"),
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


ITEM_INVOICE_ALIASES = {
    "item invoice",
    "item_invoice",
    "inventory",
    "inventory invoice",
}

VOUCHER_WITH_INVENTORY_ALIASES = {
    "voucher with stock allocation",
    "voucher with inventory",
    "voucher_with_inventory",
    "voucher_with_stock_allocation",
    "accounting voucher with inventory",
}


def _posting_mode(settings: Dict[str, Any]) -> str:
    return str(settings.get("posting_mode") or "Accounting Voucher").strip().lower()


def _is_item_invoice_mode(settings: Dict[str, Any]) -> bool:
    return _posting_mode(settings) in ITEM_INVOICE_ALIASES


def _is_voucher_with_inventory_mode(settings: Dict[str, Any]) -> bool:
    return _posting_mode(settings) in VOUCHER_WITH_INVENTORY_ALIASES


def _uses_stock_items(settings: Dict[str, Any]) -> bool:
    """Both inventory-backed modes need stock item, UOM, and quantity data."""

    return _is_item_invoice_mode(settings) or _is_voucher_with_inventory_mode(settings)


def _line_stock_item(row: Dict[str, Any], settings: Dict[str, Any]) -> str:
    explicit = str(
        row.get("TALLY_STOCK_ITEM")
        or row.get("TARGET_ITEM_NAME")
        or row.get("TARGET ITEM")
        or row.get("STOCK ITEM")
        or ""
    ).strip()
    if explicit:
        return explicit

    configured_item = str(settings.get("stock_item_name") or "").strip()
    configured_hsn = re.sub(r"\D", "", str(settings.get("stock_item_hsn") or ""))
    row_hsn = re.sub(r"\D", "", str(row.get("HSN/SAC") or row.get("HSN") or row.get("SAC") or ""))
    description = str(row.get("DESCRIPTION") or row.get("ITEM") or "").strip()

    if configured_item and configured_hsn and row_hsn == configured_hsn:
        return configured_item
    if configured_item and not configured_hsn:
        return configured_item
    return description or configured_item or "Invoice item"


def _line_tally_uom(row: Dict[str, Any], settings: Dict[str, Any]) -> str:
    uom = str(row.get("TARGET_UOM") or row.get("TALLY_UOM") or row.get("UOM") or row.get("UNIT") or "EA").strip().upper() or "EA"
    tally_uom = str(settings.get("stock_item_uom") or "").strip().upper()
    if tally_uom and uom in {"KG", "KGS"}:
        return tally_uom
    return uom


def _line_net_amount(row: Dict[str, Any]) -> float:
    amount = _amount(row.get("EXTENDED AMOUNT") or row.get("NET AMOUNT") or row.get("TAXABLE VALUE"))
    if amount:
        return amount
    gross = _amount(row.get("AMOUNT") or row.get("TOTAL"))
    tax = _amount(row.get("TAX AMOUNT"))
    return round(max(0.0, gross - tax), 2) if gross else 0.0


def _tax_total(parts: Dict[str, Any], rows: List[Dict[str, Any]]) -> float:
    invoice = parts["invoice"]
    tax_summary = invoice.get("INVOICE TAX SUMMARY", {}) or {}
    total = _amount(tax_summary.get("TOTAL TAX") or tax_summary.get("TAX AMOUNT"))
    if total:
        return total
    return round(sum(_amount(row.get("TAX AMOUNT")) for row in rows), 2)


def _settings_tax_ledger(settings: Dict[str, Any], *keys: str) -> str:
    tax_settings = settings.get("tax_settings") or {}
    if not isinstance(tax_settings, dict):
        tax_settings = {}
    for key in keys:
        for candidate in (
            key,
            key.lower(),
            key.upper(),
            key.replace(" ", "_").lower(),
            key.replace("_", " ").upper(),
        ):
            value = str(tax_settings.get(candidate) or "").strip()
            if value:
                return value
    return ""


def _row_summary_amount(rows: List[Dict[str, Any]], labels: List[str]) -> float:
    wanted = {label.upper() for label in labels}
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            key_norm = str(key or "").upper().replace("_", " ")
            if key_norm in wanted or any(label in key_norm for label in wanted):
                total += _amount(value)
    return round(total, 2)


def _summary_amount(parts: Dict[str, Any], labels: List[str]) -> float:
    invoice = parts["invoice"]
    candidates = [
        invoice.get("INVOICE TAX SUMMARY", {}) or {},
        invoice.get("PARSER_DIAGNOSTICS", {}) or {},
        invoice.get("ADJUSTMENTS", {}) or {},
        invoice.get("TOTALS", {}) or {},
    ]
    wanted = {label.upper() for label in labels}
    for source in candidates:
        for key, value in source.items():
            key_norm = str(key or "").upper().replace("_", " ")
            if key_norm in wanted or any(label in key_norm for label in wanted):
                amount = _amount(value)
                if amount:
                    return amount
    return 0.0


def _tax_ledger_components(
    parts: Dict[str, Any],
    rows: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    tax_total = _tax_total(parts, rows)
    if not tax_total:
        return []

    tax_mode = str(settings.get("tax_mode") or "").strip().lower()
    invoice_text = json.dumps(parts.get("invoice") or {}, default=str).upper()
    igst_total = _summary_amount(parts, ["IGST", "INPUT IGST", "IGST AMOUNT"])
    cgst_total = _summary_amount(parts, ["CGST", "INPUT CGST", "CGST AMOUNT"])
    sgst_total = _summary_amount(parts, ["SGST", "INPUT SGST", "SGST AMOUNT"])

    igst_total = igst_total or _row_summary_amount(rows, ["IGST", "IGST AMOUNT"])
    cgst_total = cgst_total or _row_summary_amount(rows, ["CGST", "CGST AMOUNT"])
    sgst_total = sgst_total or _row_summary_amount(rows, ["SGST", "SGST AMOUNT"])

    igst_ledger = (
        _settings_tax_ledger(settings, "igst_ledger", "input_igst_ledger", "input igst")
        or str(settings.get("tax_ledger") or "").strip()
    )
    cgst_ledger = _settings_tax_ledger(
        settings,
        "cgst_ledger",
        "input_cgst_ledger",
        "input cgst",
    )
    sgst_ledger = _settings_tax_ledger(
        settings,
        "sgst_ledger",
        "input_sgst_ledger",
        "input sgst",
    )
    generic_tax_ledger = str(settings.get("tax_ledger") or "").strip()

    if igst_total or tax_mode == "gst_igst" or ("IGST" in invoice_text and "CGST" not in invoice_text):
        return [
            {
                "kind": "igst",
                "ledger": igst_ledger,
                "amount": round(igst_total or tax_total, 2),
                "field": "tax_ledger",
            }
        ]

    if cgst_total or sgst_total or tax_mode == "gst_cgst_sgst":
        if not cgst_total and not sgst_total:
            cgst_total = round(tax_total / 2, 2)
            sgst_total = round(tax_total - cgst_total, 2)
        return [
            {
                "kind": "cgst",
                "ledger": cgst_ledger if tax_mode == "gst_cgst_sgst" else cgst_ledger or generic_tax_ledger,
                "amount": round(cgst_total, 2),
                "field": "tax_settings.cgst_ledger",
            },
            {
                "kind": "sgst",
                "ledger": sgst_ledger if tax_mode == "gst_cgst_sgst" else sgst_ledger or generic_tax_ledger,
                "amount": round(sgst_total, 2),
                "field": "tax_settings.sgst_ledger",
            },
        ]

    return [
        {
            "kind": "tax",
            "ledger": generic_tax_ledger,
            "amount": tax_total,
            "field": "tax_ledger",
        }
    ]


def _ledger_entry(
    ledger: str,
    amount: float,
    deemed_positive: str,
    is_party: bool = False,
    bill_name: str = "",
) -> str:
    bill_xml = ""
    if is_party and bill_name:
        bill_xml = f"""
        <BILLALLOCATIONS.LIST>
          <NAME>{_xml(bill_name)}</NAME>
          <BILLTYPE>New Ref</BILLTYPE>
          <AMOUNT>{_fmt_amount(amount)}</AMOUNT>
        </BILLALLOCATIONS.LIST>"""
    return f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_xml(ledger)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>{deemed_positive}</ISDEEMEDPOSITIVE>
        <ISPARTYLEDGER>{'Yes' if is_party else 'No'}</ISPARTYLEDGER>
        <AMOUNT>{_fmt_amount(amount)}</AMOUNT>{bill_xml}
      </ALLLEDGERENTRIES.LIST>"""


def _build_inventory_entries(
    rows: List[Dict[str, Any]],
    settings: Dict[str, Any],
    classifier=None,
) -> str:
    if classifier:
        try:
            rows = classifier.classify_invoice_rows(rows)
        except Exception:
            pass

    purchase_ledger = settings.get("purchase_ledger") or "Purchase Accounts"
    godown_name = str(settings.get("godown_name") or "").strip()
    entries: List[str] = []
    for row in rows:
        stock_item = _line_stock_item(row, settings)
        quantity = _amount(row.get("QUANTITY") or row.get("QTY") or 1) or 1.0
        uom = _line_tally_uom(row, settings)
        unit_price = _amount(row.get("UNIT PRICE") or row.get("RATE"))
        net_amount = _line_net_amount(row)
        if not net_amount and unit_price:
            net_amount = round(quantity * unit_price, 2)
        if not unit_price and quantity:
            unit_price = round(net_amount / quantity, 6)

        qty_text = f"{_fmt_qty(quantity)} {uom}"
        rate_xml = f"<RATE>{_fmt_amount(unit_price)}/{_xml(uom)}</RATE>" if unit_price else ""
        godown_xml = ""
        if godown_name:
            godown_xml = f"""
        <BATCHALLOCATIONS.LIST>
          <GODOWNNAME>{_xml(godown_name)}</GODOWNNAME>
          <BATCHNAME>Primary Batch</BATCHNAME>
          <AMOUNT>-{_fmt_amount(net_amount)}</AMOUNT>
          <ACTUALQTY>{_xml(qty_text)}</ACTUALQTY>
          <BILLEDQTY>{_xml(qty_text)}</BILLEDQTY>
        </BATCHALLOCATIONS.LIST>"""

        entries.append(
            f"""
      <ALLINVENTORYENTRIES.LIST>
        <STOCKITEMNAME>{_xml(stock_item)}</STOCKITEMNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        {rate_xml}
        <AMOUNT>-{_fmt_amount(net_amount)}</AMOUNT>
        <ACTUALQTY>{_xml(qty_text)}</ACTUALQTY>
        <BILLEDQTY>{_xml(qty_text)}</BILLEDQTY>{godown_xml}
        <ACCOUNTINGALLOCATIONS.LIST>
          <LEDGERNAME>{_xml(_line_ledger(row, purchase_ledger))}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{_fmt_amount(net_amount)}</AMOUNT>
        </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>"""
        )
    return "".join(entries)


def _build_voucher_inventory_entries(
    payload: Dict[str, Any],
    settings: Dict[str, Any],
    classifier=None,
) -> str:
    """Build voucher-mode purchase entries with nested inventory allocations.

    This is how many TallyPrime users actually enter purchases: the voucher
    looks like a plain Dr/Cr accounting voucher (ISINVOICE=No, Accounting
    Voucher View), but each purchase ledger debit carries an
    INVENTORYALLOCATIONS.LIST so stock still updates. Lines are grouped by
    their resolved purchase ledger, so a client using one purchase ledger gets
    a single debit block and a client splitting across ledgers gets one block
    per ledger.
    """

    parts = _invoice_parts(payload)
    rows = parts["rows"]
    default_ledger = settings.get("purchase_ledger") or "Purchase Accounts"
    godown_name = str(settings.get("godown_name") or "").strip()
    if classifier:
        try:
            rows = classifier.classify_invoice_rows(rows)
        except Exception:
            pass

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_line_ledger(row, default_ledger), []).append(row)

    entries: List[str] = []

    tax_total = _tax_total(parts, rows)
    net_total = round(sum(_line_net_amount(row) for row in rows), 2)
    tcs_total = _summary_amount(parts, ["TCS", "TCS AMOUNT", "TOTAL TCS"])
    current_total = round(net_total + tax_total + tcs_total, 2)
    party_total = parts["total"] or current_total
    invoice_no = str(parts["header"].get("INVOICE NO.", "") or "SiftEntry")

    entries.append(
        _ledger_entry(
            parts["vendor"],
            party_total,
            "No",
            is_party=True,
            bill_name=invoice_no,
        )
    )

    for ledger, ledger_rows in grouped.items():
        allocations: List[str] = []
        ledger_total = 0.0
        for row in ledger_rows:
            stock_item = _line_stock_item(row, settings)
            quantity = _amount(row.get("QUANTITY") or row.get("QTY") or 1) or 1.0
            uom = _line_tally_uom(row, settings)
            unit_price = _amount(row.get("UNIT PRICE") or row.get("RATE"))
            net_amount = _line_net_amount(row)
            if not net_amount and unit_price:
                net_amount = round(quantity * unit_price, 2)
            if not unit_price and quantity:
                unit_price = round(net_amount / quantity, 6)
            ledger_total += net_amount

            qty_text = f"{_fmt_qty(quantity)} {uom}"
            rate_xml = (
                f"<RATE>{_fmt_amount(unit_price)}/{_xml(uom)}</RATE>"
                if unit_price
                else ""
            )
            godown_xml = ""
            if godown_name:
                godown_xml = f"""
          <BATCHALLOCATIONS.LIST>
            <GODOWNNAME>{_xml(godown_name)}</GODOWNNAME>
            <BATCHNAME>Primary Batch</BATCHNAME>
            <AMOUNT>-{_fmt_amount(net_amount)}</AMOUNT>
            <ACTUALQTY>{_xml(qty_text)}</ACTUALQTY>
            <BILLEDQTY>{_xml(qty_text)}</BILLEDQTY>
          </BATCHALLOCATIONS.LIST>"""

            allocations.append(
                f"""
        <INVENTORYALLOCATIONS.LIST>
          <STOCKITEMNAME>{_xml(stock_item)}</STOCKITEMNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          {rate_xml}
          <AMOUNT>-{_fmt_amount(net_amount)}</AMOUNT>
          <ACTUALQTY>{_xml(qty_text)}</ACTUALQTY>
          <BILLEDQTY>{_xml(qty_text)}</BILLEDQTY>{godown_xml}
        </INVENTORYALLOCATIONS.LIST>"""
            )

        entries.append(
            f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_xml(ledger)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <ISPARTYLEDGER>No</ISPARTYLEDGER>
        <AMOUNT>-{_fmt_amount(round(ledger_total, 2))}</AMOUNT>{"".join(allocations)}
      </ALLLEDGERENTRIES.LIST>"""
        )

    for component in _tax_ledger_components(parts, rows, settings):
        tax_ledger = component.get("ledger") or default_ledger
        entries.append(_ledger_entry(tax_ledger, -component.get("amount", 0), "Yes"))

    if tcs_total:
        tcs_ledger = settings.get("tcs_ledger") or default_ledger
        entries.append(_ledger_entry(tcs_ledger, -tcs_total, "Yes"))

    round_delta = round(party_total - current_total, 2)
    explicit_round = _summary_amount(
        parts,
        ["ROUND OFF", "ROUNDOFF", "ROUNDING", "ROUNDING OFF"],
    )
    if explicit_round:
        round_delta = explicit_round
    if abs(round_delta) >= 0.01:
        round_ledger = settings.get("round_off_ledger") or default_ledger
        entries.append(
            _ledger_entry(round_ledger, -round_delta, "Yes" if round_delta > 0 else "No")
        )

    return "".join(entries)


def _build_item_invoice_adjustment_entries(
    parts: Dict[str, Any],
    rows: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> str:
    entries: List[str] = []
    tax_total = _tax_total(parts, rows)
    for component in _tax_ledger_components(parts, rows, settings):
        ledger = component.get("ledger") or settings.get("purchase_ledger") or "Purchase Accounts"
        entries.append(_ledger_entry(ledger, -component.get("amount", 0), "Yes"))

    tcs_total = _summary_amount(parts, ["TCS", "TCS AMOUNT", "TOTAL TCS"])
    if tcs_total:
        tcs_ledger = settings.get("tcs_ledger") or settings.get("purchase_ledger") or "Purchase Accounts"
        entries.append(_ledger_entry(tcs_ledger, -tcs_total, "Yes"))

    net_total = round(sum(_line_net_amount(row) for row in rows), 2)
    current_total = round(net_total + tax_total + tcs_total, 2)
    round_delta = round((parts["total"] or current_total) - current_total, 2)
    explicit_round = _summary_amount(parts, ["ROUND OFF", "ROUNDOFF", "ROUNDING", "ROUNDING OFF"])
    if explicit_round:
        round_delta = explicit_round
    if abs(round_delta) >= 0.01:
        round_ledger = settings.get("round_off_ledger") or settings.get("purchase_ledger") or "Purchase Accounts"
        entries.append(_ledger_entry(round_ledger, -round_delta, "Yes" if round_delta > 0 else "No"))

    return "".join(entries)


def _build_ledger_entries(
    payload: Dict[str, Any],
    settings: Dict[str, Any],
    classifier=None,
) -> str:
    parts = _invoice_parts(payload)
    rows = parts["rows"]
    default_ledger = settings.get("purchase_ledger") or "Purchase Accounts"
    if classifier:
        try:
            rows = classifier.classify_invoice_rows(rows)
        except Exception:
            pass

    ledger_totals: Dict[str, float] = {}
    for row in rows:
        amount = _amount(row.get("EXTENDED AMOUNT") or row.get("AMOUNT"))
        ledger = _line_ledger(row, default_ledger)
        ledger_totals[ledger] = ledger_totals.get(ledger, 0.0) + amount

    if not ledger_totals and parts["total"]:
        ledger_totals[default_ledger] = parts["total"]

    for component in _tax_ledger_components(parts, rows, settings):
        tax_target = component.get("ledger") or default_ledger
        ledger_totals[tax_target] = ledger_totals.get(tax_target, 0.0) + component.get("amount", 0)

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
          <NAME>{_xml(inv_no or "SiftEntry")}</NAME>
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
    """Build a TallyPrime XML import.

    Item Invoice mode creates inventory-backed purchase invoices for clients
    whose stock items already exist in Tally. Accounting Voucher mode remains
    available for service/non-stock bills.
    """

    settings = settings or current_settings()
    parts = _invoice_parts(payload)
    header = parts["header"]
    invoice_no = str(header.get("INVOICE NO.", "") or "SiftEntry")
    invoice_date = _to_tally_date(header.get("INVOICE DATE", ""))
    voucher_type = settings.get("voucher_type") or "Purchase"
    company = settings.get("company") or ""
    static_company = f"<SVCURRENTCOMPANY>{_xml(company)}</SVCURRENTCOMPANY>" if company else ""
    narration = "Imported by SiftEntry"
    po_no = header.get("PO NO./CONTRACT NO.", "")
    if po_no and po_no != "N/A":
        narration += " | PO: " + str(po_no)

    if _is_item_invoice_mode(settings) and parts["rows"]:
        inventory_entries = _build_inventory_entries(parts["rows"], settings, classifier=classifier)
        adjustment_entries = _build_item_invoice_adjustment_entries(parts, parts["rows"], settings)
        computed_total = round(sum(_line_net_amount(row) for row in parts["rows"]) + _tax_total(parts, parts["rows"]), 2)
        party_total = parts["total"] or computed_total
        party_entry = _ledger_entry(parts["vendor"], party_total, "No", is_party=True, bill_name=invoice_no)
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
        <VOUCHER VCHTYPE="{_xml(voucher_type)}" ACTION="Create" OBJVIEW="Invoice Voucher View">
          <DATE>{invoice_date}</DATE>
          <EFFECTIVEDATE>{invoice_date}</EFFECTIVEDATE>
          <VOUCHERTYPENAME>{_xml(voucher_type)}</VOUCHERTYPENAME>
          <VOUCHERNUMBER>{_xml(invoice_no)}</VOUCHERNUMBER>
          <REFERENCE>{_xml(invoice_no)}</REFERENCE>
          <REFERENCEDATE>{invoice_date}</REFERENCEDATE>
          <PARTYLEDGERNAME>{_xml(parts["vendor"])}</PARTYLEDGERNAME>
          <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
          <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
          <ISINVOICE>Yes</ISINVOICE>
          <NARRATION>{_xml(narration)}</NARRATION>{party_entry}{inventory_entries}{adjustment_entries}
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""

    if _is_voucher_with_inventory_mode(settings) and parts["rows"]:
        voucher_entries = _build_voucher_inventory_entries(
            payload,
            settings,
            classifier=classifier,
        )
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
          <EFFECTIVEDATE>{invoice_date}</EFFECTIVEDATE>
          <VOUCHERTYPENAME>{_xml(voucher_type)}</VOUCHERTYPENAME>
          <VOUCHERNUMBER>{_xml(invoice_no)}</VOUCHERNUMBER>
          <REFERENCE>{_xml(invoice_no)}</REFERENCE>
          <REFERENCEDATE>{invoice_date}</REFERENCEDATE>
          <PARTYLEDGERNAME>{_xml(parts["vendor"])}</PARTYLEDGERNAME>
          <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>
          <VCHENTRYMODE>Voucher</VCHENTRYMODE>
          <ISINVOICE>No</ISINVOICE>
          <NARRATION>{_xml(narration)}</NARRATION>{voucher_entries}
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""

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


def _tally_issue(
    code: str,
    message: str,
    field: str = "",
    blocking: bool = True,
) -> Dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "field": field,
        "blocking": blocking,
    }


def _friendly_tally_message(message: str) -> str:
    text = str(message or "").strip()
    ledger_match = re.search(r"Ledger ['\"]?([^'\"!]+)['\"]? does not exist", text, re.I)
    if ledger_match:
        ledger = ledger_match.group(1).strip()
        return (
            f"Tally rejected the voucher because ledger '{ledger}' does not exist. "
            "Open the selected client profile and use the exact ledger name from "
            "Tally. For India GST profiles, check Purchase ledger, IGST/CGST/SGST "
            "ledgers, TCS ledger, and Round-off ledger. If the name is correct, "
            "create that ledger in Tally before retrying."
        )
    stock_match = re.search(r"Stock Item ['\"]?([^'\"!]+)['\"]? does not exist", text, re.I)
    if stock_match:
        item = stock_match.group(1).strip()
        return (
            f"Tally rejected the item invoice because stock item '{item}' does not exist. "
            "Map the invoice line to an existing Tally stock item in the client profile, "
            "or create the stock item in Tally before posting."
        )
    godown_match = re.search(r"Godown ['\"]?([^'\"!]+)['\"]? does not exist", text, re.I)
    if godown_match:
        godown = godown_match.group(1).strip()
        return (
            f"Tally rejected the item invoice because godown '{godown}' does not exist. "
            "Set the client profile godown to the exact Tally location, or leave it blank "
            "if this client does not use godowns."
        )
    if "voucher type" in text.lower() and "does not exist" in text.lower():
        return (
            "Tally rejected the voucher type. Confirm the client profile voucher type "
            "matches the exact Tally name, usually 'Purchase' for inbound bills."
        )
    if "unit" in text.lower() and "does not exist" in text.lower():
        return (
            "Tally rejected the item unit. Confirm the client profile UOM matches the "
            "exact Tally unit symbol for this stock item, for example KGS instead of KG."
        )
    if "company" in text.lower() and ("does not exist" in text.lower() or "not found" in text.lower()):
        return (
            "Tally could not post into the selected company. Keep the correct company "
            "open in TallyPrime and make sure the client profile company name matches it exactly."
        )
    return text or "Tally rejected this voucher."


def _tally_error_issues(message: str) -> List[Dict[str, Any]]:
    text = str(message or "")
    ledger_match = re.search(r"ledger '([^']+)'", text, re.I)
    if ledger_match:
        ledger = ledger_match.group(1)
        return [
            _tally_issue(
                "tally_ledger_missing",
                f"Ledger '{ledger}' is missing in Tally or not mapped in this client profile.",
                "purchase_ledger",
            )
        ]
    stock_match = re.search(r"stock item '([^']+)'", text, re.I)
    if stock_match:
        item = stock_match.group(1)
        return [
            _tally_issue(
                "tally_stock_item_missing",
                f"Stock item '{item}' is missing in Tally or not mapped in this client profile.",
                "stock_item_name",
            )
        ]
    godown_match = re.search(r"godown '([^']+)'", text, re.I)
    if godown_match:
        godown = godown_match.group(1)
        return [
            _tally_issue(
                "tally_godown_missing",
                f"Godown '{godown}' is missing in Tally or not mapped in this client profile.",
                "godown_name",
            )
        ]
    return []


def _tally_preflight_issues(
    payload: Dict[str, Any],
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    parts = _invoice_parts(payload)
    rows = parts["rows"]
    posting_mode = _posting_mode(settings)
    is_item_invoice = posting_mode in ITEM_INVOICE_ALIASES or posting_mode in VOUCHER_WITH_INVENTORY_ALIASES
    issues: List[Dict[str, Any]] = []

    if not str(settings.get("company") or "").strip():
        issues.append(
            _tally_issue(
                "tally_company_missing",
                "Tally company name is not set in the selected client profile.",
                "company_name",
            )
        )
    if not str(settings.get("voucher_type") or "").strip():
        issues.append(
            _tally_issue(
                "tally_voucher_type_missing",
                "Voucher type is not set in the selected client profile.",
                "voucher_type",
            )
        )

    tax_components = _tax_ledger_components(parts, rows, settings)
    tax_total = round(sum(_amount(component.get("amount")) for component in tax_components), 2)
    tcs_total = _summary_amount(parts, ["TCS", "TCS AMOUNT", "TOTAL TCS"])
    net_total = round(sum(_line_net_amount(row) for row in rows), 2)
    current_total = round(net_total + tax_total + tcs_total, 2)
    round_delta = round((parts["total"] or current_total) - current_total, 2)
    explicit_round = _summary_amount(
        parts,
        ["ROUND OFF", "ROUNDOFF", "ROUNDING", "ROUNDING OFF"],
    )
    if explicit_round:
        round_delta = explicit_round

    if is_item_invoice:
        purchase_ledger = str(settings.get("purchase_ledger") or "").strip()
        if not purchase_ledger:
            issues.append(
                _tally_issue(
                    "tally_purchase_ledger_missing",
                    "Item Invoice posting needs the exact Tally purchase ledger for inventory accounting allocations.",
                    "purchase_ledger",
                )
            )
        if not rows:
            issues.append(
                _tally_issue(
                    "tally_item_rows_missing",
                    "Item Invoice posting needs at least one extracted line item.",
                    "lines",
                )
            )
        for index, row in enumerate(rows, start=1):
            stock_item = str(
                row.get("TALLY_STOCK_ITEM")
                or row.get("TALLY ITEM")
                or row.get("TARGET_ITEM_NAME")
                or row.get("TARGET ITEM")
                or row.get("STOCK ITEM")
                or row.get("ITEM")
                or settings.get("stock_item_name")
                or ""
            ).strip()
            if not stock_item:
                issues.append(
                    _tally_issue(
                        "tally_stock_item_missing",
                        f"Line {index} needs a stock item name that exists in Tally.",
                        "stock_item_name",
                    )
                )
            configured_hsn = str(settings.get("stock_item_hsn") or "").strip()
            row_hsn = str(row.get("HSN/SAC") or row.get("HSN") or "").strip()
            if configured_hsn and row_hsn and configured_hsn != row_hsn:
                issues.append(
                    _tally_issue(
                        "tally_hsn_mismatch",
                        f"Line {index} HSN/SAC is {row_hsn}, but the client profile stock item HSN/SAC is {configured_hsn}.",
                        "stock_item_hsn",
                        blocking=False,
                    )
                )

    for component in tax_components:
        ledger = str(component.get("ledger") or "").strip()
        amount = _amount(component.get("amount"))
        kind = str(component.get("kind") or "tax").upper()
        field = str(component.get("field") or "tax_ledger")
        if amount and not ledger:
            issues.append(
                _tally_issue(
                    f"tally_{kind.lower()}_ledger_missing",
                    f"This invoice has {kind}, so the exact Tally {kind} ledger must be set in the selected client profile.",
                    field,
                )
            )
    if tcs_total and not str(settings.get("tcs_ledger") or "").strip():
        issues.append(
            _tally_issue(
                "tally_tcs_ledger_missing",
                "This invoice has TCS, so the exact Tally TCS ledger must be set in the selected client profile.",
                "tcs_ledger",
            )
        )
    if abs(round_delta) >= 0.01 and not str(settings.get("round_off_ledger") or "").strip():
        issues.append(
            _tally_issue(
                "tally_round_off_ledger_missing",
                "This invoice has a round-off adjustment, so the exact Tally round-off ledger must be set in the selected client profile.",
                "round_off_ledger",
            )
        )
    return issues


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


def send_to_tally(
    payload: Dict[str, Any],
    classifier=None,
    dry_run: bool = False,
    settings_override: Optional[Dict[str, Any]] = None,
    connector_settings_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests not installed", "response": None}
    settings = {**current_settings(), **(settings_override or {})}
    connector_settings = {
        **current_connector_settings(),
        **(connector_settings_override or {}),
    }
    invoice_no = _invoice_parts(payload)["header"].get("INVOICE NO.", "invoice")
    preflight_issues = _tally_preflight_issues(payload, settings)
    blocking_issues = [issue for issue in preflight_issues if issue.get("blocking", True)]
    if blocking_issues:
        return {
            "success": False,
            "message": "Tally profile is incomplete: "
            + "; ".join(issue["message"] for issue in blocking_issues),
            "issues": preflight_issues,
            "response": {"invoice": invoice_no, "preflight": preflight_issues},
        }
    xml = build_tally_xml(payload, settings=settings, classifier=classifier)
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
        friendly = _friendly_tally_message(detail)
        return {
            "success": False,
            "message": "Connector import failed: " + friendly,
            "issues": _tally_error_issues(friendly),
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
    friendly = _friendly_tally_message(str(detail))
    return {
        "success": False,
        "message": "Tally import failed (" + str(response.status_code) + "): " + friendly,
        "issues": _tally_error_issues(friendly),
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
            preflight_issues = _tally_preflight_issues(payload, settings)
            blocking_issues = [
                issue for issue in preflight_issues if issue.get("blocking", True)
            ]
            if blocking_issues:
                results[fname] = {
                    "success": False,
                    "message": "Tally profile is incomplete: "
                    + "; ".join(issue["message"] for issue in blocking_issues),
                    "issues": preflight_issues,
                    "response": {"invoice": invoice_id, "preflight": preflight_issues},
                }
                continue
            xml = build_tally_xml(payload, settings=settings, classifier=classifier)
            vouchers.append({"invoice_id": invoice_id, "xml": xml})
            name_by_invoice_id[invoice_id] = fname
        if not vouchers:
            return {
                "success": False,
                "message": "Tally profile is incomplete for all selected invoices.",
                "results": results,
                "response": {"preflight": True},
            }
        batch_result = send_xml_batch_to_connector(vouchers, settings=connector_settings, dry_run=dry_run)
        for item in batch_result.get("results", []) or []:
            fname = name_by_invoice_id.get(str(item.get("invoice_id", "")), str(item.get("invoice_id", "")))
            message = str(item.get("message", batch_result.get("message", "")))
            if not item.get("success"):
                message = _friendly_tally_message(message)
            results[fname] = {
                "success": bool(item.get("success")),
                "message": message,
                "issues": _tally_error_issues(message),
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
            batch_message = "Connector import failed: " + _friendly_tally_message(
                _connector_failure_details(batch_result)
            )
        final_success = all(item.get("success") for item in results.values())
        if not final_success and batch_result.get("success"):
            batch_message = "Some selected invoices were blocked by Tally profile preflight."
        return {
            "success": final_success,
            "message": batch_message,
            "results": results,
            "response": batch_result,
        }

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
            value=connector_settings.get("workspace_id", "local-workspace"),
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
            "workspace_id": workspace_id.strip() or "local-workspace",
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
        profile_options = list(TALLY_SETUP_PROFILES.keys())
        saved_profile = str(settings.get("setup_profile") or "generic")
        if saved_profile not in TALLY_SETUP_PROFILES:
            saved_profile = "generic"
        selected_profile = st.selectbox(
            "Client setup profile",
            profile_options,
            index=profile_options.index(saved_profile),
            format_func=lambda profile_id: TALLY_SETUP_PROFILES[profile_id]["label"],
            key="tally_setup_profile",
            help="Use a saved client profile for exact Tally company, ledger, stock item, GST, TCS, and round-off names.",
        )
        profile_values = _profile_defaults(selected_profile)
        if selected_profile == saved_profile:
            field_settings = {**profile_values, **settings}
        else:
            field_settings = {**settings, **profile_values, "setup_profile": selected_profile}

        url = st.text_input("Tally URL", value=field_settings.get("url", "http://localhost:9000"), key=f"tally_url_{selected_profile}")
        company = st.text_input(
            "Tally company name",
            value=field_settings.get("company", ""),
            placeholder="Exact company name open in TallyPrime",
            key=f"tally_company_{selected_profile}",
        )
        posting_options = ["Item Invoice", "Accounting Voucher"]
        saved_posting_mode = str(field_settings.get("posting_mode") or "Accounting Voucher")
        posting_index = 0 if saved_posting_mode not in posting_options else posting_options.index(saved_posting_mode)
        posting_mode = st.selectbox(
            "Posting mode",
            posting_options,
            index=posting_index,
            key=f"tally_posting_mode_{selected_profile}",
            help="Use Item Invoice when Tally stock items already exist. Use Accounting Voucher for non-stock/service bills.",
        )
        voucher_type = st.text_input("Voucher type", value=field_settings.get("voucher_type", "Purchase"), key=f"tally_voucher_type_{selected_profile}")
        purchase_ledger = st.text_input(
            "Purchase/expense ledger",
            value=field_settings.get("purchase_ledger", "Purchase Accounts"),
            key=f"tally_purchase_ledger_{selected_profile}",
        )
        tax_ledger = st.text_input("GST ledger", value=field_settings.get("tax_ledger", ""), key=f"tally_tax_ledger_{selected_profile}")
        i1, i2 = st.columns(2)
        with i1:
            stock_item_name = st.text_input(
                "Stock item override",
                value=field_settings.get("stock_item_name", ""),
                key=f"tally_stock_item_name_{selected_profile}",
                help="Optional. Used when an invoice line matches the configured HSN. Leave blank to use the parsed item description.",
            )
            tcs_ledger = st.text_input("TCS ledger", value=field_settings.get("tcs_ledger", ""), key=f"tally_tcs_ledger_{selected_profile}")
        with i2:
            stock_item_hsn = st.text_input(
                "Stock item HSN",
                value=field_settings.get("stock_item_hsn", ""),
                key=f"tally_stock_item_hsn_{selected_profile}",
            )
            stock_item_uom = st.text_input(
                "Tally stock UOM",
                value=field_settings.get("stock_item_uom", ""),
                key=f"tally_stock_item_uom_{selected_profile}",
                help="Exact Tally unit symbol for the stock item. The parser may normalize KGS as KG, but Tally may require KGS.",
            )
            round_off_ledger = st.text_input(
                "Round-off ledger",
                value=field_settings.get("round_off_ledger", ""),
                key=f"tally_round_off_ledger_{selected_profile}",
            )
        godown_name = st.text_input(
            "Godown/location master name",
            value=field_settings.get("godown_name", ""),
            placeholder="Optional. Leave blank if the client does not use godowns.",
            key=f"tally_godown_name_{selected_profile}",
        )
        if selected_profile == "india_gst_item_invoice":
            st.caption("Starter template only: fill the client's exact Tally company, purchase ledger, GST ledger, stock item, HSN/SAC, unit, and optional adjustment ledgers before posting.")
        elif posting_mode == "Item Invoice":
            st.caption("Item Invoice mode needs exact Tally stock item, unit, purchase ledger, and tax/adjustment ledger names for this client.")

        new_settings = {
            "setup_profile": selected_profile,
            "url": url.strip(),
            "company": company.strip(),
            "posting_mode": posting_mode,
            "voucher_type": voucher_type.strip() or "Purchase",
            "purchase_ledger": purchase_ledger.strip() or "Purchase Accounts",
            "tax_ledger": tax_ledger.strip(),
            "stock_item_name": stock_item_name.strip(),
            "stock_item_hsn": stock_item_hsn.strip(),
            "stock_item_uom": stock_item_uom.strip(),
            "godown_name": godown_name.strip(),
            "tcs_ledger": tcs_ledger.strip(),
            "round_off_ledger": round_off_ledger.strip(),
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
