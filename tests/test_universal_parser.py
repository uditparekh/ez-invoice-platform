from siftentry_app.universal_parser import parse_generic_invoice


STRUCTURED_COLUMN_TEXT = """
Tel: +27 11 609 0123 Email: ops@example.com
Internet: www.example.com
EJME (PORTUGAL) AIRCRAFT MANAGEMENT, LDA
RUA CALVET MAGALHAES 245 B
PACO DE ARCOS 2774-550
PORTUGAL
TAX REG: PT510878822
9800 N.W. 41st STREET SUITE 400
MIAMI, FL 33178
WORLD FUEL SERVICES, INC.
USD      1,251.60
ELECTRONIC
PLEASE REMIT THIS AMOUNT
PO NO./CONTRACT NO.
N/A
DUE DATE
13-JUL-2025
INVOICE AMOUNT
SALES ORDER NO.
30037622
LANDING FEES
HANGAR RENTAL
RAMP FEE
1 EA
1 EA
1 EA
460.80000 USD/EA
460.80000 USD/EA
330.00000 USD/EA
460.80
460.80
330.00
0.00
0.00
0.00
460.80
460.80
330.00
1,251.60
0.00
1,251.60
13-JUN-2025
25840190-21101
125928
INVOICE NO.
INVOICE DATE
CUSTOMER NO.
INVOICE
PAGE NO.
USD
USD
USD
REMIT TO:
IBAN# GB27HBUK40127659321630
1 - 1
"""


def test_structured_column_invoice_extracts_real_header_and_rows():
    payload = parse_generic_invoice(
        filename="sample.pdf",
        text=STRUCTURED_COLUMN_TEXT,
        engine="test",
        pages=1,
        extracted_at="2026-06-27T00:00:00Z",
    )
    invoice = payload["INVOICE"]
    header = invoice["INVOICE HEADER"]
    rows = invoice["LINE ITEMS"]["ROWS"]

    assert invoice["DOCUMENT"]["PARSER"] == "Structured Column"
    assert header["INVOICE NO."] == "25840190-21101"
    assert header["INVOICE DATE"] == "13-JUN-2025"
    assert header["DUE DATE"] == "13-JUL-2025"
    assert header["PO NO./CONTRACT NO."] == "N/A"
    assert invoice["SELLER"]["NAME"] == "WORLD FUEL SERVICES, INC."
    assert invoice["SELLER"]["ADDRESS"] == ["9800 N.W. 41st STREET SUITE 400", "MIAMI, FL 33178"]
    assert invoice["BILL TO"]["TAX ID"] == "PT510878822"
    assert header["INVOICE AMOUNT"] == 1251.6
    assert [row["DESCRIPTION"] for row in rows] == [
        "LANDING FEES",
        "HANGAR RENTAL",
        "RAMP FEE",
    ]
    assert sum(row["AMOUNT"] for row in rows) == 1251.6


def test_generic_parser_does_not_turn_bank_details_into_line_items():
    payload = parse_generic_invoice(
        filename="unknown.pdf",
        text="""
        INVOICE
        Tel: +1 555 0100 Email: billing@example.com
        ACCT# 59321630
        IBAN# GB27HBUK40127659321630
        Amount Due: USD 1,251.60
        """,
        engine="test",
        pages=1,
        extracted_at="2026-06-27T00:00:00Z",
    )
    invoice = payload["INVOICE"]
    rows = invoice["LINE ITEMS"]["ROWS"]

    assert invoice["INVOICE HEADER"]["INVOICE NO."] == "unknown"
    assert len(rows) == 1
    assert rows[0]["DESCRIPTION"] == "Invoice total"
    assert rows[0]["AMOUNT"] == 1251.6
