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

STRUCTURED_INVNO_PAT = r"\d{6,8}-\d{5}(?:-\d+)?"
STRUCTURED_DATE_PAT = r"\d{1,2}-[A-Z]{3}-\d{2,4}"
STRUCTURED_CUSTOMER_PAT = r"\d{3,8}"

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


def _normal_structured_date(value: str) -> str:
    value = (value or "").strip().upper()
    if re.fullmatch(r"\d{1,2}-[A-Z]{3}-\d{2}", value):
        value = value[:-2] + "20" + value[-2:]
    return value


def _valid_structured_customer(value: str) -> bool:
    value = (value or "").strip()
    return bool(re.fullmatch(STRUCTURED_CUSTOMER_PAT, value)) and not set(value) <= {"0"}


def _structured_header_triplet(text: str) -> Tuple[str, str, str]:
    """Extract customer, invoice number, and invoice date from columnar invoice headers."""

    patterns = [
        re.compile(
            rf"(?<![.\d])(?P<customer>{STRUCTURED_CUSTOMER_PAT})\s+"
            rf"(?P<invoice>{STRUCTURED_INVNO_PAT})\s+"
            rf"(?P<date>{STRUCTURED_DATE_PAT})(?![A-Z0-9-])",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<date>{STRUCTURED_DATE_PAT})\s*"
            rf"(?P<invoice>{STRUCTURED_INVNO_PAT})\s*"
            rf"(?P<customer>{STRUCTURED_CUSTOMER_PAT})(?![.\d])",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<invoice>{STRUCTURED_INVNO_PAT})\s+"
            rf"(?P<date>{STRUCTURED_DATE_PAT})\s+"
            rf"(?P<customer>{STRUCTURED_CUSTOMER_PAT})(?![.\d])",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<invoice>{STRUCTURED_INVNO_PAT})\s+"
            rf"(?P<customer>{STRUCTURED_CUSTOMER_PAT})\s+"
            rf"(?P<date>{STRUCTURED_DATE_PAT})(?![A-Z0-9-])",
            re.IGNORECASE,
        ),
    ]
    lines = normalize_lines(text)
    label_re = re.compile(
        r"(CUSTOMER\s+NO|INVOICE\s+NO|INVOICE\s+DATE|PAGE\s+NO)",
        re.IGNORECASE,
    )
    windows = []
    for idx, line in enumerate(lines):
        if label_re.search(line):
            windows.append("\n".join(lines[max(0, idx - 10) : min(len(lines), idx + 16)]))
    windows.append(normalize_text(text))

    for window in windows:
        for pattern in patterns:
            for match in pattern.finditer(window):
                customer = match.group("customer")
                if _valid_structured_customer(customer):
                    return (
                        customer,
                        match.group("invoice"),
                        _normal_structured_date(match.group("date")),
                    )
    return "", "", ""


def _next_value_after_label(lines: List[str], label_pattern: str, value_pattern: str = r".+") -> str:
    label_re = re.compile(label_pattern, re.IGNORECASE)
    value_re = re.compile(value_pattern, re.IGNORECASE)
    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue
        same_line = label_re.sub("", line, count=1).strip(" :-")
        if same_line and not re.fullmatch(r"[\W_]+", same_line) and value_re.fullmatch(same_line):
            return same_line
        for candidate in lines[idx + 1 : idx + 10]:
            clean = _compact_space(candidate)
            if not clean:
                continue
            if re.search(r"\b(INVOICE|CUSTOMER|DESCRIPTION|QUANTITY|EXTENDED|TAX AMOUNT)\b", clean, re.IGNORECASE):
                continue
            if value_re.fullmatch(clean):
                return clean
    return ""


def _structured_parties(lines: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    seller_name = ""
    seller_address: List[str] = []
    for idx, line in enumerate(lines):
        if re.fullmatch(r"WORLD\s+FUEL\s+SERVICES,\s+INC\.?", line, re.IGNORECASE):
            seller_name = _compact_space(line)
            before = [
                _compact_space(item)
                for item in lines[max(0, idx - 3) : idx]
                if re.search(r"\d|MIAMI|STREET|SUITE|FL\b", item, re.IGNORECASE)
                and not re.search(r"\b(TAX\s+REG|GSTIN|VAT|TIN)\b", item, re.IGNORECASE)
            ]
            after = [
                _compact_space(item)
                for item in lines[idx + 1 : idx + 4]
                if not re.search(r"terms and conditions|invoice|remit|tax\s+reg|gstin|vat|tin", item, re.IGNORECASE)
            ]
            seller_address = before or after
            break
    if not seller_name:
        for line in lines[:20]:
            if "WORLD FUEL SERVICES" in line.upper():
                seller_name = _compact_space(line)
                break

    customer_name = ""
    customer_address: List[str] = []
    customer_tax_id = ""
    for idx, line in enumerate(lines[:20]):
        clean = _compact_space(line)
        if re.search(r"\b(tel|email|internet|world fuel|terms and conditions)\b", clean, re.IGNORECASE):
            continue
        if re.search(r"\b(AIRCRAFT|MANAGEMENT|LDA|INC|LTD|LLC|PVT|PRIVATE|ENTERPRISE)\b", clean, re.IGNORECASE):
            customer_name = clean
            for candidate in lines[idx + 1 : idx + 6]:
                candidate = _compact_space(candidate)
                tax_match = re.search(r"\b(?:TAX\s+REG|GSTIN|VAT|TIN)[:\s-]+(.+)$", candidate, re.IGNORECASE)
                if tax_match:
                    customer_tax_id = _compact_space(tax_match.group(1))
                    break
                if re.search(r"\b(WORLD FUEL|INVOICE|TEL|EMAIL)\b", candidate, re.IGNORECASE):
                    break
                customer_address.append(candidate)
            break

    return (
        {"NAME": customer_name, "ADDRESS": customer_address, "TAX ID": customer_tax_id},
        {"NAME": seller_name or "Unknown Supplier", "ADDRESS": seller_address},
    )


def _table_noise_filter(lines: List[str]) -> List[str]:
    noise_exact = {
        "DESCRIPTION",
        "QUANTITY",
        "UNIT PRICE",
        "EXTENDED AMOUNT",
        "TAX AMOUNT",
        "DESTINATION",
        "MAIL INSTRUCTIONS",
        "CUSTOMER NO.",
        "INVOICE NO.",
        "INVOICE DATE",
        "PAGE NO.",
        "INVOICE",
        "INVOICE AMOUNT",
        "PAYMENT DUE DATE",
        "DUE DATE",
        "USD USD USD",
    }
    output: List[str] = []
    for line in lines:
        clean = _compact_space(line)
        upper = clean.upper()
        if not clean or upper in noise_exact:
            continue
        if upper.startswith(("COMMENTS", "REMIT TO:", "OR WIRE TO:", "SWIFT:", "SORT CODE:", "ACCT", "IBAN#")):
            continue
        if re.fullmatch(r"\d+\s*-\s*\d+", clean):
            continue
        output.append(clean)
    return output


def _parse_structured_column_rows(text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lines = normalize_lines(text)
    start_idx = None
    for idx, line in enumerate(lines):
        if re.search(r"\bSALES\s+ORDER\s+NO\.?\b", line, re.IGNORECASE):
            for next_idx in range(idx + 1, min(idx + 12, len(lines))):
                if re.fullmatch(r"\d{5,}", lines[next_idx]):
                    start_idx = next_idx + 1
                    break
            if start_idx is None:
                start_idx = idx + 1
            break
    if start_idx is None:
        for idx, line in enumerate(lines):
            if line.upper().startswith("DESCRIPTION"):
                start_idx = idx + 1
                break
    if start_idx is None:
        return [], {"mode": "structured_column_blocks", "rows": 0, "reason": "no_table_start"}

    stop_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if re.search(r"\b(INVOICE\s+NO\.?|CUSTOMER\s+NO\.?|REMIT\s+TO:|OR\s+WIRE\s+TO:)\b", lines[idx], re.IGNORECASE):
            stop_idx = idx
            break

    table = _table_noise_filter(lines[start_idx:stop_idx])
    qty_re = re.compile(r"^[0-9,]+(?:\.\d+)?\s+[A-Z]{1,4}$")
    unit_re = re.compile(r"^[0-9,]+(?:\.\d+)?\s+[A-Z]{3}/[A-Z]{1,4}$")
    amount_re = re.compile(r"^[0-9,]+\.\d{2}$")

    descriptions: List[str] = []
    index = 0
    while index < len(table) and not qty_re.match(table[index]):
        candidate = table[index]
        if not re.search(r"\b(total|tax|amount|date|terms|n/a)\b", candidate, re.IGNORECASE):
            descriptions.append(candidate)
        index += 1

    quantities: List[Tuple[float, str]] = []
    while index < len(table) and qty_re.match(table[index]):
        qty, uom = table[index].split()[:2]
        quantities.append((money0(qty), uom))
        index += 1

    unit_prices: List[Tuple[float, str]] = []
    while index < len(table) and unit_re.match(table[index]):
        rate, basis = table[index].split()[:2]
        unit_prices.append((money0(rate), basis))
        index += 1

    amounts: List[float] = []
    while index < len(table):
        if amount_re.match(table[index]):
            amounts.append(money0(table[index]))
        index += 1

    expected = min(len(descriptions), len(quantities), len(unit_prices))
    diag = {
        "mode": "structured_column_blocks",
        "desc_count": len(descriptions),
        "qty_count": len(quantities),
        "unit_price_count": len(unit_prices),
        "amount_count": len(amounts),
        "rows_expected": expected,
    }
    if not expected:
        return [], diag

    ext = amounts[0:expected]
    tax = amounts[expected : expected * 2]
    total = amounts[expected * 2 : expected * 3] or ext
    rows: List[Dict[str, Any]] = []
    for idx in range(expected):
        amount = total[idx] if idx < len(total) else ext[idx] if idx < len(ext) else 0.0
        rows.append(
            {
                "DESCRIPTION": descriptions[idx][:180],
                "QUANTITY": quantities[idx][0],
                "UOM": quantities[idx][1],
                "UNIT PRICE": unit_prices[idx][0],
                "PRICE BASIS": unit_prices[idx][1],
                "EXTENDED AMOUNT": ext[idx] if idx < len(ext) else amount,
                "TAX AMOUNT": tax[idx] if idx < len(tax) else 0.0,
                "AMOUNT": amount,
            }
        )
    diag["rows"] = len(rows)
    return rows, diag


def _parse_structured_vendor_invoice(
    filename: str,
    text: str,
    engine: str,
    pages: int,
    extracted_at: str,
) -> Optional[Dict[str, Any]]:
    lines = normalize_lines(text)
    rows, diag = _parse_structured_column_rows(text)
    customer_no, invoice_no, invoice_date = _structured_header_triplet(text)
    if not rows or not invoice_no:
        return None

    bill_to, seller = _structured_parties(lines)
    currency = _find_currency(text)
    line_total = round(sum(money0(row.get("AMOUNT")) for row in rows), 2)
    tax_total = round(sum(money0(row.get("TAX AMOUNT")) for row in rows), 2)
    total = _find_total(text) or line_total
    if line_total and abs(line_total - total) <= 0.5:
        total = line_total
    due_date = _next_value_after_label(lines, r"^DUE\s+DATE\b", STRUCTURED_DATE_PAT) or _find_date(text, ["Due Date"])
    sales_order = _next_value_after_label(lines, r"^SALES\s+ORDER\s+NO\.?\b", r"\d{5,}")
    po_number = _next_value_after_label(lines, r"^PO\s+NO\./CONTRACT\s+NO\.?\b", r"\S+")

    return {
        "INVOICE": {
            "DOCUMENT": {
                "DOCUMENT TYPE": "INVOICE",
                "PAGE NO.": _next_value_after_label(lines, r"^PAGE\s+NO\.?\b", r"\d+\s*-\s*\d+") or f"1 - {pages or 1}",
                "PAGES": pages,
                "EXTRACTED AT": extracted_at,
                "SOURCE FILE": filename,
                "EXTRACTION ENGINE": engine,
                "SCHEMA VERSION": "EZ-1.0",
                "PARSER": "Structured Column",
            },
            "BILL TO": bill_to,
            "SELLER": seller,
            "INVOICE HEADER": {
                "CUSTOMER NO.": customer_no,
                "INVOICE NO.": invoice_no,
                "INVOICE DATE": invoice_date,
                "DUE DATE": _normal_structured_date(due_date),
                "SALES ORDER NO.": sales_order,
                "PO NO./CONTRACT NO.": po_number or "N/A",
                "AMOUNT TO BE EFT DRAFTED": total,
                "INVOICE AMOUNT": total,
            },
            "PAYMENT": {"ELECTRONIC": {"CURRENCY": currency, "AMOUNT": float(total or 0)}},
            "CONTEXT": {},
            "LINE ITEMS": {
                "COLUMNS": ["DESCRIPTION", "QUANTITY", "UNIT PRICE", "EXTENDED AMOUNT", "TAX AMOUNT", "AMOUNT"],
                "ROWS": rows,
            },
            "USD USD USD": {"TOTAL TAX": tax_total},
            "INVOICE TAX SUMMARY": {"TOTAL TAX": tax_total},
            "REMIT TO": {},
            "OR WIRE TO": {},
            "COMMENTS": {},
            "PARSER_DIAGNOSTICS": diag,
        }
    }

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
    structured = re.search(STRUCTURED_INVNO_PAT, text, re.IGNORECASE)
    if structured:
        return structured.group(0).strip()

    value = _find_label_value(
        text,
        ["Invoice Number", "Invoice No", "Invoice #", "Inv No", "Bill Number", "Bill No"],
        r"[A-Z0-9][A-Z0-9\-\/_.]{2,40}",
    )
    if value and value.upper() not in {"INVOICE", "BILL", "INV"}:
        return value.rstrip(".")

    heading_match = re.search(
        r"\b(?:INVOICE|BILL)[\s:\/-]+(?P<number>[A-Z0-9][A-Z0-9\-\/_.]{2,40})\b",
        text,
        re.IGNORECASE,
    )
    if heading_match:
        number = heading_match.group("number").strip().rstrip(".")
        if re.search(r"\d", number) and number.upper() not in {"DATE", "NUMBER", "NO"}:
            return number

    match = re.search(r"\bINV[\-\/ ][A-Z0-9][A-Z0-9\-\/_.]{1,30}\b", text, re.IGNORECASE)
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
    skip = re.compile(r"invoice|tax invoice|bill|receipt|statement|tel:|email:|internet:|www\.|http", re.IGNORECASE)
    for line in lines[:12]:
        clean = _compact_space(line)
        if len(clean) < 3 or skip.fullmatch(clean):
            continue
        if skip.search(clean):
            continue
        if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", clean):
            continue
        return clean[:120]
    return "Unknown Supplier"


def _bill_to(text: str) -> Dict[str, Any]:
    lines = normalize_lines(text)
    for idx, line in enumerate(lines):
        if re.search(r"\b(Customer\s+Card|Customer\s+No|Customer\s+ID)\b", line, re.IGNORECASE):
            continue
        if re.search(r"\b(Bill To|Billed To|Customer Name|Buyer|Client)\b", line, re.IGNORECASE):
            collected = []
            for next_line in lines[idx + 1 : idx + 6]:
                if re.search(r"\b(Ship To|Invoice|Date|Due|Total|Description|Qty)\b", next_line, re.IGNORECASE):
                    break
                collected.append(next_line)
            if collected:
                return {"NAME": collected[0], "ADDRESS": collected[1:]}
    return {"NAME": "", "ADDRESS": []}


def _line_item_region(lines: List[str]) -> List[str]:
    start: Optional[int] = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if re.search(r"\b(description|particulars|item|service).*\b(amount|total|qty|quantity|rate|price)\b", line, re.IGNORECASE):
            start = idx + 1
            break
        if line.strip().lower() in {"description", "particulars", "item", "service"}:
            lookahead = " ".join(lines[idx : idx + 10])
            if re.search(r"\b(amount|total|qty|quantity|rate|price|unit price)\b", lookahead, re.IGNORECASE):
                start = idx + 1
                break
    if start is None:
        return []
    for idx in range(start, len(lines)):
        if re.search(r"\b(subtotal|sub total|grand total|invoice total|amount due|balance due)\b", lines[idx], re.IGNORECASE):
            end = idx
            break
    return lines[start:end]


def _line_amount_is_plausible(amount: float, invoice_total: float) -> bool:
    if amount <= 0:
        return False
    if invoice_total and amount > max(invoice_total * 1.25, invoice_total + 10):
        return False
    return True


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
        if re.search(r"\b(total|subtotal|tax|balance|amount due|invoice no|date|iban|swift|sort code|acct|email|tel:|www\.|customer card)\b", clean, re.IGNORECASE):
            continue

        structured = qty_price_amount.match(clean)
        if structured:
            desc = structured.group("desc").strip(":- ")
            amount = money0(structured.group("amount"))
            if desc and amount and _line_amount_is_plausible(amount, invoice_total):
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
        if desc and amount and _line_amount_is_plausible(amount, invoice_total):
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
    if looks_like_structured_vendor_invoice(text):
        structured_payload = _parse_structured_vendor_invoice(filename, text, engine, pages, extracted_at)
        if structured_payload:
            return structured_payload

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
