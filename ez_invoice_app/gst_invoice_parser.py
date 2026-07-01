"""GST/e-invoice parsing helpers for EZ-Invoice.

This adapter handles table-heavy Indian GST invoice PDFs that expose readable
text but need table extraction for accurate line items.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DATE_FORMATS = (
    "%d-%b-%y",
    "%d-%b-%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
)


def looks_like_gst_invoice(text: str) -> bool:
    upper = (text or "").upper()
    compact = re.sub(r"[^A-Z0-9]", "", upper)
    has_gst = any(marker in upper for marker in ("GSTIN", "GST NO", "GSTIN/UIN", "GSTIN REGN"))
    has_hsn = any(marker in upper for marker in ("HSN/SAC", "HSN CODE", "HSN"))
    has_invoice = "TAXINVOICE" in compact or "EINVOICE" in compact or "INVOICE NO" in upper
    return has_gst and has_hsn and has_invoice


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _cell_lines(value: Any) -> List[str]:
    return [line.strip() for line in str(value or "").splitlines() if line and line.strip()]


def _money(value: Any) -> float:
    raw = str(value or "").strip()
    is_negative = raw.startswith("-") or raw.startswith("(-)") or raw.startswith("(")
    cleaned = re.sub(r"[^0-9.]", "", raw)
    if cleaned in ("", "."):
        return 0.0
    try:
        amount = float(cleaned)
    except ValueError:
        return 0.0
    return -amount if is_negative else amount


def _amount_tokens(value: Any) -> List[str]:
    return re.findall(r"(?:₹|Rs\.?)?\s*-?\s*\d[\d,]*(?:\.\d{2,3})?", str(value or ""), re.IGNORECASE)


def _money_values(value: Any) -> List[float]:
    values = []
    for match in re.finditer(r"(?:\(-?\)?|-)?\d[\d,]*\.\d{2}", str(value or "")):
        values.append(_money(match.group(0)))
    return values


def _normal_date(value: str) -> str:
    value = _compact(value).replace(",", "")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%d-%b-%Y").upper()
        except ValueError:
            continue
    return value.upper()


def _first_date(value: str) -> str:
    match = re.search(
        r"\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}",
        value or "",
        re.IGNORECASE,
    )
    if not match:
        return ""
    raw = match.group(0)
    normalized = _normal_date(raw)
    return normalized if normalized != raw.upper() else ""


def _split_text(text: str) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, str, int]:
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return "\n".join(page.get_text("text") or "" for page in doc), "pymupdf", doc.page_count
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages), "pypdf", len(reader.pages)
    except Exception:
        return "", "none", 0


def _all_table_cells(pdf_bytes: bytes) -> Tuple[List[List[List[Any]]], str]:
    try:
        import pdfplumber
    except Exception as exc:
        return [], "pdfplumber unavailable: " + str(exc)

    try:
        tables = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables() or [])
        return tables, ""
    except Exception as exc:
        return [], "pdfplumber failed: " + str(exc)


def _table_text(tables: List[List[List[Any]]]) -> str:
    pieces: List[str] = []
    for table in tables:
        for row in table:
            for cell in row or []:
                if cell:
                    pieces.append(str(cell))
    return "\n".join(pieces)


def _seller_name(text: str, lines: List[str]) -> str:
    skip = re.compile(
        r"^(?:ORIGINAL|DUPLICATE|TRIPLICATE|EXTRA COPY|SUBJECT TO|TAX\s*INVOICE|TA\s*X|IRN|ACK|ACK DATE|E-INVOICE|PAN\s*:|GSTIN|CIN\b|:?\s*[a-f0-9-]{20,})",
        re.IGNORECASE,
    )
    for line in lines[:12]:
        clean = _compact(line)
        if clean.startswith(":") or re.fullmatch(r"[:\s-]*[a-f0-9-]{12,}", clean, re.IGNORECASE):
            continue
        if (
            not clean
            or skip.search(clean)
            or _first_date(clean)
            or re.search(r"AUTHORISED|TEL:|EMAIL:|PH\s*:", clean, re.IGNORECASE)
        ):
            continue
        if len(clean) > 2:
            return clean[:120]
    for line in lines[:30]:
        clean = _compact(line)
        if clean and not skip.search(clean) and re.search(r"(LIMITED|PRIVATE|ENTERPRISE|CHEMICAL|MILLS|PVT|LLP|LTD)", clean, re.IGNORECASE):
            return clean[:120]
    return "Unknown Supplier"


def _party_lines(block: str) -> List[str]:
    lines = []
    skip = re.compile(
        r"^(?:Recipient|Customer Details:?|Buyer \(Bill to\)|Billed To|NAME & ADDRESS|GSTIN|GST NO|PAN NO|PAN:|STATE|PLACE|COUNTRY|Billing Address:?)",
        re.IGNORECASE,
    )
    for line in _cell_lines(block):
        clean = _compact(line)
        if not clean or skip.search(clean) or re.fullmatch(r"\d{3,}", clean):
            continue
        lines.append(clean)
    return lines


def _party_from_block(block: str, label: str) -> Dict[str, Any]:
    block_lines = _cell_lines(block)
    start = -1
    for idx, line in enumerate(block_lines):
        if label.lower() in line.lower():
            start = idx
            break
    if start == -1:
        return {"NAME": "", "ADDRESS": []}

    first = re.sub(rf"^{re.escape(label)}\s*:?\s*", "", block_lines[start], flags=re.IGNORECASE).strip()
    collected = [first] if first else []
    for line in block_lines[start + 1 :]:
        if re.search(r"GSTIN|P\.A\.NO|TEL NO|STATE\s*:", line, re.IGNORECASE):
            break
        collected.append(line)
    return {"NAME": collected[0] if collected else "", "ADDRESS": collected[1:]}


def _bill_to(text: str, tables: List[List[List[Any]]]) -> Dict[str, Any]:
    joined = _table_text(tables) or text
    block_patterns = [
        r"NAME\s*&\s*ADDRESS\s+OF\s+RECIPIENT\s+\(BILLED\s+TO\)\s*(.*?)(?:NAME\s*&\s*ADDRESS\s+OF\s+DELIVERY|Challan No\.|PAN\s*:)",
        r"Customer Details:\s*(.*?)(?:Invoice\s*#:|Place of Supply:|Shipping Address:)",
        r"Recipient\s*(.*?)(?:STATE OF SUPPLY|Consignee)",
        r"Buyer\s+\(Bill to\)\s*(.*?)(?:Invoice No\.|GSTIN/UIN|Place of Supply)",
    ]
    for pattern in block_patterns:
        match = re.search(pattern, joined, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        collected = _party_lines(match.group(1))
        if collected:
            return {"NAME": collected[0], "ADDRESS": collected[1:]}

    for label in ("NAME & ADDRESS OF RECIPIENT (BILLED TO)", "Buyer (Bill to)", "Billed To", "Customer Details"):
        party = _party_from_block(joined, label)
        if party.get("NAME"):
            return party

    lines = _split_text(text)
    for idx, line in enumerate(lines):
        if re.search(r"Buyer \(Bill to\)|Billed To", line, re.IGNORECASE):
            collected = []
            value = re.sub(r"^.*?Billed To\s*:?\s*", "", line, flags=re.IGNORECASE).strip()
            if value and value != line:
                collected.append(value)
            for next_line in lines[idx + 1 : idx + 8]:
                if re.search(r"GSTIN|State Name|Tel No|Original for Recipient", next_line, re.IGNORECASE):
                    break
                collected.append(next_line)
            if collected:
                return {"NAME": collected[0], "ADDRESS": collected[1:]}
    return {"NAME": "", "ADDRESS": []}


def _invoice_no(joined_text: str, lines: List[str]) -> str:
    for pattern in (
        r"\bINVOICE\s+NO\.?\s*:?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        r"\bINVOICE\s*#\s*:?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        r"\bTAX\s+INVOICE\s+NO\.?\s*:?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        r"Tax Inv\. No\.\s*:?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        r"Invoice No\.\s*(?:e-Way Bill No\.)?\s*([A-Z]/\d{2}-\d{2}/\d{3,})",
        r"Invoice No\.\s*e-Way Bill No\.\s*([A-Z0-9/-]{3,})",
    ):
        match = re.search(pattern, joined_text, re.IGNORECASE)
        if match and match.group(1).strip().upper() not in {"DATE", "NO", "E-WAY"}:
            return match.group(1).strip()

    for idx, line in enumerate(lines):
        if re.fullmatch(r"Invoice No\.?|Tax Inv\. No\.?|Tax Invoice No|Invoice #:", line, re.IGNORECASE):
            for candidate in lines[idx + 1 : idx + 10]:
                if re.search(r"date|e-way|bill|no\\.", candidate, re.IGNORECASE):
                    continue
                if re.fullmatch(r"[A-Z]/\d{2}-\d{2}/\d{3,}", candidate):
                    return candidate
                if re.fullmatch(r"[A-Z0-9][A-Z0-9/-]{2,}", candidate):
                    return candidate
    return ""


def _invoice_dates(joined_text: str, lines: List[str], invoice_no: str) -> Tuple[str, str]:
    date = ""
    due = ""
    date_patterns = [
        r"\bDATE\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        r"\bAR\s+Invoice\s+Date\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        r"\bInvoice\s+Date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})",
        r"\bDated\s*:?\s*([0-9]{1,2}[-/][A-Za-z]{3,9}[-/][0-9]{2,4})",
        r"Tax Inv\. No\.\s*:?\s*[A-Z0-9/-]+\s+Date\s*:?\s*([0-9./-]+)",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, joined_text, re.IGNORECASE)
        if match:
            date = _normal_date(match.group(1))
            break
    due_patterns = [
        r"\bDue\s+Date\s*:?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})",
        r"\bDue\s+On\s*:?\s*([0-9./-]+)",
    ]
    for pattern in due_patterns:
        match = re.search(pattern, joined_text, re.IGNORECASE)
        if match:
            due = _normal_date(match.group(1))
            break

    if not date and invoice_no:
        for idx, line in enumerate(lines):
            if invoice_no in line:
                scan = lines[idx : idx + 35]
                for pos, candidate in enumerate(scan):
                    if "dt." in candidate.lower():
                        date_part = re.split(r"dt\.", candidate, flags=re.IGNORECASE, maxsplit=1)[-1]
                        date = _first_date(date_part)
                        break
                    if candidate.lower() == "dated" and pos + 1 < len(scan):
                        date = _first_date(scan[pos + 1])
                        break
                if date:
                    break

    if not date:
        for idx, line in enumerate(lines):
            if line.lower() == "dated" and idx + 1 < len(lines):
                date = _first_date(lines[idx + 1])
                if date:
                    break

    return date, due or date


def _po_number(joined_text: str, lines: List[str]) -> str:
    for pattern in (
        r"Buyer.?s Order No\.\s*([A-Z0-9/.-]{3,})",
        r"Order No\.\s*:?\s*([A-Z0-9 /.-]{3,})",
    ):
        match = re.search(pattern, joined_text, re.IGNORECASE)
        if match:
            return _compact(match.group(1))
    for idx, line in enumerate(lines):
        if re.search(r"Buyer.?s Order No\.|Order No\.", line, re.IGNORECASE):
            for candidate in lines[idx + 1 : idx + 5]:
                if not re.search(r"Date|Dispatch|Payment", candidate, re.IGNORECASE):
                    return _compact(candidate)
    return "N/A"


def _gross_total(lines: List[str], joined_text: str) -> float:
    candidates: List[float] = []
    label_patterns = [
        r"TOTAL\s+INVOICE\s+VALUE(?!\s*\(IN WORDS\))(?!\s+IN WORDS)",
        r"TOTAL\s+VALUE\s*:",
        r"AMOUNT\s+PAYABLE\s*:",
        r"TOTAL\s+INV\s+AMT\s*:",
    ]
    for pattern in label_patterns:
        for match in re.finditer(pattern, joined_text, re.IGNORECASE):
            snippet = joined_text[match.start() : match.start() + 220]
            if re.match(r"TOTAL\s+VALUE\s*\(RS\)", snippet, re.IGNORECASE):
                continue
            values = [value for value in _money_values(snippet) if abs(value) > 100]
            if values:
                candidates.append(max(values))
    if candidates:
        return candidates[-1]
    match = re.search(r"TOTAL\s+(?:₹|Rs\.?)\s*(-?\s*\d[\d,]*\.\d{2})", joined_text, re.IGNORECASE)
    if match:
        return _money(match.group(1))

    for idx, line in enumerate(lines):
        if line.lower() == "gross amount" and idx + 1 < len(lines):
            amount = _money(lines[idx + 1])
            if amount:
                return amount
        if re.fullmatch(r"Total|TOTAL INVOICE VALUE|Total Value|Amount Payable:?", line, re.IGNORECASE):
            for candidate in lines[idx + 1 : idx + 5]:
                amount = _money(candidate)
                if amount:
                    return amount
        if line.lower() == "total":
            lookahead = lines[idx + 1 : idx + 5]
            if any("amount chargeable" in item.lower() for item in lookahead):
                for candidate in lookahead:
                    amount = _money(candidate)
                    if amount:
                        return amount

    match = re.search(r"Gross Amount\s+(-?\d[\d,]*\.\d{2})", joined_text, re.IGNORECASE)
    if match:
        return _money(match.group(1))
    return 0.0


def _taxable_base(joined_text: str) -> float:
    match = re.search(r"(?:CGST|SGST|IGST)\s*@.*?on\s+Rs\.?\s*([\d,]+\.\d{2})", joined_text, re.IGNORECASE)
    if match:
        return _money(match.group(1))
    idx = re.search(r"Taxable\s+(?:Value|Amount)", joined_text, re.IGNORECASE)
    if idx:
        values = [value for value in _money_values(joined_text[idx.start() : idx.start() + 180]) if abs(value) > 100]
        if values:
            return values[0]
    return 0.0


def _tax_total_from_text(joined_text: str) -> float:
    patterns = [
        r"Total\s+GST\s*:?\s*(?:₹|Rs\.?)?\s*([\d,]+\.\d{2})",
        r"(?:CGST|SGST|IGST)\s*(?:Payable|@|9\.0%|18\.00%)?[^\d₹R]{0,20}(?:₹|Rs\.?)?\s*([\d,]+\.\d{2})",
    ]
    if re.search(r"Total\s+GST", joined_text, re.IGNORECASE):
        match = re.search(patterns[0], joined_text, re.IGNORECASE)
        if match:
            return _money(match.group(1))
    total = 0.0
    for match in re.finditer(patterns[1], joined_text, re.IGNORECASE):
        amount = _money(match.group(1))
        if amount:
            total += amount
    return round(total, 2)


def _tax_total_from_lines(lines: List[str]) -> float:
    total = 0.0
    for idx, line in enumerate(lines):
        if not re.search(r"\b(?:IGST|CGST|SGST)\b", line, re.IGNORECASE):
            continue
        if re.search(r"GSTIN|GST/UIN|GST\s*No", line, re.IGNORECASE):
            continue
        if not ("@" in line or "%" in line or re.search(r"\b(?:tax|amount|payable)\b", line, re.IGNORECASE)):
            continue
        if re.search(r"\b(?:Act|Rules?|Section)\b", line, re.IGNORECASE) and "@" not in line and "%" not in line:
            continue

        amount = 0.0
        if "%" not in line:
            values = _money_values(line)
            if values:
                amount = values[-1]
        if not amount:
            for candidate in lines[idx + 1 : idx + 4]:
                if re.search(r"^\s*-", candidate):
                    amount = _money(candidate)
                    if amount:
                        break
                values = _money_values(candidate)
                if values:
                    amount = values[0]
                    break
        if amount:
            total += amount
    return round(total, 2)


def _amount_after_label(lines: List[str], label_pattern: str) -> float:
    for idx, line in enumerate(lines):
        if not re.search(label_pattern, line, re.IGNORECASE):
            continue
        for candidate in lines[idx + 1 : idx + 4]:
            if re.search(r"^\s*-", candidate):
                amount = _money(candidate)
                if amount:
                    return amount
            values = _money_values(candidate)
            if values:
                return values[0]
            amount = _money(candidate)
            if amount:
                return amount
    return 0.0


def _tax_summary_from_tables(tables: List[List[List[Any]]]) -> Tuple[float, float]:
    for table in tables:
        for row in table or []:
            row_text = " ".join(_compact(cell) for cell in row or [])
            if not row or not str(row[0] or "").strip().lower().startswith("total"):
                continue
            if not re.search(r"GST|CGST|SGST|IGST|Taxable", row_text, re.IGNORECASE):
                continue
            values = [_money(cell) for cell in row]
            values = [value for value in values if value]
            if len(row) >= 13 and _money(row[6]) and (_money(row[10]) or _money(row[12])):
                return _money(row[6]), _money(row[12]) or _money(row[10])
            if len(values) >= 3:
                return values[0], values[-1]
    return 0.0, 0.0


def _numeric_lines(value: Any) -> List[float]:
    return [_money(line) for line in _cell_lines(value) if _money(line) or re.search(r"\d", line)]


def _quantity_lines(value: Any) -> List[Tuple[float, str]]:
    parsed = []
    for line in _cell_lines(value):
        match = re.search(r"([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)?", line)
        if not match:
            continue
        parsed.append((_money(match.group(1)), (match.group(2) or "").upper()))
    return parsed


def _serials(value: Any) -> List[str]:
    return [line for line in _cell_lines(value) if re.fullmatch(r"\d+", line)]


def _is_total_line(line: str) -> bool:
    return bool(re.search(r"T\s*O\s*T\s*A\s*L|NET AMOUNT|LESS:|CGST|SGST|IGST|ROUND OFF|GROSS AMOUNT", line, re.IGNORECASE))


def _descriptions(desc_cell: Any, hsn_values: List[str], expected: int) -> List[str]:
    lines = _cell_lines(desc_cell)
    filtered = [line for line in lines if not _is_total_line(line)]
    if len(filtered) == expected:
        return filtered

    starts: List[int] = []
    for idx, line in enumerate(lines):
        if any(re.match(rf"^{re.escape(hsn)}(?:\b|\s)", line) for hsn in hsn_values):
            starts.append(idx)

    descriptions: List[str] = []
    if starts:
        for item_idx, start in enumerate(starts[:expected]):
            end = starts[item_idx + 1] if item_idx + 1 < len(starts) else len(lines)
            chunk = []
            for line in lines[start + 1 : end]:
                if _is_total_line(line):
                    continue
                if any(re.fullmatch(rf"{re.escape(hsn)}(?:\s+[A-Z]+)?", line) for hsn in hsn_values):
                    continue
                chunk.append(line)
            descriptions.append(_compact(" ".join(chunk)))
        if len(descriptions) == expected:
            return descriptions

    return [_compact(line) for line in filtered[:expected]]


def _align_amounts(amounts: List[float], expected: int, desc_cell: Any) -> List[float]:
    if len(amounts) <= expected:
        return amounts
    desc = "\n".join(_cell_lines(desc_cell)).upper()
    if "B/F" in desc:
        return amounts[-expected:]
    return amounts[:expected]


def _header_idx(row: List[Any], *patterns: str) -> int:
    for idx, cell in enumerate(row or []):
        text = _compact(cell).lower()
        if all(pattern.lower() in text for pattern in patterns):
            return idx
    return -1


def _first_header_idx(row: List[Any], pattern_options: List[Tuple[str, ...]]) -> int:
    for patterns in pattern_options:
        idx = _header_idx(row, *patterns)
        if idx != -1:
            return idx
    return -1


def _parse_qty_uom(value: Any, default_uom: str = "") -> Tuple[float, str]:
    text = _compact(value)
    qty = _money(text)
    match = re.search(r"\b(KGS?|KG|NOS?|PCS?|MT|LTR|LITRE|LITER|EA|MTR|METER)\b", text, re.IGNORECASE)
    uom = (match.group(1).upper() if match else default_uom).replace("KGS", "KG")
    return qty, uom or "EA"


def _uom_from_header(value: Any) -> str:
    text = _compact(value).upper()
    match = re.search(r"\((KG|KGS|NOS?|PCS?|MT|LTR|LITRE|LITER|EA|MTR|METER)\)|\bPER\s+(KG|KGS|NOS?|PCS?|MT|LTR|LITRE|LITER|EA|MTR|METER)\b", text)
    if not match:
        return ""
    uom = next(group for group in match.groups() if group)
    return uom.replace("KGS", "KG")


def _cell_money(value: Any) -> float:
    values = _money_values(value)
    if values:
        return values[-1]
    return _money(value)


def _split_hsn_description(value: Any) -> Tuple[str, str]:
    text = _compact(value)
    match = re.match(r"^(\d{4,8})\s+(.+)$", text)
    if match:
        return match.group(1), _compact(match.group(2))
    hsn_match = re.search(r"\b(\d{4,8})\b", text)
    hsn = hsn_match.group(1) if hsn_match else ""
    desc = re.sub(r"\b\d{4,8}\b", "", text, count=1).strip(" :-")
    return hsn, desc


def _extract_rows_header_aware(tables: List[List[List[Any]]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for table in tables:
        header_idx = -1
        header: List[Any] = []
        for idx, row in enumerate(table or []):
            row_text = " ".join(_compact(cell) for cell in row or []).lower()
            if ("description" in row_text or "goods" in row_text or "item" in row_text) and (
                "amount" in row_text or "value" in row_text
            ):
                header_idx = idx
                header = row or []
                break
        if header_idx == -1:
            continue

        combined_idx = _first_header_idx(header, [("hsn", "description"), ("hsn/sac",)])
        desc_idx = _first_header_idx(header, [("description",), ("goods",), ("item",)])
        hsn_idx = _first_header_idx(header, [("hsn/sac",), ("hsn code",), ("hsn",)])
        qty_idx = _first_header_idx(header, [("quantity",), ("qty",), ("commercial mass",)])
        rate_idx = _first_header_idx(header, [("rate",), ("price",)])
        taxable_idx = _first_header_idx(header, [("taxable",), ("total value",)])
        tax_idx = _first_header_idx(header, [("tax amount",)])
        amount_idx = -1
        for idx, cell in enumerate(header or []):
            text = _compact(cell).lower()
            if ("amount" in text or "value" in text) and "tax amount" not in text and "taxable" not in text:
                amount_idx = idx
        if amount_idx == -1:
            amount_idx = taxable_idx

        default_uom = _uom_from_header(header[qty_idx]) if qty_idx != -1 and qty_idx < len(header) else ""
        if not default_uom and rate_idx != -1 and rate_idx < len(header):
            default_uom = _uom_from_header(header[rate_idx])

        for row in (table or [])[header_idx + 1:]:
            cells = list(row or [])
            row_text = " ".join(_compact(cell) for cell in cells)
            row_upper = row_text.upper()
            if not row_text or row_upper.startswith("TOTAL") or re.search(r"\b(TAXABLE VALUE|TOTAL INVOICE|AMOUNT PAYABLE|ROUNDING|CGST|SGST|IGST)\b", row_upper):
                continue

            desc = ""
            hsn = ""
            if combined_idx != -1 and combined_idx < len(cells):
                hsn, desc = _split_hsn_description(cells[combined_idx])
            if hsn_idx != -1 and hsn_idx < len(cells):
                hsn = re.sub(r"\D", "", _compact(cells[hsn_idx]))[:8] or hsn
            if desc_idx != -1 and desc_idx != combined_idx and desc_idx < len(cells):
                candidate = _compact(cells[desc_idx])
                if candidate and not re.fullmatch(r"\d{4,8}", candidate):
                    desc = candidate

            if not desc:
                text_cells = [
                    _compact(cell)
                    for idx, cell in enumerate(cells)
                    if idx not in {hsn_idx, qty_idx, rate_idx, taxable_idx, tax_idx, amount_idx}
                    and re.search(r"[A-Za-z]", _compact(cell))
                ]
                desc = text_cells[0] if text_cells else ""

            if not hsn:
                hsn_match = re.search(r"\b(\d{4,8})\b", row_text)
                hsn = hsn_match.group(1) if hsn_match else ""

            if not desc or _is_total_line(desc):
                continue

            qty = 0.0
            uom = default_uom
            if qty_idx != -1 and qty_idx < len(cells):
                qty, uom = _parse_qty_uom(cells[qty_idx], default_uom=default_uom)
            if not qty:
                for idx, cell in enumerate(cells):
                    if idx in {hsn_idx, rate_idx, taxable_idx, tax_idx, amount_idx}:
                        continue
                    text = _compact(cell)
                    if re.search(r"\b(KGS?|KG|NOS?|PCS?|MT|LTR|EA)\b", text, re.IGNORECASE):
                        qty, uom = _parse_qty_uom(text, default_uom=default_uom)
                        break
            qty = qty or 1.0

            taxable_amount = _cell_money(cells[taxable_idx]) if taxable_idx != -1 and taxable_idx < len(cells) else 0.0
            tax_amount = _cell_money(cells[tax_idx]) if tax_idx != -1 and tax_idx < len(cells) else 0.0
            amount = _cell_money(cells[amount_idx]) if amount_idx != -1 and amount_idx < len(cells) else 0.0
            extended = taxable_amount or amount
            gross = amount if tax_amount and taxable_amount else extended + tax_amount
            if not extended:
                continue

            unit_price = _cell_money(cells[rate_idx]) if rate_idx != -1 and rate_idx < len(cells) else 0.0
            if not unit_price and qty:
                unit_price = round(extended / qty, 4)

            items.append(
                {
                    "DESCRIPTION": desc[:220],
                    "HSN/SAC": hsn,
                    "QUANTITY": qty,
                    "UOM": uom or "EA",
                    "UNIT PRICE": unit_price,
                    "PRICE BASIS": "",
                    "EXTENDED AMOUNT": round(extended, 2),
                    "TAX AMOUNT": round(tax_amount, 2),
                    "AMOUNT": round(gross, 2),
                }
            )
    return items


def _extract_rows_from_tables(tables: List[List[List[Any]]]) -> List[Dict[str, Any]]:
    header_rows = _extract_rows_header_aware(tables)
    if header_rows:
        return header_rows

    items: List[Dict[str, Any]] = []
    for table in tables:
        for row in table or []:
            if not row or len(row) < 9:
                continue
            serials = _serials(row[0])
            if not serials:
                continue

            desc_idx = 1
            hsn_idx = 2
            if len(row) >= 13:
                qty_idx = 4
                rate_idx = 7
                per_idx = 9
                amount_idx = 11
            else:
                qty_idx = 3
                rate_idx = 5
                per_idx = 6
                amount_idx = 7 if len(row) >= 11 else 8

            expected = len(serials)
            hsn_values = [re.sub(r"\D", "", line) for line in _cell_lines(row[hsn_idx]) if re.search(r"\d", line)]
            hsn_values = hsn_values[:expected]
            quantities = _quantity_lines(row[qty_idx])[:expected]
            rates = _numeric_lines(row[rate_idx])[:expected]
            per_values = _cell_lines(row[per_idx])[:expected]
            amounts = _align_amounts(_money_values(row[amount_idx]), expected, row[desc_idx])
            descriptions = _descriptions(row[desc_idx], hsn_values, expected)

            if not (descriptions and amounts):
                continue

            for idx in range(min(expected, len(descriptions), len(amounts))):
                quantity, qty_uom = quantities[idx] if idx < len(quantities) else (1.0, "")
                unit_price = rates[idx] if idx < len(rates) else (amounts[idx] / quantity if quantity else amounts[idx])
                uom = qty_uom or (per_values[idx].upper() if idx < len(per_values) else "EA")
                desc = descriptions[idx] or "Invoice item"
                item = {
                    "DESCRIPTION": desc[:220],
                    "HSN/SAC": hsn_values[idx] if idx < len(hsn_values) else "",
                    "QUANTITY": quantity or 1.0,
                    "UOM": uom or "EA",
                    "UNIT PRICE": unit_price,
                    "PRICE BASIS": "",
                    "EXTENDED AMOUNT": amounts[idx],
                    "TAX AMOUNT": 0.0,
                    "AMOUNT": amounts[idx],
                }
                items.append(item)
    return items


def _allocate_tax(
    rows: List[Dict[str, Any]],
    gross_total: float,
    taxable_total: float,
    tax_total_override: float = 0.0,
) -> None:
    if not rows:
        return
    current_taxable = sum(_money(row.get("EXTENDED AMOUNT")) for row in rows)
    if taxable_total and current_taxable and taxable_total < current_taxable - 0.50:
        ratio = taxable_total / current_taxable
        for row in rows:
            original = _money(row.get("EXTENDED AMOUNT"))
            adjusted = round(original * ratio, 2)
            row["ORIGINAL AMOUNT"] = original
            row["DISCOUNT AMOUNT"] = round(original - adjusted, 2)
            row["EXTENDED AMOUNT"] = adjusted
            row["UNIT PRICE"] = round(adjusted / (row.get("QUANTITY") or 1.0), 4)

    net_total = sum(_money(row.get("EXTENDED AMOUNT")) for row in rows)
    tax_total = round(tax_total_override if tax_total_override else max(0.0, gross_total - net_total), 2)
    if not tax_total or not net_total:
        return

    allocated = 0.0
    for idx, row in enumerate(rows):
        if idx == len(rows) - 1:
            tax = round(tax_total - allocated, 2)
        else:
            tax = round(tax_total * (_money(row.get("EXTENDED AMOUNT")) / net_total), 2)
            allocated += tax
        row["TAX AMOUNT"] = tax
        row["AMOUNT"] = round(_money(row.get("EXTENDED AMOUNT")) + tax, 2)


def parse_gst_invoice(
    filename: str,
    pdf_bytes: bytes,
    text: Optional[str] = None,
    engine: str = "",
    pages: int = 0,
    extracted_at: str = "",
) -> Optional[Dict[str, Any]]:
    if text is None:
        text, engine, pages = _extract_pdf_text(pdf_bytes)
    if not looks_like_gst_invoice(text or ""):
        return None

    tables, table_warning = _all_table_cells(pdf_bytes)
    joined = _table_text(tables) or text or ""
    lines = _split_text(text or "")
    seller = _seller_name(text or "", lines)
    bill_to = _bill_to(text or "", tables)
    inv_no = _invoice_no(joined, lines) or Path(filename).stem
    inv_date, due_date = _invoice_dates(joined, lines, inv_no)
    po_no = _po_number(joined, lines)
    gross = _gross_total(lines, joined)
    rows = _extract_rows_from_tables(tables)
    summary_taxable, summary_tax = _tax_summary_from_tables(tables)
    explicit_gst_tax = _tax_total_from_lines(lines) or _tax_total_from_text(joined)
    tcs_total = _amount_after_label(lines, r"\bTCS\b")
    round_off = _amount_after_label(lines, r"Rounding\s+Off|Round\s*Off|Rounding")
    taxable = _taxable_base(joined) or summary_taxable or sum(_money(row.get("EXTENDED AMOUNT")) for row in rows)
    if not gross:
        gross = taxable + (explicit_gst_tax or summary_tax) + tcs_total + round_off if (explicit_gst_tax or summary_tax or tcs_total or round_off) else taxable
    _allocate_tax(rows, gross, taxable, tax_total_override=explicit_gst_tax or summary_tax)

    net_total = round(sum(_money(row.get("EXTENDED AMOUNT")) for row in rows), 2)
    tax_total = round((explicit_gst_tax or summary_tax or sum(_money(row.get("TAX AMOUNT")) for row in rows)), 2)
    diagnostics = {
        "parser": "gst_einvoice_adapter",
        "table_warning": table_warning,
        "line_count": len(rows),
        "taxable_total": net_total,
        "tax_total": tax_total,
        "tcs_total": tcs_total,
        "round_off": round_off,
        "gross_total": gross,
    }

    return {
        "INVOICE": {
            "DOCUMENT": {
                "DOCUMENT TYPE": "INVOICE",
                "PAGE NO.": "1 - " + str(pages or 1),
                "PAGES": pages,
                "EXTRACTED AT": extracted_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "SOURCE FILE": filename,
                "EXTRACTION ENGINE": engine or "pdfplumber+pymupdf",
                "SCHEMA VERSION": "EZ-GST-1.0",
                "PARSER": "GST/e-Invoice Adapter",
            },
            "BILL TO": bill_to,
            "SELLER": {"NAME": seller, "ADDRESS": []},
            "INVOICE HEADER": {
                "CUSTOMER NO.": "",
                "INVOICE NO.": inv_no,
                "INVOICE DATE": inv_date,
                "DUE DATE": due_date or inv_date,
                "SALES ORDER NO.": "",
                "PO NO./CONTRACT NO.": po_no or "N/A",
                "AMOUNT TO BE EFT DRAFTED": gross,
                "INVOICE AMOUNT": gross,
            },
            "PAYMENT": {"ELECTRONIC": {"CURRENCY": "INR", "AMOUNT": float(gross or 0)}},
            "CONTEXT": {},
            "LINE ITEMS": {
                "COLUMNS": [
                    "DESCRIPTION",
                    "HSN/SAC",
                    "QUANTITY",
                    "UOM",
                    "UNIT PRICE",
                    "EXTENDED AMOUNT",
                    "TAX AMOUNT",
                    "AMOUNT",
                ],
                "ROWS": rows,
            },
            "INVOICE TAX SUMMARY": {
                "TOTAL TAX": tax_total,
                "TAXABLE VALUE": net_total,
                "TCS": tcs_total,
                "ROUND OFF": round_off,
            },
            "INR INR INR": {"TOTAL TAX": tax_total, "TAXABLE VALUE": net_total, "TCS": tcs_total, "ROUND OFF": round_off},
            "USD USD USD": {"TOTAL TAX": tax_total, "TAXABLE VALUE": net_total, "TCS": tcs_total, "ROUND OFF": round_off},
            "REMIT TO": {},
            "OR WIRE TO": {},
            "COMMENTS": {},
            "PARSER_DIAGNOSTICS": diagnostics,
        }
    }
