from ez_invoice_app.api_client import (
    invoice_to_legacy_payload,
    invoice_to_session_data,
    parser_mode_for_api,
)


def sample_api_invoice():
    return {
        "id": "invoice-1",
        "organization_id": "org-1",
        "source_file": "sample.pdf",
        "parser": "Generic",
        "extraction_engine": "pymupdf",
        "page_count": 1,
        "status": "validated",
        "invoice_number": "INV-100",
        "invoice_date": "19-JUN-2026",
        "due_date": "19-JUL-2026",
        "purchase_order": "PO-10",
        "currency": "INR",
        "subtotal": 100,
        "tax_total": 18,
        "total": 118,
        "supplier": {"name": "Supplier", "tax_id": "GST-1", "address": []},
        "customer": {"name": "Client", "tax_id": "", "address": []},
        "direction": "inbound",
        "lines": [
            {
                "description": "Material",
                "quantity": 1,
                "uom": "EA",
                "unit_price": 100,
                "net_amount": 100,
                "tax_amount": 18,
                "total_amount": 118,
                "hsn_sac": "1234",
                "category": "Materials",
                "gl_code": "PURCHASES A/C",
            }
        ],
        "validation_issues": [],
        "raw_payload": {},
        "created_at": "2026-06-19T00:00:00Z",
        "updated_at": "2026-06-19T00:00:00Z",
    }


def test_api_invoice_translates_to_pilot_payload():
    invoice = sample_api_invoice()
    payload = invoice_to_legacy_payload(invoice)
    legacy = payload["INVOICE"]

    assert legacy["INVOICE HEADER"]["INVOICE NO."] == "INV-100"
    assert legacy["SELLER"]["NAME"] == "Supplier"
    assert legacy["LINE ITEMS"]["ROWS"][0]["GL_CODE"] == "PURCHASES A/C"

    session_data = invoice_to_session_data(invoice)
    assert session_data["ok"] is True
    assert session_data["api_invoice_id"] == "invoice-1"


def test_parser_mode_mapping():
    assert parser_mode_for_api("Auto") == "auto"
    assert parser_mode_for_api("AI/OCR assisted") == "ai_assisted"
    assert parser_mode_for_api("GST/e-Invoice adapter") == "gst/e-invoice adapter"
    assert parser_mode_for_api("Universal extraction") == "universal extraction"
