"""Uniform posting adapters over the proven local connector implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol

from ..erp_connector import ConnectorResult, PreflightIssue
from .domain import invoice_to_legacy_payload
from .models import Invoice, PostingTarget


class PostingAdapter(Protocol):
    target: PostingTarget

    def post(self, invoice: Invoice, dry_run: bool = False) -> ConnectorResult:
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

    def post(self, invoice: Invoice, dry_run: bool = False) -> ConnectorResult:
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

    def post(self, invoice: Invoice, dry_run: bool = False) -> ConnectorResult:
        issues = _basic_issues(invoice)
        if issues:
            return ConnectorResult(False, issues[0].message, issues=issues)
        try:
            from ..tally_integration import send_to_tally

            result = send_to_tally(
                invoice_to_legacy_payload(invoice),
                dry_run=dry_run,
            )
            return _connector_result(result, ("voucher_number", "external_id"))
        except Exception as exc:
            return ConnectorResult(False, f"Tally adapter failed: {exc}")


@dataclass
class ZohoBooksAdapter:
    target: PostingTarget = PostingTarget.ZOHO_BOOKS

    def post(self, invoice: Invoice, dry_run: bool = False) -> ConnectorResult:
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
