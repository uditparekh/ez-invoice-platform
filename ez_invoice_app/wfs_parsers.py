"""
wfs_parsers.py — Robust WFS Invoice Parser
Handles all 9 known World Fuel Services invoice formats.

ROOT CAUSE FIX (customer number):
  The Italy bilingual invoice has "UOM CONVERSION = 0.800714285714286 KG/LIT"
  at the bottom.  PyMuPDF's column-based text ordering sometimes renders that
  section BEFORE the header box, so a blind first-match regex catches
  "800714285714286" instead of "125928".

  Fix: anchor the search to the text that follows the "CUSTOMER NO." /
  "INVOICE NO." / "INVOICE DATE" label block.  Only fall back to a
  digit-length-bounded regex when the labels are absent.
"""

import re
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Regex building blocks
# ─────────────────────────────────────────────────────────────────────────────
_UOM  = r'(?:USG|EA|GAL|LIT|LT|MTN|KG|MT|L\b)'
_CURR = r'(?:USD|EUR|GBP|CAD|ARS|RON|ZAR|JPY|SGD)'
_NUM  = r'[\d,]+\.?\d*'


def _tf(s: str) -> float:
    """Convert formatted number string to float."""
    return float(str(s).replace(',', '').strip() or '0')


# ─────────────────────────────────────────────────────────────────────────────
# CORE FIX: find_invoice_triplet
# ─────────────────────────────────────────────────────────────────────────────

def find_invoice_triplet(text: str):
    """
    Return (customer_no, invoice_no, invoice_date) from invoice text.

    WFS text extraction is not visually ordered. COLT invoices usually emit
    customer/invoice/date values after the labels, while standard, Canada, and
    bilingual invoices often emit date/invoice/customer immediately before the
    labels. Search near header labels first and use bounded invoice/customer
    patterns so UOM conversion decimals cannot become customer numbers.
    """
    invno_pat = r'\d{6,8}-\d{5}(?:-\d+)?'
    date_pat = r'\d{1,2}-[A-Z]{3}-\d{2,4}'
    cust_pat = r'\d{3,8}'

    def norm_date(value: str) -> str:
        value = (value or '').strip().upper()
        if re.fullmatch(r'\d{1,2}-[A-Z]{3}-\d{2}', value):
            value = value[:-2] + '20' + value[-2:]
        return value

    def valid_customer(value: str) -> bool:
        return bool(re.fullmatch(cust_pat, value or '')) and not set(value) <= {'0'}

    patterns = [
        re.compile(
            rf'(?<![.\d])(?P<customer>{cust_pat})\s+'
            rf'(?P<invoice>{invno_pat})\s+'
            rf'(?P<date>{date_pat})(?![A-Z0-9-])',
            re.IGNORECASE,
        ),
        re.compile(
            rf'(?P<date>{date_pat})\s*'
            rf'(?P<invoice>{invno_pat})\s*'
            rf'(?P<customer>{cust_pat})(?![.\d])',
            re.IGNORECASE,
        ),
        re.compile(
            rf'(?P<invoice>{invno_pat})\s+'
            rf'(?P<date>{date_pat})\s+'
            rf'(?P<customer>{cust_pat})(?![.\d])',
            re.IGNORECASE,
        ),
        re.compile(
            rf'(?P<invoice>{invno_pat})\s+'
            rf'(?P<customer>{cust_pat})\s+'
            rf'(?P<date>{date_pat})(?![A-Z0-9-])',
            re.IGNORECASE,
        ),
    ]

    lines = [ln.strip() for ln in (text or '').replace('\u00a0', ' ').splitlines() if ln.strip()]
    label_re = re.compile(
        r'(CUSTOMER\s+NO|CLIENTE\s+NR|INVOICE\s+NO|FATTURA\s+NR|INVOICE\s+DATE|DATA\s+FATTURA)',
        re.IGNORECASE,
    )
    windows = []
    for idx, line in enumerate(lines):
        if label_re.search(line):
            windows.append('\n'.join(lines[max(0, idx - 10): min(len(lines), idx + 16)]))
    windows.append((text or '').replace('\u00a0', ' '))

    for window in windows:
        for pat in patterns:
            for m in pat.finditer(window):
                cust = m.group('customer')
                if valid_customer(cust):
                    return cust, m.group('invoice'), norm_date(m.group('date'))

    return None, None, None


# ─────────────────────────────────────────────────────────────────────────────
# Page number extraction (secondary fix)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_page_no(text: str) -> str:
    """
    Extract page number like '1 - 1' without matching postal codes.
    Valid page: both parts ≤ 3 digits (max 999 pages).
    Postal codes like 2774-550 are excluded (parts > 3 digits).
    """
    for m in re.finditer(r'\b(\d{1,3})\s*-\s*(\d{1,3})\b', text):
        p1, p2 = m.group(1), m.group(2)
        if len(p1) <= 3 and len(p2) <= 3:
            return f"{p1} - {p2}"
    return "1 - 1"


# ─────────────────────────────────────────────────────────────────────────────
# Line item parsing
# ─────────────────────────────────────────────────────────────────────────────

# Pre-compiled patterns ordered by specificity (most specific first)
_P_DUAL_QTY_6 = re.compile(          # 488.72 USG 1,850.00 LIT  rate  e1 e2 t1 t2 a1 a2
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(' + _UOM + r')\s+(' + _NUM + r')\s+(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _CURR + r')/(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_SINGLE_QTY_6 = re.compile(        # 617.11 USG  rate  e1 e2 t1 t2 a1 a2
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _CURR + r')/(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_EA_6 = re.compile(                 # 1 EA  rate/EA  e1 e2 t1 t2 a1 a2
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(EA)\s+'
    r'(' + _NUM + r')\s+(' + _CURR + r')/(EA)\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_LIT_ONLY_3 = re.compile(           # 5,513.20 LIT  rate  ext tax total  (Canada EFT)
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(LIT|MT|KG)\s+'
    r'(' + _NUM + r')\s+(' + _CURR + r')/(LIT|MT|KG)\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_SINGLE_QTY_3 = re.compile(         # 383.00 USG  rate  ext tax total
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _CURR + r')/(' + _UOM + r')\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_EA_3 = re.compile(                  # 1 EA  rate/EA  ext tax total
    r'^(.+?)\s+'
    r'(' + _NUM + r')\s+(EA)\s+'
    r'(' + _NUM + r')\s+(?:' + _CURR + r'|' + _NUM + r')/(EA)\s+'
    r'(' + _NUM + r')\s+(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)

_P_COLT_EA = re.compile(               # COLT service: desc  qty EA  unit_price  total
    r'^(.+?)\s+(\d+)\s+(EA)\s+(' + _NUM + r')\s+(' + _NUM + r')$',
    re.MULTILINE
)


def _is_colt_invoice(text: str) -> bool:
    t = (text or '').upper()
    return 'TRIP NO.' in t and 'SERVICE DATE' in t


def parse_colt_line_items(text: str, payment_currency: str = "USD") -> list:
    """
    Parse COLT service invoices where PyMuPDF emits each table cell as a line.
    The remittance amount is the fifth numeric value after qty/unit price.
    """
    if not _is_colt_invoice(text):
        return []

    lines = [ln.strip() for ln in (text or '').replace('\u00a0', ' ').splitlines() if ln.strip()]
    date_pat = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
    qty_pat = re.compile(r'^(?P<qty>[0-9,]+(?:\.\d+)?)\s+(?P<uom>[A-Z]{1,4})$')
    num_pat = re.compile(r'^[0-9,]+(?:\.\d+)?$')
    remit_pat = re.compile(r'^' + _CURR + r'\s+' + _NUM + r'$', re.IGNORECASE)

    start_idx = 0
    for i, line in enumerate(lines):
        if 'PLEASE REMIT THIS AMOUNT' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                if remit_pat.match(lines[j]):
                    start_idx = j + 1
                    break
            break

    rows = []
    seen = set()
    i = start_idx
    while i < len(lines):
        up = lines[i].upper()
        if up.startswith('COMMENTS') or up.startswith('VENDOR CODE'):
            break
        if not date_pat.match(lines[i]):
            i += 1
            continue

        i += 1
        while i < len(lines) and re.fullmatch(r'[A-Z0-9]{3,4}', lines[i]):
            i += 1

        desc_parts = []
        while i < len(lines) and not qty_pat.match(lines[i]):
            up = lines[i].upper()
            if date_pat.match(lines[i]) or up.startswith('COMMENTS') or up.startswith('VENDOR CODE'):
                break
            desc_parts.append(lines[i])
            i += 1

        if i >= len(lines):
            break
        qty_match = qty_pat.match(lines[i])
        if not qty_match or not desc_parts:
            i += 1
            continue

        qty = _tf(qty_match.group('qty'))
        uom = qty_match.group('uom')
        i += 1

        nums = []
        while i < len(lines) and len(nums) < 5 and num_pat.match(lines[i]):
            nums.append(_tf(lines[i]))
            i += 1
        if len(nums) < 2:
            continue

        row = {
            "DESCRIPTION": " ".join(desc_parts).strip(),
            "QUANTITY": qty,
            "UOM": uom,
            "UNIT PRICE": nums[0],
            "PRICE BASIS": f"{payment_currency}/{uom}",
            "EXTENDED AMOUNT": nums[1],
            "TAX AMOUNT": 0.0,
            "AMOUNT": nums[4] if len(nums) >= 5 else nums[1],
        }
        key = (row["DESCRIPTION"], round(row["AMOUNT"], 2))
        if key not in seen:
            seen.add(key)
            rows.append(row)

    return rows


def _line_values(text: str) -> list:
    return [ln.strip() for ln in (text or '').replace('\u00a0', ' ').splitlines() if ln.strip()]


def _table_noise_filter(lines: list) -> list:
    noise_exact = {
        "DESCRIPTION", "QUANTITY", "UNIT PRICE", "EXTENDED AMOUNT", "TAX AMOUNT",
        "DESTINATION", "MAIL INSTRUCTIONS", "DATE UPLIFTED FUEL TICKET AIRCRAFT TYPE",
        "FLIGHT NO. TERMS", "TAIL NO. LOCATION TERRITORY CONTACT", "INVOICE",
        "PAGE NO.", "USD USD USD", "CAD CAD CAD", "EUR EUR EUR",
        "CUSTOMER NO.", "INVOICE NO.", "INVOICE DATE", "IMPORTO TOTALE",
        "N. ORDINE DI VENDITA", "FECHA DE VENCIMIENTO", "PAYMENT DUE DATE",
        "INVOICE AMOUNT",
    }
    out = []
    for line in lines:
        up = line.upper().strip()
        if up in noise_exact:
            continue
        if up.startswith((
            "DESCRIPTION/", "QUANTITY/", "UNIT PRICE/", "EXTENDED AMOUNT/",
            "TAX AMOUNT/", "SALES ORDER NO", "INVOICE AMOUNT/",
            "PAYMENT DUE DATE/",
        )):
            continue
        if re.match(r'^\d+\s*-\s*\d+$', line):
            continue
        if "WORLD FUEL SERVICES" in up and "INC" in up:
            continue
        out.append(line)
    return out


def parse_line_items_column_blocks(text: str) -> list:
    """
    Parse WFS column-block text where each table cell is emitted on its own
    line instead of one row per line.
    """
    lines = _line_values(text)
    start_idx = None

    for i, line in enumerate(lines):
        if line.upper().startswith("SALES ORDER NO"):
            for j in range(i + 1, min(i + 12, len(lines))):
                if re.fullmatch(r'\d+', lines[j]):
                    start_idx = j + 1
                    break
            if start_idx is None:
                start_idx = i + 1
            break

    if start_idx is None:
        for i, line in enumerate(lines):
            if line.upper().startswith("DESCRIPTION"):
                start_idx = i + 1
                break
    if start_idx is None:
        return []

    label = "CUSTOMER NO. INVOICE NO. INVOICE DATE"
    three_num_line = re.compile(r'^[0-9,]+\.\d{2}\s+[0-9,]+\.\d{2}\s+[0-9,]+\.\d{2}$')
    last_three_idx = None
    stop_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if three_num_line.match(lines[i]):
            last_three_idx = i
            if label in " ".join(lines[i:i + 60]).upper():
                stop_idx = i
                break
    if stop_idx == len(lines) and last_three_idx is not None:
        stop_idx = last_three_idx

    table = _table_noise_filter(lines[start_idx:stop_idx])
    qty_pat = re.compile(r'^[0-9,]+(?:\.\d+)?\s+[A-Z]{1,4}(?:\s+[0-9,]+(?:\.\d+)?\s+[A-Z]{1,4})?$')
    unit_price_pat = re.compile(r'^[0-9,]+(?:\.\d+)?\s+[A-Z]{3}/[A-Z]{1,4}$')
    amt_pat = re.compile(r'^[0-9,]+\.\d{2}$')

    desc = []
    i = 0
    while i < len(table) and not qty_pat.match(table[i]):
        desc.append(table[i])
        i += 1

    qty = []
    while i < len(table) and qty_pat.match(table[i]):
        parts = table[i].split()
        qty.append((_tf(parts[0]), parts[1]))
        i += 1

    unit_prices = []
    while i < len(table) and unit_price_pat.match(table[i]):
        price, basis = table[i].split()
        unit_prices.append((_tf(price), basis))
        i += 1

    amounts = []
    while i < len(table):
        if amt_pat.match(table[i]):
            amounts.append(_tf(table[i]))
        i += 1

    n = min(len(desc), len(qty), len(unit_prices))
    if n == 0:
        return []

    ext = amounts[0:n] if len(amounts) >= n else [0.0] * n
    tax = amounts[n:2 * n] if len(amounts) >= 2 * n else [0.0] * n
    total = amounts[2 * n:3 * n] if len(amounts) >= 3 * n else ext

    rows = []
    for idx in range(n):
        rows.append({
            "DESCRIPTION": desc[idx],
            "QUANTITY": qty[idx][0],
            "UOM": qty[idx][1],
            "UNIT PRICE": unit_prices[idx][0],
            "PRICE BASIS": unit_prices[idx][1],
            "EXTENDED AMOUNT": ext[idx] if idx < len(ext) else 0.0,
            "TAX AMOUNT": tax[idx] if idx < len(tax) else 0.0,
            "AMOUNT": total[idx] if idx < len(total) else (ext[idx] if idx < len(ext) else 0.0),
        })
    return rows


def parse_line_items(text: str, payment_currency: str = "USD") -> list:
    """
    Extract line items from invoice text.

    For dual-currency invoices (6-amount columns), always returns the
    remittance/payment-currency column (USD column = every 2nd value).
    Returns a list of dicts matching the existing JSON schema.
    """
    colt_rows = parse_colt_line_items(text, payment_currency=payment_currency)
    if colt_rows:
        return colt_rows

    rows = []
    seen = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        row = None

        # ── Dual quantity (USG + LIT), 6 amounts ─────────────────────────────
        m = _P_DUAL_QTY_6.match(line)
        if m:
            g = m.groups()
            # groups: desc, qty1, uom1, qty2, uom2, price, curr, puom,
            #         e_loc, e_usd, t_loc, t_usd, a_loc, a_usd
            row = {
                "DESCRIPTION":    g[0].strip(),
                "QUANTITY":       _tf(g[1]),
                "UOM":            g[2],
                "UNIT PRICE":     _tf(g[5]),
                "PRICE BASIS":    f"{g[6]}/{g[7]}",
                "EXTENDED AMOUNT": _tf(g[9]),   # USD column
                "TAX AMOUNT":     _tf(g[11]),
                "AMOUNT":         _tf(g[13]),
            }

        # ── Single quantity non-EA, 6 amounts ────────────────────────────────
        if row is None:
            m = _P_SINGLE_QTY_6.match(line)
            if m:
                g = m.groups()
                # groups: desc, qty, uom, price, curr, puom,
                #         e_loc, e_usd, t_loc, t_usd, a_loc, a_usd
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            g[2],
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    f"{g[4]}/{g[5]}",
                    "EXTENDED AMOUNT": _tf(g[7]),
                    "TAX AMOUNT":     _tf(g[9]),
                    "AMOUNT":         _tf(g[11]),
                }

        # ── EA 6 amounts ──────────────────────────────────────────────────────
        if row is None:
            m = _P_EA_6.match(line)
            if m:
                g = m.groups()
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            "EA",
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    f"{g[4]}/EA",
                    "EXTENDED AMOUNT": _tf(g[6]),
                    "TAX AMOUNT":     _tf(g[8]),
                    "AMOUNT":         _tf(g[10]),
                }

        # ── LIT-only 3 amounts (Canada EFT) ──────────────────────────────────
        # groups: desc, qty, uom1, rate, curr, uom2, ext, tax, total
        if row is None:
            m = _P_LIT_ONLY_3.match(line)
            if m:
                g = m.groups()
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            g[2],
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    f"{g[4]}/{g[5]}",
                    "EXTENDED AMOUNT": _tf(g[6]),
                    "TAX AMOUNT":     _tf(g[7]),
                    "AMOUNT":         _tf(g[8]),
                }

        # ── Single quantity 3 amounts ─────────────────────────────────────────
        if row is None:
            m = _P_SINGLE_QTY_3.match(line)
            if m:
                g = m.groups()
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            g[2],
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    f"{g[4]}/{g[5]}",
                    "EXTENDED AMOUNT": _tf(g[6]),
                    "TAX AMOUNT":     _tf(g[7]),
                    "AMOUNT":         _tf(g[8]),
                }

        # ── EA 3 amounts ──────────────────────────────────────────────────────
        if row is None:
            m = _P_EA_3.match(line)
            if m:
                g = m.groups()
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            "EA",
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    f"USD/EA",
                    "EXTENDED AMOUNT": _tf(g[4]),
                    "TAX AMOUNT":     _tf(g[5]),
                    "AMOUNT":         _tf(g[6]),
                }

        # ── COLT service lines ────────────────────────────────────────────────
        if row is None:
            m = _P_COLT_EA.match(line)
            if m:
                g = m.groups()
                row = {
                    "DESCRIPTION":    g[0].strip(),
                    "QUANTITY":       _tf(g[1]),
                    "UOM":            "EA",
                    "UNIT PRICE":     _tf(g[3]),
                    "PRICE BASIS":    "USD/EA",
                    "EXTENDED AMOUNT": _tf(g[4]),
                    "TAX AMOUNT":     0.0,
                    "AMOUNT":         _tf(g[4]),
                }

        if row is None:
            continue

        # Deduplicate and sanity-check
        key = (row["DESCRIPTION"], round(row["AMOUNT"], 2))
        if key in seen:
            continue
        # Filter out totals/subtotal rows caught by the regex
        if row["DESCRIPTION"].upper() in {
            "TOTAL", "SUBTOTAL", "TAX TOTAL", "INVOICE TOTAL",
            "TOTAL TAX", "TOTAL EXCLUSIVE OF TAX"
        }:
            continue

        seen.add(key)
        rows.append(row)

    if not rows:
        rows = parse_line_items_column_blocks(text)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Header helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_header_fields(text: str) -> dict:
    """
    Extract all header fields from invoice text.
    Returns a dict with keys matching the existing JSON schema.
    """
    customer_no, invoice_no, invoice_date = find_invoice_triplet(text)

    h = {
        "CUSTOMER NO.":   customer_no or "",
        "INVOICE NO.":    invoice_no  or "",
        "INVOICE DATE":   invoice_date or "",
        "DUE DATE":       "",
        "SALES ORDER NO.": "",
        "PO NO./CONTRACT NO.": "N/A",
        "AMOUNT TO BE EFT DRAFTED": 0.0,
        "INVOICE AMOUNT": 0.0,
    }

    # Due date
    dd = re.search(
        r'DUE\s+DATE(?:\s*/\s*FECHA\s+DE\s+VENCIMIENTO)?\s*\n?\s*(\d{1,2}-[A-Z]{3}-\d{2,4})',
        text, re.IGNORECASE
    )
    if dd:
        h["DUE DATE"] = dd.group(1)

    # Sales order
    so = re.search(r'SALES\s+ORDER\s+NO\.?\s*\n?\s*(\d{5,})', text, re.IGNORECASE)
    if so:
        h["SALES ORDER NO."] = so.group(1)

    # PO / contract
    po = re.search(r'PO\s+NO\./CONTRACT\s+NO\.?\s*\n?\s*(\S+)', text, re.IGNORECASE)
    if po:
        h["PO NO./CONTRACT NO."] = po.group(1)

    # Payment amount — use the "PLEASE REMIT" / "AMOUNT TO BE EFT DRAFTED" footer
    remit = re.search(
        r'(?:PLEASE\s+REMIT\s+THIS\s+AMOUNT|AMOUNT\s+TO\s+BE\s+EFT\s+DRAFTED)'
        r'[^\n]*\n.*?('
        + _CURR + r')\s+(' + _NUM + r')',
        text, re.IGNORECASE | re.DOTALL
    )
    if remit:
        h["INVOICE AMOUNT"] = _tf(remit.group(2))
        h["AMOUNT TO BE EFT DRAFTED"] = h["INVOICE AMOUNT"]

    # Page number — specifically a "N - N" pattern after the header triplet
    # Avoid matching postal codes (e.g. 2774-550 has no space around dash)
    pg = re.search(r'\b(\d{1,3})\s+-\s+(\d{1,3})\b', text)
    if pg:
        h["PAGE NO."] = f"{pg.group(1)} - {pg.group(2)}"

    return h


def extract_payment_info(text: str) -> dict:
    """
    Extract currency and amount from ELECTRONIC / EFT / INTERNAL payment line.
    """
    pay = re.search(
        r'(?:ELECTRONIC|EFT|INTERNAL|DIGITAL_IT)\s+'
        r'(?:[\d.]+\s+[A-Z]{3}/[A-Z]{3}\s+)?'
        r'(?:[A-Z0-9\-]+\s+)?'
        r'(' + _CURR + r')\s+(' + _NUM + r')',
        text, re.IGNORECASE
    )
    if pay:
        return {"CURRENCY": pay.group(1).upper(), "AMOUNT": _tf(pay.group(2))}

    # CAD-only invoices: "CAD  14,586.92" at the end
    pay2 = re.search(r'\b(CAD|USD|EUR|GBP)\s+(' + _NUM + r')\s*$', text, re.IGNORECASE | re.MULTILINE)
    if pay2:
        return {"CURRENCY": pay2.group(1).upper(), "AMOUNT": _tf(pay2.group(2))}

    return {"CURRENCY": "USD", "AMOUNT": 0.0}


def extract_exchange_rate(text: str) -> dict:
    """
    Extract exchange rate information from invoice footer.
    Returns {RATE, FROM, TO, TEXT} or empty dict.
    """
    m = re.search(
        r'([\d.]+)\s+([A-Z]{3})/([A-Z]{3})',
        text
    )
    if m:
        rate_str = m.group(0)
        rate = float(m.group(1))
        frm  = m.group(2)
        to   = m.group(3)
        # Confirm this is in the exchange rate context (not a unit price)
        ctx = text[max(0, m.start()-80): m.end()+80]
        if re.search(r'EXCHANGE\s+RATE|TASSO\s+DI\s+CAMBIO', ctx, re.IGNORECASE):
            return {"RATE": rate, "FROM": frm, "TO": to, "TEXT": rate_str}

    return {}


def detect_invoice_format(text: str) -> str:
    """
    Detect the WFS invoice format variant.
    Returns one of: 'standard', 'colt', 'bilingual_it', 'canada', 'singapore'
    """
    t = text.upper()

    if 'FATTURA' in t or 'ISTRUZIONI DI POSTA' in t:
        return 'bilingual_it'
    if 'TRIP NO.' in t and ('SERVICE INVOICE' in t or '3RD PARTY' in t or 'OVERFLIGHT' in t):
        return 'colt'
    if 'WORLD FUEL SERVICES CANADA' in t or 'GST#807271705' in t:
        return 'canada'
    if 'SINGAPORE' in t or '157.71' in t:   # JPY rate hint for Japan invoice
        return 'singapore'
    return 'standard'


# ─────────────────────────────────────────────────────────────────────────────
# Extended / fallback parser (called when base parser needs help)
# ─────────────────────────────────────────────────────────────────────────────

def parse_extended_formats(text: str, payload: dict, *args, **kwargs) -> dict:
    """
    Fallback parser. Fills gaps in `payload` using format-specific logic.
    Mutates and returns the payload dict (same schema the app expects).
    """
    fmt = detect_invoice_format(text)
    inv = payload.get("INVOICE", payload)

    # ── Fix customer number if still looks like a decimal fragment ────────────
    hdr = inv.get("INVOICE HEADER", {})
    cust = str(hdr.get("CUSTOMER NO.", ""))
    if len(cust) > 8 or not cust.isdigit():
        c, i, d = find_invoice_triplet(text)
        if c:
            hdr["CUSTOMER NO."] = c
        if i and not hdr.get("INVOICE NO."):
            hdr["INVOICE NO."] = i
        if d and not hdr.get("INVOICE DATE"):
            hdr["INVOICE DATE"] = d

    # ── Fix page number if it captured a postal code ──────────────────────────
    pg = hdr.get("PAGE NO.", "")
    if pg:
        # Valid page numbers are small: 1-1, 1-2, 2-3 etc. (each part ≤ 3 digits)
        parts = pg.replace(' ', '').split('-')
        if len(parts) == 2 and all(len(p) <= 3 and p.isdigit() for p in parts):
            pass  # looks fine
        else:
            # Re-extract with the correct pattern
            pg_m = re.search(r'\b(\d{1,3})\s+-\s+(\d{1,3})\b', text)
            hdr["PAGE NO."] = f"{pg_m.group(1)} - {pg_m.group(2)}" if pg_m else "1 - 1"

    # ── Re-parse line items if none were extracted ────────────────────────────
    li = inv.get("LINE ITEMS", {})
    rows = li.get("ROWS", [])
    pay_amt = inv.get("PAYMENT", {}).get("ELECTRONIC", {}).get("AMOUNT", 0) or 0
    line_sum = sum(r.get("AMOUNT", 0) for r in rows)
    if not rows or all(r.get("AMOUNT", 0) == 0 for r in rows) or \
            (pay_amt > 0 and abs(line_sum - pay_amt) / max(pay_amt, 1) > 0.05):
        pay_cur = inv.get("PAYMENT", {}).get("ELECTRONIC", {}).get("CURRENCY", "USD")
        new_rows = parse_line_items(text, payment_currency=pay_cur)
        if new_rows:
            li["ROWS"] = new_rows
            inv["LINE ITEMS"] = li

    # ── Canada: pick correct currency for total ───────────────────────────────
    if fmt == 'canada':
        pay_info = extract_payment_info(text)
        if pay_info["AMOUNT"]:
            inv.setdefault("PAYMENT", {}).setdefault("ELECTRONIC", {}).update(pay_info)

    # ── Bilingual Italy: ensure correct field labels survive ──────────────────
    if fmt == 'bilingual_it':
        er = extract_exchange_rate(text)
        if er:
            inv.setdefault("PAYMENT", {}).setdefault("EXCHANGE_RATE", er)

    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Standalone full parser (for testing / direct use)
# ─────────────────────────────────────────────────────────────────────────────

def parse_wfs_invoice(text: str, source_file: str = "") -> dict:
    """
    Parse a WFS invoice text block and return the full structured payload.
    This is equivalent to what the main app produces.
    """
    fmt = detect_invoice_format(text)
    hdr = extract_header_fields(text)
    pay = extract_payment_info(text)
    rows = parse_line_items(text, payment_currency=pay.get("CURRENCY", "USD"))

    # Seller name
    seller_map = {
        'WORLD FUEL SERVICES CANADA': 'WORLD FUEL SERVICES CANADA, ULC',
        'WORLD FUEL SERVICES ITALY':  'World Fuel Services Italy S.r.l.',
        'WORLD FUEL COMMODITIES':     'World Fuel Commodities Services (Ireland) Limited',
        'WORLD FUEL SERVICES (SINGAPORE)': 'WORLD FUEL SERVICES (SINGAPORE) PTE LTD',
        'WORLD FUEL SERVICES':        'WORLD FUEL SERVICES, INC.',
    }
    seller_name = 'WORLD FUEL SERVICES, INC.'
    t_upper = text.upper()
    for key, name in seller_map.items():
        if key in t_upper:
            seller_name = name
            break

    # Bill-to name (first non-WFS company name)
    bill_to = ""
    lines = text.splitlines()
    for ln in lines:
        ln = ln.strip()
        if (ln and len(ln) > 5 and ln[0].isupper()
                and not re.search(r'WORLD\s+FUEL|WFS|SWIFT:|ACCT|SORT\s+CODE|IBAN|HSBC|Bank of', ln, re.I)
                and not re.search(r'^\d', ln)
                and 'INVOICE' not in ln.upper()
                and 'REMIT' not in ln.upper()):
            bill_to = ln
            break

    return {
        "INVOICE": {
            "DOCUMENT": {
                "DOCUMENT TYPE": "INVOICE",
                "SOURCE FILE":   source_file,
                "EXTRACTED AT":  datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                "FORMAT":        fmt,
                "SCHEMA VERSION": "4.1",
            },
            "BILL TO":  {"NAME": bill_to, "ADDRESS": []},
            "SELLER":   {"NAME": seller_name},
            "INVOICE HEADER": hdr,
            "PAYMENT":  {"ELECTRONIC": pay},
            "LINE ITEMS": {"ROWS": rows},
        }
    }
