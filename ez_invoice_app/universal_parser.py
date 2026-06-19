"""Generic invoice parsing helpers for EZ-Invoice.

This module provides a conservative fallback that normalizes supplier PDFs into
the same payload shape used by the accounting exports.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


CURRENCY_SYMBOLS = {
    "$": "USD",
    "₹": "INR",
    "£": "GBP",
    "€": "EUR",
}

CURRENCY_CODES = (
    "USD|INR|EUR|GBP|CAD|AUD|JPY|CHF|SGD|AED|SAR|ZAR|NZD|HKD|CNY|MXN|BRL"
)

DATE_FORMATS = [
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%m.%d.%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
]


def normalize_text(text: str) -> str:
    return (text or "").replace("\u00a0", " ")


def normalize_lines(text: str) -> List[str]:
    return [line.strip() for line in normalize_text(text).splitlines() if line.strip()]


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    clean = re.sub(r"[^0-9.\-]", "", str(value))
    if clean in ("", "-", "."):
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def money0(value: Any) -> float:
    parsed = to_float(value)
    return float(parsed) if parsed is not None else 0.0


def looks_like_structured_vendor_invoice(text: str) -> bool:
    upper = normalize_text(text).upper()
    return any(
        marker in upper
        for marker in [
            "WORLD FUEL SERVICES",
            "WORLD FUEL",
            "COLT INTERNATIONAL",
            "AVCARD",
            "AMOUNT TO BE EFT DRAFTED",
        ]
    )

def _compact_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_date(value: str) -> str:
    raw = _compact_space(value).replace(",", ", ")
    raw = re.sub(r"\s+", " ", raw)
    candidates = [raw]
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2}", raw):
        d1, d2, yy = raw.split("/")
        candidates.extend([f"{d1}/{d2}/20{yy}", f"{d1}/{d2}/19{yy}"])
    if re.fullmatch(r"\d{1,2}-[A-Za-z]{3}-\d{2}", raw):
        candidates.append(raw[:-2] + "20" + raw[-2:])
    for candidate in candidates:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).strftime("%d-%b-%Y").upper()
            except ValueError:
                continue
    return raw.upper()


def _find_label_value(text: str, labels: List[str], value_pattern: str, flags: int = re.IGNORECASE) -> str:
    label_pat = "|".join(re.escape(label) for label in labels)
    patterns = [
        rf"(?:{label_pat})\s*[:#\-]?\s*({value_pattern})",
        rf"(?:{label_pat})\s*\n\s*({value_pattern})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _compact_space(match.group(1))
    return ""


def _find_invoice_no(text: str, filename: str) -> str:
    value = _find_label_value(
        text,
        ["Invoice Number", "Invoice No", "Invoice #", "Inv No", "Bill Number", "Bill No"],
        r"[A-Z0-9][A-Z0-9\-\/_.]{2,40}",
    )
    if value:
        return value.rstrip(".")

    match = re.search(r"\b(?:INV|INVOICE|BILL)[\-\/ ]?[A-Z0-9]{3,30}\b", text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)


def _find_date(text: str, labels: List[str]) -> str:
    date_pat = (
        r"(?:\d{1,2}[-/ .][A-Za-z]{3,9}[-/ .,]\s*\d{2,4}|"
        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
    )
    value = _find_label_value(text, labels, date_pat)
    if value:
        return _parse_date(value)
    match = re.search(date_pat, text, re.IGNORECASE)
    return _parse_date(match.group(0)) if match else ""


def _find_currency(text: str) -> str:
    code_match = re.search(rf"\b({CURRENCY_CODES})\b", text, re.IGNORECASE)
    if code_match:
        return code_match.group(1).upper()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return "USD"


def _find_amount_by_labels(text: str, labels: List[str]) -> float:
    amount_pat = r"([$₹£€]?\s*[0-9][0-9,]*(?:\.\d{2})?)"
    label_pat = "|".join(re.escape(label) for label in labels)
    matches = list(re.finditer(rf"(?:{label_pat})\s*[:\-]?\s*{amount_pat}", text, re.IGNORECASE))
    if matches:
        return money0(matches[-1].group(1))
    return 0.0


def _find_total(text: str) -> float:
    total = _find_amount_by_labels(
        text,
        ["Total Amount Due", "Amount Due", "Balance Due", "Grand Total", "Invoice Total", "Total Due", "Total"],
    )
    if total:
        return total

    amounts = [money0(m.group(0)) for m in re.finditer(r"[$₹£€]?\s*[0-9][0-9,]*\.\d{2}", text)]
    return max(amounts) if amounts else 0.0


def _find_tax(text: str) -> float:
    return _find_amount_by_labels(text, ["Tax Amount", "Total Tax", "GST", "VAT", "Sales Tax"])


def _seller_name(lines: List[str]) -> str:
    skip = re.compile(r"invoice|tax invoice|bill|receipt|statement", re.IGNORECASE)
    for line in lines[:12]:
        clean = _compact_space(line)
        if len(clean) < 3 or skip.fullmatch(clean):
            continue
        if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", clean):
            continue
        return clean[:120]
    return "Unknown Supplier"


def _bill_to(text: str) -> Dict[str, Any]:
    lines = normalize_lines(text)
    for idx, line in enumerate(lines):
        if re.search(r"\b(Bill To|Billed To|Customer|Client)\b", line, re.IGNORECASE):
            collected = []
            for next_line in lines[idx + 1 : idx + 6]:
                if re.search(r"\b(Ship To|Invoice|Date|Due|Total|Description|Qty)\b", next_line, re.IGNORECASE):
                    break
                collected.append(next_line)
            if collected:
                return {"NAME": collected[0], "ADDRESS": collected[1:]}
    return {"NAME": "", "ADDRESS": []}


def _line_item_region(lines: List[str]) -> List[str]:
    start = 0
    end = len(lines)
    for idx, line in enumerate(lines):
        if re.search(r"\b(description|particulars|item|service).*\b(amount|total|qty|quantity|rate|price)\b", line, re.IGNORECASE):
            start = idx + 1
            break
    for idx in range(start, len(lines)):
        if re.search(r"\b(subtotal|sub total|grand total|invoice total|amount due|balance due)\b", lines[idx], re.IGNORECASE):
            end = idx
            break
    return lines[start:end]


def _parse_line_items(text: str, invoice_total: float, tax_total: float) -> Tuple[List[Dict[str, Any]], str]:
    rows: List[Dict[str, Any]] = []
    region = _line_item_region(normalize_lines(text))
    amount_pat = r"([\-]?[0-9][0-9,]*(?:\.\d{2})?)$"
    qty_price_amount = re.compile(
        r"^(?P<desc>.+?)\s+(?P<qty>[0-9][0-9,]*(?:\.\d+)?)\s+"
        r"(?P<unit>[0-9][0-9,]*(?:\.\d{2})?)\s+(?P<amount>[0-9][0-9,]*(?:\.\d{2})?)$"
    )

    for line in region:
        clean = _compact_space(line)
        if len(clean) < 4:
            continue
        if re.search(r"\b(total|subtotal|tax|balance|amount due|invoice no|date)\b", clean, re.IGNORECASE):
            continue

        structured = qty_price_amount.match(clean)
        if structured:
            desc = structured.group("desc").strip(":- ")
            amount = money0(structured.group("amount"))
            if desc and amount:
                rows.append(
                    {
                        "DESCRIPTION": desc,
                        "QUANTITY": money0(structured.group("qty")),
                        "UOM": "EA",
                        "UNIT PRICE": money0(structured.group("unit")),
                        "PRICE BASIS": "",
                        "EXTENDED AMOUNT": amount,
                        "TAX AMOUNT": 0.0,
                        "AMOUNT": amount,
                    }
                )
                continue

        amount_match = re.search(amount_pat, clean)
        if not amount_match:
            continue
        desc = clean[: amount_match.start()].strip(":- ")
        amount = money0(amount_match.group(1))
        if desc and amount:
            rows.append(
                {
                    "DESCRIPTION": desc[:180],
                    "QUANTITY": 1.0,
                    "UOM": "EA",
                    "UNIT PRICE": amount,
                    "PRICE BASIS": "",
                    "EXTENDED AMOUNT": amount,
                    "TAX AMOUNT": 0.0,
                    "AMOUNT": amount,
                }
            )

    if rows:
        return rows, "line_table"

    fallback_amount = invoice_total if invoice_total else tax_total
    return (
        [
            {
                "DESCRIPTION": "Invoice total",
                "QUANTITY": 1.0,
                "UOM": "EA",
                "UNIT PRICE": fallback_amount,
                "PRICE BASIS": "",
                "EXTENDED AMOUNT": fallback_amount,
                "TAX AMOUNT": tax_total,
                "AMOUNT": fallback_amount,
            }
        ]
        if fallback_amount
        else [],
        "total_fallback",
    )


def parse_generic_invoice(
    filename: str,
    text: str,
    engine: str,
    pages: int,
    extracted_at: str,
) -> Dict[str, Any]:
    """Return a normalized payload for general supplier invoices."""

    text = normalize_text(text)
    lines = normalize_lines(text)
    invoice_no = _find_invoice_no(text, filename)
    invoice_date = _find_date(text, ["Invoice Date", "Bill Date", "Date"])
    due_date = _find_date(text, ["Due Date", "Payment Due", "Pay By"])
    if not due_date and invoice_date:
        try:
            due_date = (datetime.strptime(invoice_date, "%d-%b-%Y") + timedelta(days=30)).strftime("%d-%b-%Y").upper()
        except ValueError:
            due_date = ""

    currency = _find_currency(text)
    total = _find_total(text)
    tax = _find_tax(text)
    rows, mode = _parse_line_items(text, total, tax)

    bill_to = _bill_to(text)
    seller = {"NAME": _seller_name(lines), "ADDRESS": []}

    return {
        "INVOICE": {
            "DOCUMENT": {
                "DOCUMENT TYPE": "INVOICE",
                "PAGE NO.": "1 - " + str(pages or 1),
                "PAGES": pages,
                "EXTRACTED AT": extracted_at,
                "SOURCE FILE": filename,
                "EXTRACTION ENGINE": engine,
                "SCHEMA VERSION": "EZ-1.0",
                "PARSER": "Generic",
            },
            "BILL TO": bill_to,
            "SELLER": seller,
            "INVOICE HEADER": {
                "CUSTOMER NO.": "",
                "INVOICE NO.": invoice_no,
                "INVOICE DATE": invoice_date,
                "DUE DATE": due_date,
                "SALES ORDER NO.": "",
                "PO NO./CONTRACT NO.": _find_label_value(text, ["PO Number", "PO No", "Purchase Order"], r"[A-Z0-9\-\/_.]{2,40}") or "N/A",
                "AMOUNT TO BE EFT DRAFTED": total,
                "INVOICE AMOUNT": total,
            },
            "PAYMENT": {"ELECTRONIC": {"CURRENCY": currency, "AMOUNT": float(total or 0)}},
            "CONTEXT": {},
            "LINE ITEMS": {
                "COLUMNS": ["DESCRIPTION", "QUANTITY", "UNIT PRICE", "EXTENDED AMOUNT", "TAX AMOUNT", "AMOUNT"],
                "ROWS": rows,
            },
            "USD USD USD": {"TOTAL TAX": tax},
            "INVOICE TAX SUMMARY": {"TOTAL TAX": tax},
            "REMIT TO": {},
            "OR WIRE TO": {},
            "COMMENTS": {},
            "PARSER_DIAGNOSTICS": {"mode": mode, "parser": "generic"},
        }
    }
