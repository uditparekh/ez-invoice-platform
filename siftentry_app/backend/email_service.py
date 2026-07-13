"""Email delivery for invitation and password reset flows."""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import List, Optional

from .settings import ApiSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveredEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: str


class EmailDeliveryError(RuntimeError):
    """Raised when a required email cannot be delivered."""


class EmailService:
    """Small provider boundary for pilot-safe email delivery.

    `memory` is used by tests, `log` is useful for local development, `smtp`
    works with providers that accept SMTP relay, and `resend` sends through
    Resend's HTTPS API — the right choice on hosts (such as Railway) that
    block outbound SMTP ports.
    """

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.outbox: List[DeliveredEmail] = []

    def send_invitation(
        self,
        *,
        to_email: str,
        organization_name: str,
        invited_by_name: str,
        role: str,
        invitation_url: str,
        expires_at: datetime,
    ) -> DeliveredEmail:
        subject = f"Join {organization_name} on SiftEntry"
        text_body = (
            f"{invited_by_name or 'A workspace admin'} invited you to join "
            f"{organization_name} on SiftEntry as {role}.\n\n"
            f"Accept your invite: {invitation_url}\n\n"
            f"This invite expires on {expires_at:%d %b %Y, %H:%M UTC}."
        )
        html_body = _basic_email_html(
            eyebrow="Workspace invite",
            title=f"Join {escape(organization_name)} on SiftEntry",
            body=(
                f"{escape(invited_by_name or 'A workspace admin')} invited you "
                f"as <strong>{escape(role)}</strong>."
            ),
            action_label="Accept invite",
            action_url=invitation_url,
            footer=f"This invite expires on {expires_at:%d %b %Y, %H:%M UTC}.",
        )
        return self._deliver(to_email, subject, text_body, html_body)

    def send_password_reset(
        self,
        *,
        to_email: str,
        full_name: str,
        reset_url: str,
        expires_at: datetime,
    ) -> DeliveredEmail:
        subject = "Reset your SiftEntry password"
        greeting = full_name.strip() or "there"
        text_body = (
            f"Hi {greeting},\n\n"
            "Use this link to reset your SiftEntry password:\n\n"
            f"{reset_url}\n\n"
            f"This link expires on {expires_at:%d %b %Y, %H:%M UTC}. "
            "If you did not request it, you can ignore this email."
        )
        html_body = _basic_email_html(
            eyebrow="Password reset",
            title="Reset your SiftEntry password",
            body=(
                f"Hi {escape(greeting)}, use this one-time link to set a new "
                "password for your workspace."
            ),
            action_label="Reset password",
            action_url=reset_url,
            footer=(
                f"This link expires on {expires_at:%d %b %Y, %H:%M UTC}. "
                "If you did not request it, you can ignore this email."
            ),
        )
        return self._deliver(to_email, subject, text_body, html_body)

    def _deliver(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> DeliveredEmail:
        delivered = DeliveredEmail(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        provider = self.settings.email_provider
        if provider == "memory":
            self.outbox.append(delivered)
            return delivered
        if provider == "log":
            logger.info("Email prepared for %s: %s\n%s", to_email, subject, text_body)
            self.outbox.append(delivered)
            return delivered
        if provider == "disabled":
            self.outbox.append(delivered)
            return delivered
        if provider == "smtp":
            self._send_smtp(delivered)
            self.outbox.append(delivered)
            return delivered
        if provider == "resend":
            self._send_resend(delivered)
            self.outbox.append(delivered)
            return delivered
        raise EmailDeliveryError(f"Unsupported email provider: {provider}")

    def _send_resend(self, delivered: DeliveredEmail) -> None:
        """Send through Resend's HTTPS API (https://api.resend.com/emails).

        Preferred on hosts such as Railway that restrict outbound SMTP ports;
        HTTPS on port 443 is never blocked.
        """
        settings = self.settings
        if not settings.resend_api_key:
            raise EmailDeliveryError("Resend API key is not configured.")
        payload: dict = {
            "from": settings.email_from,
            "to": [delivered.to_email],
            "subject": delivered.subject,
            "text": delivered.text_body,
            "html": delivered.html_body,
        }
        if settings.email_reply_to:
            payload["reply_to"] = settings.email_reply_to
        request = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=settings.smtp_timeout_seconds
            ) as response:
                if response.status not in (200, 201):
                    raise EmailDeliveryError(
                        f"Resend API returned status {response.status}."
                    )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                body = json.loads(exc.read().decode("utf-8", errors="replace"))
                detail = str(body.get("message", ""))[:200]
            except Exception:  # noqa: BLE001 - best-effort error detail
                pass
            logger.error("Resend API error %s: %s", exc.code, detail)
            raise EmailDeliveryError(
                f"Resend API error {exc.code}: {detail or 'request rejected'}."
            ) from exc
        except OSError as exc:
            logger.error("Resend API connection failed: %s", exc)
            raise EmailDeliveryError("Email delivery failed.") from exc

    def _send_smtp(self, delivered: DeliveredEmail) -> None:
        settings = self.settings
        if not settings.smtp_host:
            raise EmailDeliveryError("SMTP host is not configured.")
        message = EmailMessage()
        message["Subject"] = delivered.subject
        message["From"] = settings.email_from
        message["To"] = delivered.to_email
        if settings.email_reply_to:
            message["Reply-To"] = settings.email_reply_to
        message.set_content(delivered.text_body)
        message.add_alternative(delivered.html_body, subtype="html")
        try:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username or settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Email delivery failed.") from exc


def _basic_email_html(
    *,
    eyebrow: str,
    title: str,
    body: str,
    action_label: str,
    action_url: str,
    footer: Optional[str] = None,
) -> str:
    escaped_action_url = escape(action_url, quote=True)
    footer_html = f"<p class='footer'>{escape(footer)}</p>" if footer else ""
    return f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{ margin: 0; background: #f8fafc; color: #08111f; font-family: Inter, Arial, sans-serif; }}
      .wrap {{ max-width: 560px; margin: 0 auto; padding: 32px 20px; }}
      .card {{ background: #ffffff; border: 1px solid #e6eaf2; border-radius: 18px; padding: 28px; }}
      .eyebrow {{ color: #06b6d4; font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }}
      h1 {{ font-size: 28px; line-height: 1.15; margin: 12px 0; }}
      p {{ color: #667085; font-size: 15px; line-height: 1.55; }}
      a.button {{ display: inline-block; margin-top: 18px; background: #4f46e5; color: #fff; padding: 13px 18px; border-radius: 12px; font-weight: 800; text-decoration: none; }}
      .footer {{ margin-top: 22px; font-size: 12px; color: #98a2b3; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="eyebrow">{escape(eyebrow)}</div>
        <h1>{title}</h1>
        <p>{body}</p>
        <a class="button" href="{escaped_action_url}">{escape(action_label)}</a>
        {footer_html}
      </div>
    </div>
  </body>
</html>
"""
