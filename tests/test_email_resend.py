"""Tests for the Resend HTTPS email provider."""

import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from siftentry_app.backend.email_service import EmailDeliveryError, EmailService
from siftentry_app.backend.settings import ApiSettings


def _settings(**overrides) -> ApiSettings:
    values = {
        "database_url": "sqlite:///./qa-email.db",
        "database_path": "./qa-email.db",
        "upload_directory": "./qa-email-uploads",
        "max_upload_bytes": 1024,
        "cors_origins": [],
        "email_provider": "resend",
        "email_from": "SiftEntry <no-reply@siftentry.test>",
        "resend_api_key": "re_test_key",
    }
    values.update(overrides)
    return ApiSettings(**values)


def _expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_resend_provider_posts_expected_payload(monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = EmailService(_settings())

    delivered = service.send_password_reset(
        to_email="owner@example.test",
        full_name="Owner",
        reset_url="https://app.siftentry.test/reset-password?token=abc",
        expires_at=_expiry(),
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_test_key"
    assert captured["content_type"] == "application/json"
    assert captured["payload"]["from"] == "SiftEntry <no-reply@siftentry.test>"
    assert captured["payload"]["to"] == ["owner@example.test"]
    assert "reset-password?token=abc" in captured["payload"]["text"]
    assert delivered.to_email == "owner@example.test"
    assert service.outbox and service.outbox[0].subject


def test_resend_provider_requires_api_key():
    service = EmailService(_settings(resend_api_key=""))
    with pytest.raises(EmailDeliveryError, match="Resend API key"):
        service.send_password_reset(
            to_email="owner@example.test",
            full_name="Owner",
            reset_url="https://app.siftentry.test/reset-password?token=abc",
            expires_at=_expiry(),
        )


def test_resend_provider_surfaces_api_errors(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=422,
            msg="Unprocessable",
            hdrs=None,
            fp=io.BytesIO(b'{"message": "Invalid `from` address"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = EmailService(_settings())

    with pytest.raises(EmailDeliveryError, match="422"):
        service.send_password_reset(
            to_email="owner@example.test",
            full_name="Owner",
            reset_url="https://app.siftentry.test/reset-password?token=abc",
            expires_at=_expiry(),
        )


def test_resend_provider_wraps_connection_failures(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise OSError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = EmailService(_settings())

    with pytest.raises(EmailDeliveryError, match="Email delivery failed"):
        service.send_invitation(
            to_email="clerk@example.test",
            organization_name="QA Org",
            invited_by_name="Owner",
            role="accountant",
            invitation_url="https://app.siftentry.test/invite?token=xyz",
            expires_at=_expiry(),
        )
