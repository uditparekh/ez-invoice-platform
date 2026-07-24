"""Idempotent, synthetic data for the public read-only demo workspace."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import (
    ExtractionEvidence,
    InvoiceCreate,
    InvoiceLine,
    InvoiceStatus,
    OrganizationCreate,
    OrganizationRole,
    Party,
    PostingTarget,
    User,
)
from .repository import InvoiceRepository
from .security import hash_password


PUBLIC_DEMO_EMAIL = "demo@siftentry.com"
PUBLIC_DEMO_ORGANIZATION = "SiftEntry Demo Workspace"


def _demo_invoice_specs(organization_id: str) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date()
    customer = Party(
        name="SiftEntry Demo Operations Inc.",
        tax_id="88-1234567",
        address=["101 Finance Park", "New York, NY 10001"],
        email="accounts@siftentry.invalid",
    )
    return [
        {
            "invoice": InvoiceCreate(
                organization_id=organization_id,
                source_file="northwind-office-supply-demo.pdf",
                source_path="synthetic-demo/northwind-office-supply-demo.pdf",
                parser="SiftEntry Universal",
                extraction_engine="AI + deterministic validation",
                page_count=2,
                status=InvoiceStatus.EXTRACTED,
                invoice_number="DEMO-QB-1001",
                invoice_date=(today - timedelta(days=6)).isoformat(),
                due_date=(today + timedelta(days=24)).isoformat(),
                purchase_order="PO-DEMO-2401",
                currency="USD",
                subtotal=3200,
                tax_total=288,
                total=3488,
                supplier=Party(
                    name="Northwind Office Supply Inc.",
                    tax_id="12-3456789",
                    address=["18 Market Street", "Austin, TX 78701"],
                    email="billing@northwind.invalid",
                ),
                customer=customer,
                lines=[
                    InvoiceLine(
                        line_number=1,
                        description="Ergonomic office chairs",
                        quantity=4,
                        uom="EA",
                        unit_price=750,
                        net_amount=3000,
                        tax_amount=270,
                        total_amount=3270,
                        hsn_sac="9401.30",
                        category="Office supplies",
                        gl_code="OFFICE EXPENSES",
                        confidence=0.99,
                    ),
                    InvoiceLine(
                        line_number=2,
                        description="Delivery and installation",
                        quantity=1,
                        uom="SERVICE",
                        unit_price=200,
                        net_amount=200,
                        tax_amount=18,
                        total_amount=218,
                        hsn_sac="DELIVERY",
                        category="Freight and installation",
                        gl_code="FREIGHT INWARD",
                        confidence=0.98,
                    ),
                ],
                confidence=0.98,
                evidence=[
                    ExtractionEvidence(
                        field="invoice_number",
                        value="DEMO-QB-1001",
                        page=1,
                        snippet="Invoice No: DEMO-QB-1001",
                        confidence=0.99,
                    ),
                    ExtractionEvidence(
                        field="supplier.name",
                        value="Northwind Office Supply Inc.",
                        page=1,
                        snippet="Northwind Office Supply Inc.",
                        confidence=0.99,
                    ),
                    ExtractionEvidence(
                        field="total",
                        value="3,488.00",
                        page=2,
                        snippet="Invoice total $3,488.00",
                        confidence=0.99,
                    ),
                ],
                raw_payload={
                    "demo": True,
                    "demo_seed_version": 1,
                    "note": "Synthetic invoice generated for the public SiftEntry demo.",
                },
            ),
            "target": PostingTarget.QUICKBOOKS,
            "message": "Supplier bill created successfully in QuickBooks Online.",
            "external_id": "SIFT-DEMO-QB-1001",
        },
        {
            "invoice": InvoiceCreate(
                organization_id=organization_id,
                source_file="brightpath-cloud-services-demo.pdf",
                source_path="synthetic-demo/brightpath-cloud-services-demo.pdf",
                parser="SiftEntry Universal",
                extraction_engine="AI + deterministic validation",
                page_count=1,
                status=InvoiceStatus.EXTRACTED,
                invoice_number="DEMO-ZOHO-1002",
                invoice_date=(today - timedelta(days=3)).isoformat(),
                due_date=(today + timedelta(days=27)).isoformat(),
                purchase_order="PO-DEMO-2402",
                currency="USD",
                subtotal=2400,
                tax_total=192,
                total=2592,
                supplier=Party(
                    name="BrightPath Cloud Services LLC",
                    tax_id="98-7654321",
                    address=["42 Technology Avenue", "Seattle, WA 98101"],
                    email="invoices@brightpath.invalid",
                ),
                customer=customer,
                lines=[
                    InvoiceLine(
                        line_number=1,
                        description="Cloud workflow subscription — quarterly",
                        quantity=3,
                        uom="MONTH",
                        unit_price=800,
                        net_amount=2400,
                        tax_amount=192,
                        total_amount=2592,
                        hsn_sac="SAAS",
                        category="Software subscriptions",
                        gl_code="SOFTWARE EXPENSES",
                        confidence=0.98,
                    ),
                ],
                confidence=0.97,
                evidence=[
                    ExtractionEvidence(
                        field="invoice_number",
                        value="DEMO-ZOHO-1002",
                        page=1,
                        snippet="Invoice DEMO-ZOHO-1002",
                        confidence=0.99,
                    ),
                    ExtractionEvidence(
                        field="supplier.name",
                        value="BrightPath Cloud Services LLC",
                        page=1,
                        snippet="BrightPath Cloud Services LLC",
                        confidence=0.98,
                    ),
                    ExtractionEvidence(
                        field="total",
                        value="2,592.00",
                        page=1,
                        snippet="Amount payable $2,592.00",
                        confidence=0.98,
                    ),
                ],
                raw_payload={
                    "demo": True,
                    "demo_seed_version": 1,
                    "note": "Synthetic invoice generated for the public SiftEntry demo.",
                },
            ),
            "target": PostingTarget.ZOHO_BOOKS,
            "message": "Supplier bill created successfully in Zoho Books.",
            "external_id": "SIFT-DEMO-ZOHO-1002",
        },
    ]


def ensure_public_demo_workspace(repository: InvoiceRepository) -> User:
    """Prepare the existing isolated demo account and its showcase records."""

    user = repository.get_user_by_email(PUBLIC_DEMO_EMAIL)
    if user is None:
        user = repository.create_user(
            email=PUBLIC_DEMO_EMAIL,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            full_name="SiftEntry Demo",
        )

    memberships = repository.list_memberships(user.id)
    if len(memberships) > 1:
        raise RuntimeError("The public demo account must have exactly one workspace.")

    if memberships:
        organization = repository.get_organization(memberships[0].organization_id)
        if organization is None or "demo" not in organization.name.lower():
            raise RuntimeError("The public demo account is linked to a non-demo workspace.")
    else:
        organization = repository.get_organization_by_name(PUBLIC_DEMO_ORGANIZATION)
        if organization is None:
            organization = repository.create_organization(
                OrganizationCreate(
                    name=PUBLIC_DEMO_ORGANIZATION,
                    legal_names=["SiftEntry Demo Operations Inc."],
                    default_currency="USD",
                )
            )

    other_members = [
        member
        for member in repository.list_organization_members(organization.id)
        if member.user_id != user.id
    ]
    if other_members:
        raise RuntimeError("The reserved public demo identity is not isolated.")

    membership = repository.get_membership(user.id, organization.id)
    if membership is None:
        repository.create_membership(
            user.id,
            organization.id,
            OrganizationRole.VIEWER,
        )
    elif membership.role != OrganizationRole.VIEWER:
        repository.create_membership(
            user.id,
            organization.id,
            OrganizationRole.VIEWER,
        )

    if organization.default_currency != "USD":
        updated = repository.set_organization_default_currency(
            organization.id,
            "USD",
        )
        if updated is None:
            raise RuntimeError("The demo workspace currency could not be updated.")

    existing = {
        invoice.invoice_number: invoice
        for invoice in repository.list_invoices(
            organization_id=organization.id,
            limit=200,
        )
    }
    for spec in _demo_invoice_specs(organization.id):
        invoice_data = spec["invoice"]
        invoice = existing.get(invoice_data.invoice_number)
        if invoice is None:
            invoice = repository.create_invoice(invoice_data)

        postings = repository.list_postings_for_invoice(invoice.id, limit=50)
        if not any(
            posting.external_id == spec["external_id"] for posting in postings
        ):
            repository.create_posting(
                invoice_id=invoice.id,
                target=spec["target"],
                success=True,
                dry_run=False,
                actor_id=user.id,
                message=spec["message"],
                external_id=spec["external_id"],
                raw={
                    "demo": True,
                    "reference": spec["external_id"],
                },
            )
        if invoice.status != InvoiceStatus.POSTED:
            repository.set_status(invoice.id, InvoiceStatus.POSTED)

    return user
