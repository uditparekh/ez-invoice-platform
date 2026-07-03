"""Tests for the first-party Anthropic extraction provider (Step 11)."""

import io
import json
from pathlib import Path

from siftentry_app.backend.ai_parser import (
    AiExtractorConfig,
    request_external_ai_suggestions,
)
from siftentry_app.backend.extraction_common import locate_field_evidence


def make_invoice_pdf() -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 80), "TAX INVOICE", fontsize=14)
    page.insert_text((72, 120), "Invoice No: 2620002662", fontsize=11)
    page.insert_text((72, 140), "Supplier: Madelin Enterprises Pvt Ltd", fontsize=11)
    page.insert_text((72, 180), "TOTAL: INR 633,912.00", fontsize=12)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_locate_field_evidence_finds_normalized_bboxes():
    pdf_bytes = make_invoice_pdf()
    evidence = locate_field_evidence(
        pdf_bytes,
        {
            "invoice_number": "2620002662",
            "total": "633,912.00",
            "missing": "NOT-ON-THE-PAGE",
        },
    )
    box = evidence["invoice_number"]
    assert box is not None and box["page"] == 1
    assert 0 <= box["x0"] < box["x1"] <= 1
    assert 0 <= box["y0"] < box["y1"] <= 1
    assert evidence["total"] is not None  # comma-insensitive match
    assert evidence["missing"] is None  # honest: no fabricated evidence


def test_anthropic_provider_parses_model_output(monkeypatch):
    pdf_bytes = make_invoice_pdf()
    model_json = {
        "fields": {
            "invoice_number": {
                "value": "2620002662",
                "confidence": 0.98,
                "reason": "Labeled 'Invoice No' in header",
            },
            "total": {"value": "633912.00", "confidence": 0.95, "reason": "TOTAL line"},
        },
        "lines": [
            {
                "description": "PTA SWEEP",
                "quantity": "23940",
                "uom": "KGS",
                "unit_price": "22.00",
                "amount": "526680.00",
                "hsn_sac": "3907",
                "confidence": 0.9,
            }
        ],
    }
    fake_envelope = json.dumps(
        {"content": [{"type": "text", "text": json.dumps(model_json)}]}
    ).encode("utf-8")

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        assert "api.anthropic.com" in req.full_url
        assert req.get_header("X-api-key") == "test-key"
        sent = json.loads(req.data.decode("utf-8"))
        # Client context (profile + learned corrections) must reach the model.
        user_payload = json.loads(sent["messages"][0]["content"])
        assert user_payload["client_context"]["profile_name"] == "Neel Enterprise"
        assert "2620002662" in user_payload["document_text"]
        return FakeResponse(fake_envelope)

    import siftentry_app.backend.anthropic_extractor as extractor

    monkeypatch.setattr(extractor.urlrequest, "urlopen", fake_urlopen)

    config = AiExtractorConfig(provider="anthropic", api_key="test-key")
    result = request_external_ai_suggestions(
        {"INVOICE": {}},
        {"profile_name": "Neel Enterprise"},
        config=config,
        document_text="Invoice No: 2620002662 TOTAL 633,912.00",
        pdf_bytes=pdf_bytes,
    )
    assert result["provider"] == "anthropic"
    assert result["configured"] is True
    assert result["error"] == ""
    assert result["suggestions"]["invoice_number"]["value"] == "2620002662"
    assert result["suggestions"]["invoice_number"]["confidence"] == 0.98
    # Evidence located locally from the PDF text layer, not from the model.
    assert result["suggestions"]["invoice_number"]["evidence"]["page"] == 1
    assert result["suggestions"]["lines"][0]["description"] == "PTA SWEEP"


def test_anthropic_without_key_degrades_clearly():
    config = AiExtractorConfig(provider="anthropic", api_key="")
    result = request_external_ai_suggestions(
        {"INVOICE": {}}, {}, config=config, document_text="anything"
    )
    assert result["configured"] is False
    assert "ANTHROPIC_API_KEY" in result["error"]
    assert result["suggestions"] == {}


def test_provider_normalization_and_status():
    config = AiExtractorConfig(provider="claude", api_key="k")
    # from_environment normalizes; direct construction keeps raw — normalize here:
    from siftentry_app.backend.ai_parser import _normalize_provider

    assert _normalize_provider("claude") == "anthropic"
    assert _normalize_provider("Anthropic") == "anthropic"
    status = AiExtractorConfig(provider="anthropic", api_key="k").status()
    assert status["configured"] is True
    assert status["live_provider"] is True
    assert status["mode"] == "anthropic_llm"
    assert status["api_key_configured"] is True
    assert config.provider  # silence unused warning
