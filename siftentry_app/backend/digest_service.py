"""Weekly email digest for SiftEntry workspaces.

The Settings -> Notifications page has always offered a "Weekly digest"
toggle ("Your week: posted count, value processed, what needs you
Monday"). This module makes that toggle real. The background worker calls
``maybe_send_weekly_digests`` every few minutes; on the configured day
(default Monday, 03:00 UTC — 08:30 IST) each organization with the toggle
on receives one digest per active member covering the previous 7 days.

Duplicate protection: a ``digest.sent`` audit event is recorded per
organization after sending, and no new digest goes out while one exists
from the last 3 days. This survives worker restarts and is safe with
multiple workers at pilot scale.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional

from .models import AccountingSystem, InvoiceStatus

logger = logging.getLogger("siftentry.digest")

DIGEST_DAY = max(0, min(6, int(os.environ.get("SIFTENTRY_DIGEST_DAY", "0"))))
DIGEST_HOUR_UTC = max(0, min(23, int(os.environ.get("SIFTENTRY_DIGEST_HOUR_UTC", "3"))))
DIGEST_WINDOW_DAYS = 7
DIGEST_REPEAT_GUARD = timedelta(days=3)
CONNECTOR_OFFLINE_AFTER = timedelta(minutes=10)
DIGEST_SENT_EVENT = "digest.sent"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class WeeklyDigest:
    organization_id: str
    organization_name: str
    received: int = 0
    posted: int = 0
    posted_value_by_currency: Dict[str, float] = field(default_factory=dict)
    failed_postings: int = 0
    needs_review: int = 0
    awaiting_approval: int = 0
    ready_to_post: int = 0
    formats_in_training: int = 0
    new_formats: List[str] = field(default_factory=list)
    offline_connectors: List[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(
            self.received
            or self.posted
            or self.failed_postings
            or self.needs_review
            or self.awaiting_approval
            or self.ready_to_post
            or self.formats_in_training
            or self.new_formats
            or self.offline_connectors
        )

    @property
    def posted_value_label(self) -> str:
        if not self.posted_value_by_currency:
            return "0"
        parts = [
            f"{amount:,.2f} {currency}"
            for currency, amount in sorted(self.posted_value_by_currency.items())
        ]
        return " + ".join(parts)


def build_weekly_digest(repo, organization, now: datetime) -> WeeklyDigest:
    since = now - timedelta(days=DIGEST_WINDOW_DAYS)
    digest = WeeklyDigest(
        organization_id=organization.id,
        organization_name=organization.name,
    )

    invoices = repo.list_invoices(
        organization_id=organization.id, limit=100_000, offset=0
    )
    invoices_by_id = {invoice.id: invoice for invoice in invoices}
    for invoice in invoices:
        status = (
            invoice.status.value
            if hasattr(invoice.status, "value")
            else str(invoice.status)
        )
        if _aware(invoice.created_at) >= since:
            digest.received += 1
        if status in (
            InvoiceStatus.UPLOADED.value,
            InvoiceStatus.EXTRACTED.value,
            InvoiceStatus.NEEDS_REVIEW.value,
        ):
            digest.needs_review += 1
        elif status == InvoiceStatus.VALIDATED.value:
            digest.awaiting_approval += 1
        elif status == InvoiceStatus.APPROVED.value:
            digest.ready_to_post += 1

    posted_invoice_ids = set()
    for posting in repo.list_recent_postings(organization.id, since):
        if posting.dry_run:
            continue
        if posting.success:
            if posting.invoice_id not in posted_invoice_ids:
                posted_invoice_ids.add(posting.invoice_id)
                digest.posted += 1
                invoice = invoices_by_id.get(posting.invoice_id)
                if invoice and invoice.total:
                    currency = (invoice.currency or "USD").upper()
                    digest.posted_value_by_currency[currency] = (
                        digest.posted_value_by_currency.get(currency, 0.0)
                        + float(invoice.total)
                    )
        else:
            digest.failed_postings += 1

    for record in repo.list_supplier_formats(organization.id):
        if str(record.get("status") or "") == "training":
            digest.formats_in_training += 1
            if int(record.get("samples_count") or 0) <= 1:
                name = str(
                    record.get("supplier_name") or record.get("supplier_key") or ""
                ).strip()
                if name:
                    digest.new_formats.append(name)

    for profile in repo.list_client_profiles_by_system(AccountingSystem.TALLY.value):
        if profile.organization_id != organization.id:
            continue
        connection_settings = profile.settings.connection_settings or {}
        configured = bool(
            str(connection_settings.get("workspace_id") or "").strip()
            and str(connection_settings.get("connector_token") or "").strip()
        )
        if not configured or not connection_settings.get("connector_enabled", True):
            continue
        heartbeat = repo.get_connector_heartbeat(profile.id)
        last_seen = _aware(heartbeat["last_seen_at"]) if heartbeat else None
        if last_seen is None or now - last_seen > CONNECTOR_OFFLINE_AFTER:
            digest.offline_connectors.append(profile.name)

    return digest


def render_digest_text(digest: WeeklyDigest) -> str:
    lines = [
        f"Invoices received: {digest.received}",
        f"Posted to accounting: {digest.posted}"
        + (
            f" (value {digest.posted_value_label})"
            if digest.posted_value_by_currency
            else ""
        ),
    ]
    if digest.failed_postings:
        lines.append(f"Failed postings to retry: {digest.failed_postings}")
    lines.append("")
    lines.append("What needs you:")
    lines.append(f"- Needs review: {digest.needs_review}")
    lines.append(f"- Awaiting approval: {digest.awaiting_approval}")
    lines.append(f"- Approved, ready to post: {digest.ready_to_post}")
    if digest.formats_in_training:
        lines.append(f"- Supplier formats still in training: {digest.formats_in_training}")
    if digest.new_formats:
        lines.append("- New formats detected: " + ", ".join(digest.new_formats[:5]))
    if digest.offline_connectors:
        lines.append(
            "- Tally connector offline: " + ", ".join(digest.offline_connectors)
        )
    return "\n".join(lines)


def render_digest_html(digest: WeeklyDigest) -> str:
    def row(label: str, value: str) -> str:
        return (
            "<tr>"
            f'<td style="padding:6px 16px 6px 0;color:#667085;font-size:14px;">{escape(label)}</td>'
            f'<td style="padding:6px 0;color:#08111F;font-size:14px;font-weight:700;">{escape(value)}</td>'
            "</tr>"
        )

    rows = [
        row("Invoices received", str(digest.received)),
        row(
            "Posted to accounting",
            str(digest.posted)
            + (
                f" · {digest.posted_value_label}"
                if digest.posted_value_by_currency
                else ""
            ),
        ),
    ]
    if digest.failed_postings:
        rows.append(row("Failed postings to retry", str(digest.failed_postings)))
    rows.append(row("Needs review", str(digest.needs_review)))
    rows.append(row("Awaiting approval", str(digest.awaiting_approval)))
    rows.append(row("Approved, ready to post", str(digest.ready_to_post)))
    if digest.formats_in_training:
        rows.append(
            row("Formats still in training", str(digest.formats_in_training))
        )
    parts = [
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;">'
        + "".join(rows)
        + "</table>"
    ]
    if digest.new_formats:
        parts.append(
            '<p style="margin:14px 0 0;font-size:14px;color:#08111F;">'
            "<strong>New formats detected:</strong> "
            + escape(", ".join(digest.new_formats[:5]))
            + "</p>"
        )
    if digest.offline_connectors:
        parts.append(
            '<p style="margin:14px 0 0;font-size:14px;color:#B45309;">'
            "<strong>Tally connector offline:</strong> "
            + escape(", ".join(digest.offline_connectors))
            + " — open the connector on the client&#39;s computer.</p>"
        )
    return "".join(parts)


def send_digest_for_organization(
    repo,
    email_service,
    organization,
    now: datetime,
    dashboard_url: str,
) -> int:
    """Build and send one organization's digest. Returns recipients count."""
    digest = build_weekly_digest(repo, organization, now)
    if not digest.has_content:
        logger.info("digest for %s skipped: nothing to report", organization.id)
        return 0
    summary_text = render_digest_text(digest)
    summary_html = render_digest_html(digest)
    recipients = 0
    for member in repo.list_organization_members(organization.id):
        if not member.is_active or not member.email:
            continue
        try:
            email_service.send_weekly_digest(
                to_email=member.email,
                full_name=member.full_name,
                organization_name=organization.name,
                summary_text=summary_text,
                summary_html=summary_html,
                dashboard_url=dashboard_url,
            )
            recipients += 1
        except Exception:
            logger.exception(
                "digest email to %s for %s failed", member.email, organization.id
            )
    repo.record_audit_event(
        organization.id,
        DIGEST_SENT_EVENT,
        {
            "recipients": recipients,
            "received": digest.received,
            "posted": digest.posted,
            "failed_postings": digest.failed_postings,
            "needs_review": digest.needs_review,
            "awaiting_approval": digest.awaiting_approval,
            "ready_to_post": digest.ready_to_post,
        },
        created_at=now,
    )
    return recipients


def maybe_send_weekly_digests(
    repo,
    email_service,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Send due digests. Called by the worker every few minutes; cheap when idle."""
    now = _aware(now or datetime.now(timezone.utc))
    result: Dict[str, Any] = {"checked": 0, "sent_orgs": 0, "recipients": 0}
    if now.weekday() != DIGEST_DAY or now.hour < DIGEST_HOUR_UTC:
        return result
    dashboard_url = str(
        getattr(email_service.settings, "app_base_url", "") or "https://app.siftentry.com"
    )
    for organization in repo.list_organizations():
        result["checked"] += 1
        stored = repo.get_organization_settings(organization.id) or {}
        notifications = stored.get("notifications") or {}
        if not notifications.get("digest"):
            continue
        last = repo.get_latest_audit_event(organization.id, DIGEST_SENT_EVENT)
        if last and now - _aware(last["created_at"]) < DIGEST_REPEAT_GUARD:
            continue
        try:
            recipients = send_digest_for_organization(
                repo, email_service, organization, now, dashboard_url
            )
        except Exception:
            logger.exception("digest for %s failed", organization.id)
            continue
        if recipients:
            result["sent_orgs"] += 1
            result["recipients"] += recipients
            logger.info(
                "digest sent for %s to %s member(s)", organization.id, recipients
            )
    return result
