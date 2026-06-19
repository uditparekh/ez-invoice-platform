from ez_invoice_app.backend.domain import (
    invoice_to_legacy_payload,
    legacy_payload_to_invoice,
)
from ez_invoice_app.backend.models import Invoice
from ez_invoice_app.backend.repository import utc_now


def sample_legacy_payload():
    return {
        "INVOICE": {
            "DOCUMENT": {
                "SOURCE FILE": "sample.pdf",
                "PARSER": "Generic",
                "EXTRACTION ENGINE": "test",
                "PAGES": 1,
            },
            "SELLER": {"NAME": "Example Supplier", "GSTIN": "24ABCDE1234F1Z5"},
            "BILL TO": {"NAME": "Example Client"},
            "INVOICE HEADER": {
                "INVOICE NO.": "INV-100",
                "INVOICE DATE": "19-JUN-2026",
                "DUE DATE": "19-JUL-2026",
                "PO NO./CONTRACT NO.": "PO-10",
                "INVOICE AMOUNT": 118.0,
            },
            "PAYMENT": {"ELECTRONIC": {"CURRENCY": "INR", "AMOUNT": 118.0}},
            "LINE ITEMS": {
                "ROWS": [
                    {
                        "DESCRIPTION": "Material",
                        "QUANTITY": 1,
                        "UOM": "EA",
                        "UNIT PRICE": 100,
                        "EXTENDED AMOUNT": 100,
                        "TAX AMOUNT": 18,
                        "AMOUNT": 118,
                        "HSN/SAC": "1234",
                    }
                ]
            },
            "INVOICE TAX SUMMARY": {"TOTAL TAX": 18},
            "ROUTING": {"DIRECTION": "inbound"},
        }
    }


def test_legacy_payload_round_trip_preserves_reviewed_fields():
    created = legacy_payload_to_invoice(
        sample_legacy_payload(),
        organization_id="org-1",
        source_file="sample.pdf",
    )
    now = utc_now()
    invoice = Invoice(id="invoice-1", created_at=now, updated_at=now, **created.model_dump())
    invoice.lines[0].category = "materials"
    invoice.lines[0].gl_code = "PURCHASES A/C"

    legacy = invoice_to_legacy_payload(invoice)
    row = legacy["INVOICE"]["LINE ITEMS"]["ROWS"][0]

    assert created.invoice_number == "INV-100"
    assert created.total == 118
    assert created.tax_total == 18
    assert created.supplier.name == "Example Supplier"
    assert row["CATEGORY"] == "materials"
    assert row["GL_CODE"] == "PURCHASES A/C"
