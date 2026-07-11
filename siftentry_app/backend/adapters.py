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


def _profiled_legacy_payload(
    invoice: Invoice,
    client_profile: Optional[ClientProfile],
) -> Dict[str, Any]:
    payload = invoice_to_legacy_payload(invoice)
    if not client_profile:
        return payload

    settings = client_profile.settings
    legacy_invoice = payload.setdefault("INVOICE", {})
    system = (
        client_profile.accounting_system.value
        if hasattr(client_profile.accounting_system, "value")
        else str(client_profile.accounting_system)
    )
    legacy_invoice["ACCOUNTING PROFILE"] = {
        "ID": client_profile.id,
        "NAME": client_profile.name,
        "SYSTEM": system,
        "COUNTRY": settings.country_code,
        "COUNTRY NAME": settings.country_name,
        "DEFAULT CURRENCY": settings.default_currency,
        "INVOICE FORMAT": settings.invoice_format,
        "TAX MODE": settings.tax_mode,
        "POSTING MODE": str(settings.posting_mode),
    }
    legacy_invoice["ACCOUNTING ROUTE"] = {
        "TARGET": system,
        "DIRECTION": settings.direction or invoice.direction,
        "POSTING MODE": str(settings.posting_mode),
        "VOUCHER TYPE": settings.voucher_type,
        "PURCHASE LEDGER": settings.purchase_ledger,
        "TAX LEDGER": settings.tax_ledger,
        "TCS LEDGER": settings.tcs_ledger,
        "ROUND OFF LEDGER": settings.round_off_ledger,
        "GODOWN": settings.godown_name,
    }

    line_items = legacy_invoice.setdefault("LINE ITEMS", {})
    rows = line_items.setdefault("ROWS", [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        _apply_profile_line_defaults(row, settings)
        for mapping in settings.item_mappings:
            if _mapping_matches_row(mapping, row):
                _apply_profile_mapping(row, mapping)

    columns = list(line_items.get("COLUMNS") or [])
    for column in (
        "CLIENT_CATEGORY",
        "TALLY_LEDGER",
        "TALLY_STOCK_ITEM",
        "TARGET_ITEM_NAME",
        "TARGET_UOM",
    ):
        if column not in columns:
            columns.append(column)
    line_items["COLUMNS"] = columns
    return payload


def _apply_profile_line_defaults(row: Dict[str, Any], settings: Any) -> None:
    if settings.purchase_ledger:
        row.setdefault("TALLY_LEDGER", settings.purchase_ledger)
        row.setdefault("PURCHASE_LEDGER", settings.purchase_ledger)
    if settings.tax_ledger:
        row.setdefault("TAX_LEDGER", settings.tax_ledger)
    if settings.stock_item_name:
        row.setdefault("TALLY_STOCK_ITEM", settings.stock_item_name)
        row.setdefault("TARGET_ITEM_NAME", settings.stock_item_name)
    if settings.stock_item_uom:
        row.setdefault("TARGET_UOM", settings.stock_item_uom)
    if settings.godown_name:
        row.setdefault("GODOWN", settings.godown_name)


def _mapping_matches_row(mapping: Any, row: Dict[str, Any]) -> bool:
    description_filter = str(mapping.source_description_contains or "").strip().lower()
    hsn_filter = _digits(mapping.source_hsn_sac)
    if not description_filter and not hsn_filter:
        return False

    description = str(row.get("DESCRIPTION") or row.get("ITEM") or "").lower()
    row_hsn = _digits(row.get("HSN/SAC") or row.get("HSN") or row.get("SAC"))
    description_matches = bool(description_filter and description_filter in description)
    hsn_matches = bool(hsn_filter and row_hsn == hsn_filter)
    return description_matches or hsn_matches


def _apply_profile_mapping(row: Dict[str, Any], mapping: Any) -> None:
    metadata = mapping.metadata or {}
    category = str(
        metadata.get("category")
        or metadata.get("platform_category")
        or metadata.get("client_category")
        or ""
    ).strip()
    gl_code = str(metadata.get("gl_code") or metadata.get("account_code") or "").strip()
    qb_account_id = str(metadata.get("qb_account_id") or "").strip()
    qb_account_name = str(metadata.get("qb_account_name") or "").strip()
    zoho_account_id = str(metadata.get("zoho_account_id") or "").strip()
    zoho_tax_id = str(metadata.get("zoho_tax_id") or "").strip()

    if category:
        row["CATEGORY"] = category
        row["PLATFORM_CATEGORY"] = category
        row["CLIENT_CATEGORY"] = category
    if gl_code:
        row["GL_CODE"] = gl_code
    if qb_account_id:
        row["QB_ACCOUNT_ID"] = qb_account_id
    if qb_account_name:
        row["QB_ACCOUNT"] = qb_account_name
    if zoho_account_id:
        row["ZOHO_ACCOUNT_ID"] = zoho_account_id
    if zoho_tax_id:
        row["ZOHO_TAX_ID"] = zoho_tax_id
    if mapping.target_item_name:
        row["TARGET_ITEM_NAME"] = mapping.target_item_name
        row["TALLY_STOCK_ITEM"] = mapping.target_item_name
    if mapping.target_uom:
        row["TARGET_UOM"] = mapping.target_uom
    if mapping.purchase_ledger:
        row["PURCHASE_LEDGER"] = mapping.purchase_ledger
        row["TALLY_LEDGER"] = mapping.purchase_ledger
    if mapping.tax_ledger:
        row["TAX_LEDGER"] = mapping.tax_ledger


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


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
        payload = _profiled_legacy_payload(invoice, client_profile)
        if dry_run:
            return ConnectorResult(
                True,
                "QuickBooks preflight passed. No Bill was created.",
                raw={
                    "invoice_number": invoice.invoice_number,
                    "line_count": len(invoice.lines),
                    "profile_id": client_profile.id if client_profile else None,
                    "profile_name": client_profile.name if client_profile else None,
                    "target": self.target.value,
                },
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
                _profiled_legacy_payload(invoice, client_profile),
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
        payload = _profiled_legacy_payload(invoice, client_profile)
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
        # The profile defines no machine-local bridge. Explicitly disable the
        # legacy local-connector default (enabled=True at 127.0.0.1:8765),
        # which only makes sense when the Streamlit pilot runs on the same
        # computer as the connector. Hosted posts and dry runs then use the
        # direct Tally path; cloud desktop connectors are unaffected because
        # they use the claim/results endpoints, not this adapter.
        return {"enabled": False}
    return {
        "enabled": connection_settings.get("connector_enabled", True),
        "url": connector_url,
        "token": connection_settings.get("connector_token", ""),
        "workspace_id": connection_settings.get("workspace_id", ""),
    }
