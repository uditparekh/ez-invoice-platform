from pathlib import Path

from ez_invoice_app.backend.domain import legacy_payload_to_invoice
from ez_invoice_app.backend.models import (
    InvoicePatch,
    InvoiceStatus,
    OrganizationCreate,
    PostingTarget,
)
from ez_invoice_app.backend.repository import InvoiceRepository

from .test_domain import sample_legacy_payload


def test_repository_tracks_corrections_validation_and_posting(tmp_path: Path):
    repository = InvoiceRepository(tmp_path / "test.db")
    organization = repository.create_organization(
        OrganizationCreate(
            name="Example Client",
            legal_names=["Example Client Private Limited"],
            default_currency="INR",
        )
    )
    created = legacy_payload_to_invoice(
        sample_legacy_payload(),
        organization_id=organization.id,
        source_file="sample.pdf",
    )
    invoice = repository.create_invoice(created)

    corrected = repository.patch_invoice(
        invoice.id,
        InvoicePatch(purchase_order="PO-UPDATED"),
        actor_id="reviewer-1",
    )
    assert corrected is not None
    assert corrected.purchase_order == "PO-UPDATED"
    assert corrected.status == InvoiceStatus.EXTRACTED.value

    validated = repository.update_validation(invoice.id, InvoiceStatus.VALIDATED, [])
    assert validated is not None
    assert validated.status == InvoiceStatus.VALIDATED.value

    posting = repository.create_posting(
        invoice_id=invoice.id,
        target=PostingTarget.TALLY,
        success=True,
        dry_run=True,
        message="Tally preflight passed.",
    )
    assert repository.get_posting(posting.id) == posting
