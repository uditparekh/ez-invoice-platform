import json

from siftentry_app.backend.ai_parser import (
    AI_PROVIDER_DISABLED,
    AI_PROVIDER_PROFILE_CONTEXT,
    AI_PROVIDER_WEBHOOK,
    AiExtractorConfig,
    request_external_ai_suggestions,
)


def test_ai_extractor_config_status_modes():
    profile_context = AiExtractorConfig(provider=AI_PROVIDER_PROFILE_CONTEXT)
    assert profile_context.status()["mode"] == "profile_context_fallback"
    assert profile_context.status()["configured"] is True
    assert profile_context.status()["live_provider"] is False

    disabled = AiExtractorConfig(provider=AI_PROVIDER_DISABLED)
    assert disabled.status()["mode"] == "disabled"
    assert disabled.status()["configured"] is False

    webhook = AiExtractorConfig(
        provider=AI_PROVIDER_WEBHOOK,
        endpoint="https://extractor.example.test/run",
        token="secret-token",
    )
    status = webhook.status()
    assert status["mode"] == "external_webhook"
    assert status["configured"] is True
    assert status["token_configured"] is True


def test_webhook_ai_provider_normalizes_result(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "provider": "fixture-llm",
                    "model": "invoice-model-v1",
                    "suggestions": {
                        "invoice_number": "INV-100",
                        "supplier": "Example Supplier",
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        "siftentry_app.backend.ai_parser.urlrequest.urlopen",
        fake_urlopen,
    )

    result = request_external_ai_suggestions(
        {"INVOICE HEADER": {"INVOICE NO.": ""}},
        {"profile_id": "profile-1"},
        config=AiExtractorConfig(
            provider=AI_PROVIDER_WEBHOOK,
            endpoint="https://extractor.example.test/run",
            token="secret-token",
            timeout_seconds=3,
            policy="review_only",
        ),
    )

    assert captured["timeout"] == 3
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["body"]["mode"] == "review_suggestions"
    assert result["provider"] == "fixture-llm"
    assert result["model"] == "invoice-model-v1"
    assert result["suggestions"]["invoice_number"] == "INV-100"
    assert result["error"] == ""
