"""Uniform posting adapters over the proven local connector implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from ..erp_connector import ConnectorResult, PreflightIssue
from .domain import invoice_to_legacy_payload
from .models import ClientProfile, Invoice, PostingTarget


class PostingAdapter(Protocol):
    target: PostingTarget

    def post(
        self,
        invoice: Invoice,
        dry_run: bool = False,
        client_profile: Optional[ClientProfile] = None,
    ) -> ConnectorResult:
        ...


def _basic_issues(invoice: Invoice) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    if not invoice.invoice_number.strip():
        issues.append(PreflightIssue("invoice_number", "Invoice number is required.", "invoice_number"))
    if not invoice.supplier.name.strip():
        issues.append(PreflightIssue("supplier", "Supplier name is required.", "supplier.name"))
    if not invoice.lines:
        issues.append(PreflightIssue("lines", "At least one invoice line is required.", "lines"))
    return issues


def _connector_result(
    result: Dict[str, Any],
    external_keys: tuple[str, ...],
) -> ConnectorResult:
    external_id = None
    for key in external_keys:
        if result.get(key):
            external_id = str(result[key])
            break
    issues = [
        PreflightIssue(
            code=str(issue.get("code", "connector_issue")),
            message=str(issue.get("message", "Connector issue")),
            field=str(issue.get("field", "")),
            blocking=bool(issue.get("blocking", True)),
        )
        for issue in result.get("issues", []) or []
        if isinstance(issue, dict)
    ]
    return ConnectorResult(
        success=bool(result.get("success")),
        message=str(result.get("message", "Connector completed.")),
        external_id=external_id,
        issues=issues,
        raw=result,
    )


@dataclass
class QuickBooksAdapter:
    target: PostingTarget = PostingTarget.QUICKBOOKS

    def post(
        self,
        invoice: Invoice,
        dry_run: bool = False,
        client_profile: Optional[ClientProfile] = None,
    ) -> ConnectorResult:
        issues = _basic_issues(invoice)
        if issues:
            return ConnectorResult(False, issues[0].message, issues=issues)
        payload = invoice_to_legacy_payload(invoice)
        if dry_run:
            return ConnectorResult(
                True,
                "QuickBooks preflight passed. No Bill was created.",
                raw={"invoice_number": invoice.invoice_number, "line_count": len(invoice.lines)},
            )
        try:
            from ..qb_integration import send_to_quickbooks

            return _connector_result(
                send_to_quickbooks(payload),
                ("bill_id", "external_id"),
            )
        except Exception as exc:
            return ConnectorResult(False, f"QuickBooks adapter failed: {exc}")


@dataclass
class TallyAdapter:
    target: PostingTarget = PostingTarget.TALLY

    def post(
        self,
        invoice: Invoice,
        dry_run: bool = False,
        client_profile: Optional[ClientProfile] = None,
    ) -> ConnectorResult:
        issues = _basic_issues(invoice)
        if issues:
            return ConnectorResult(False, issues[0].message, issues=issues)
        try:
            from ..tally_integration import send_to_tally

            result = send_to_tally(
                invoice_to_legacy_payload(invoice),
                dry_run=dry_run,
                settings_override=_tally_settings_from_profile(client_profile),
                connector_settings_override=_tally_connector_settings_from_profile(
                    client_profile
                ),
            )
            return _connector_result(result, ("voucher_number", "external_id"))
        except Exception as exc:
            return ConnectorResult(False, f"Tally adapter failed: {exc}")


@dataclass
class ZohoBooksAdapter:
    target: PostingTarget = PostingTarget.ZOHO_BOOKS

    def post(
        self,
        invoice: Invoice,
        dry_run: bool = False,
        client_profile: Optional[ClientProfile] = None,
    ) -> ConnectorResult:
        issues = _basic_issues(invoice)
        if issues:
            return ConnectorResult(False, issues[0].message, issues=issues)
        payload = invoice_to_legacy_payload(invoice)
        try:
            if dry_run:
                from ..zoho_integration import build_zoho_export

                return ConnectorResult(
                    True,
                    "Zoho Books preflight passed. No Bill was created.",
                    raw=build_zoho_export(payload),
                )
            from ..zoho_integration import send_to_zoho

            return _connector_result(
                send_to_zoho(payload),
                ("external_id", "bill_id"),
            )
        except Exception as exc:
            return ConnectorResult(False, f"Zoho Books adapter failed: {exc}")


def default_adapters() -> Dict[PostingTarget, PostingAdapter]:
    adapters: list[PostingAdapter] = [
        QuickBooksAdapter(),
        TallyAdapter(),
        ZohoBooksAdapter(),
    ]
    return {adapter.target: adapter for adapter in adapters}


def _tally_settings_from_profile(
    client_profile: Optional[ClientProfile],
) -> Optional[Dict[str, Any]]:
    if not client_profile:
        return None
    settings = client_profile.settings
    posting_mode = (
        "Item Invoice"
        if settings.posting_mode == "item_invoice"
        else "Accounting Voucher"
    )
    connection_settings = settings.connection_settings or {}
    return {
        "url": connection_settings.get("tally_url")
        or connection_settings.get("url")
        or "http://localhost:9000",
        "company": settings.company_name,
        "country_code": settings.country_code,
        "country_name": settings.country_name,
        "default_currency": settings.default_currency,
        "invoice_format": settings.invoice_format,
        "tax_mode": settings.tax_mode,
        "tax_registration_label": settings.tax_registration_label,
        "voucher_type": settings.voucher_type or "Purchase",
        "posting_mode": posting_mode,
        "purchase_ledger": settings.purchase_ledger or "Purchase Accounts",
        "tax_ledger": settings.tax_ledger,
        "stock_item_name": settings.stock_item_name,
        "stock_item_hsn": settings.stock_item_hsn,
        "stock_item_uom": settings.stock_item_uom,
        "godown_name": settings.godown_name,
        "tcs_ledger": settings.tcs_ledger,
        "round_off_ledger": settings.round_off_ledger,
        "tax_settings": settings.tax_settings or {},
    }


def _tally_connector_settings_from_profile(
    client_profile: Optional[ClientProfile],
) -> Optional[Dict[str, Any]]:
    if not client_profile:
        return None
    connection_settings = client_profile.settings.connection_settings or {}
    connector_url = (
        connection_settings.get("connector_url")
        or connection_settings.get("url")
        or connection_settings.get("tally_connector_url")
    )
    if not connector_url:
        return None
    return {
        "enabled": connection_settings.get("connector_enabled", True),
        "url": connector_url,
        "token": connection_settings.get("connector_token", ""),
        "workspace_id": connection_settings.get("workspace_id", ""),
    }
