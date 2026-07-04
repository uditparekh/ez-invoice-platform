"""Tests for parse-time evidence bounding boxes and mobile send-back (Step 13)."""

from pathlib import Path

from .test_api import authorization, bootstrap, import_sample_invoice, make_client, make_text_pdf, organization_id


def upload_pdf(client, headers, org_id: str, pdf_bytes: bytes) -> dict:
    response = client.post(
        f"/api/v1/invoices/upload?organization_id={org_id}",
        files={"file": ("evidence-test.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_parse_time_evidence_carries_bounding_boxes(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        pdf = make_text_pdf(
            "TAX INVOICE\n"
            "Invoice No: EVD-2024-777\n"
            "Supplier: Madelin Enterprises Pvt Ltd\n"
            "Subtotal: 1000.00\nIGST: 180.00\nTOTAL: 1180.00\n"
        )
        invoice = upload_pdf(client, headers, org_id, pdf)

        evidence = invoice.get("evidence") or []
        by_field = {item["field"]: item for item in evidence}
        assert "invoice_number" in by_field, evidence
        box = by_field["invoice_number"]
        assert box["page"] == 1
        assert box["x0"] is not None and 0 <= box["x0"] < box["x1"] <= 1
        assert box["y0"] is not None and 0 <= box["y0"] < box["y1"] <= 1
        assert box["confidence"] == 0.95

        # Review payload carries the same located evidence for the workspace.
        review = client.get(
            f"/api/v1/invoices/{invoice['id']}/review", headers=headers
        )
        assert review.status_code == 200
        fields = {f["field_path"]: f for f in review.json()["fields"]}
        inv_evidence = fields["invoice_number"]["evidence"]
        assert any(e.get("x0") is not None for e in inv_evidence)


def test_send_back_returns_invoice_to_review_with_reason(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        invoice = import_sample_invoice(client, tokens, org_id, "sendback.pdf")
        assert (
            client.post(
                f"/api/v1/invoices/{invoice['id']}/validate", headers=headers
            ).status_code
            == 200
        )

        # Reject with a reason from the mobile approvals flow.
        response = client.post(
            f"/api/v1/invoices/{invoice['id']}/send-back",
            json={"reason": "Amount doesn't match the PO"},
            headers=headers,
        )
        assert response.status_code == 200
        sent_back = response.json()
        assert sent_back["status"] == "needs_review"
        assert any(
            "Amount doesn't match the PO" in issue
            for issue in sent_back["validation_issues"]
        )

        # Guardrail: can't send back an invoice that isn't validated/approved.
        again = client.post(
            f"/api/v1/invoices/{invoice['id']}/send-back",
            json={"reason": "Twice should fail"},
            headers=headers,
        )
        assert again.status_code == 409
