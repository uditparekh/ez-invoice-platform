"""Profile-aware AI/OCR parser scaffolding.

This module keeps external intelligence behind a deterministic boundary:
client training profiles and saved corrections can guide extraction review
today, while hosted LLM/OCR providers can plug into the same context later.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib import request as urlrequest
from urllib.error import URLError

from .models import ClientProfile, CorrectionLearningSignal


AI_PARSER_MODES = {
    "ai",
    "ai/ocr",
    "ai_ocr",
    "ai assisted",
    "ai-assisted",
    "ai_assisted",
    "ai/ocr assisted",
    "ocr",
    "llm",
}

AI_PROVIDER_DISABLED = "disabled"
AI_PROVIDER_PROFILE_CONTEXT = "profile_context"
AI_PROVIDER_WEBHOOK = "webhook"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
AI_PROVIDERS = {
    AI_PROVIDER_DISABLED,
    AI_PROVIDER_PROFILE_CONTEXT,
    AI_PROVIDER_WEBHOOK,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OPENAI_COMPATIBLE,
}

# External AI is OFF unless explicitly enabled: without SIFTENTRY_AI_PROVIDER
# set to a live provider (anthropic / openai_compatible / webhook) plus its
# credentials, extraction runs on the free, local profile_context mode —
# no external calls, no cost, no keys required.


@dataclass(frozen=True)
class AiExtractorConfig:
    """Non-secret AI/OCR extraction configuration used by parser workers."""

    provider: str = AI_PROVIDER_PROFILE_CONTEXT
    endpoint: str = ""
    token: str = ""
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 8.0
    max_payload_chars: int = 120_000
    policy: str = "review_only"

    @classmethod
    def from_environment(cls) -> "AiExtractorConfig":
        return cls(
            provider=_normalize_provider(os.getenv("SIFTENTRY_AI_PROVIDER", "")),
            endpoint=os.getenv("SIFTENTRY_AI_EXTRACTOR_URL", "").strip(),
            token=os.getenv("SIFTENTRY_AI_EXTRACTOR_TOKEN", "").strip(),
            api_key=(
                os.getenv("SIFTENTRY_AI_API_KEY", "").strip()
                or os.getenv("ANTHROPIC_API_KEY", "").strip()
                or os.getenv("OPENAI_API_KEY", "").strip()
            ),
            model=os.getenv("SIFTENTRY_AI_MODEL", "").strip(),
            base_url=os.getenv("SIFTENTRY_AI_BASE_URL", "").strip(),
            timeout_seconds=float(os.getenv("SIFTENTRY_AI_TIMEOUT_SECONDS", "8")),
            max_payload_chars=int(os.getenv("SIFTENTRY_AI_MAX_PAYLOAD_CHARS", "120000")),
            policy=os.getenv("SIFTENTRY_AI_POLICY", "review_only").strip() or "review_only",
        )

    @classmethod
    def from_settings(cls, settings: Any) -> "AiExtractorConfig":
        return cls(
            provider=_normalize_provider(getattr(settings, "ai_provider", "")),
            endpoint=str(getattr(settings, "ai_extractor_url", "") or "").strip(),
            token=str(getattr(settings, "ai_extractor_token", "") or "").strip(),
            api_key=str(
                getattr(settings, "ai_api_key", "")
                or os.getenv("SIFTENTRY_AI_API_KEY", "")
                or os.getenv("ANTHROPIC_API_KEY", "")
                or os.getenv("OPENAI_API_KEY", "")
            ).strip(),
            model=str(getattr(settings, "ai_model", "") or "").strip(),
            base_url=str(
                getattr(settings, "ai_base_url", "")
                or os.getenv("SIFTENTRY_AI_BASE_URL", "")
            ).strip(),
            timeout_seconds=float(getattr(settings, "ai_timeout_seconds", 8.0)),
            max_payload_chars=int(getattr(settings, "ai_max_payload_chars", 120_000)),
            policy=str(getattr(settings, "ai_policy", "review_only") or "review_only").strip(),
        )

    @property
    def configured(self) -> bool:
        if self.provider == AI_PROVIDER_DISABLED:
            return False
        if self.provider == AI_PROVIDER_PROFILE_CONTEXT:
            return True
        if self.provider in {AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI_COMPATIBLE}:
            return bool(self.api_key)
        return self.provider == AI_PROVIDER_WEBHOOK and bool(self.endpoint)

    @property
    def live_provider(self) -> bool:
        if self.provider in {AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI_COMPATIBLE}:
            return bool(self.api_key)
        return self.provider == AI_PROVIDER_WEBHOOK and bool(self.endpoint)

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "live_provider": self.live_provider,
            "endpoint_configured": bool(self.endpoint),
            "token_configured": bool(self.token),
            "api_key_configured": bool(self.api_key),
            "base_url": self.base_url,
            "model": self.model
            or (
                "claude-sonnet-4-6"
                if self.provider == AI_PROVIDER_ANTHROPIC
                else "gpt-4o-mini"
                if self.provider == AI_PROVIDER_OPENAI_COMPATIBLE
                else ""
            ),
            "policy": self.policy,
            "timeout_seconds": self.timeout_seconds,
            "max_payload_chars": self.max_payload_chars,
            "mode": (
                "anthropic_llm"
                if self.provider == AI_PROVIDER_ANTHROPIC and self.api_key
                else "openai_compatible_llm"
                if self.provider == AI_PROVIDER_OPENAI_COMPATIBLE and self.api_key
                else "external_webhook"
                if self.live_provider
                else "profile_context_fallback"
                if self.provider == AI_PROVIDER_PROFILE_CONTEXT
                else "disabled"
            ),
        }


def is_ai_parser_mode(parser_mode: str) -> bool:
    return (parser_mode or "").strip().lower() in AI_PARSER_MODES


def apply_ai_parser_context(
    payload: Dict[str, Any],
    *,
    parser_mode: str,
    client_profile: Optional[ClientProfile] = None,
    correction_signals: Optional[List[CorrectionLearningSignal]] = None,
    ai_config: Optional[AiExtractorConfig] = None,
    document_text: str = "",
    pdf_bytes: bytes = b"",
) -> Dict[str, Any]:
    if not is_ai_parser_mode(parser_mode):
        return payload

    invoice = payload.setdefault("INVOICE", payload)
    document = invoice.setdefault("DOCUMENT", {})
    context = build_ai_parser_context(client_profile, correction_signals or [])
    config = ai_config or AiExtractorConfig.from_environment()

    _apply_profile_hints(invoice, client_profile)
    external_result = request_external_ai_suggestions(
        invoice,
        context,
        config=config,
        document_text=document_text,
        pdf_bytes=pdf_bytes,
    )

    base_parser = str(document.get("PARSER") or document.get("ADAPTER") or "Generic")
    document["PARSER"] = "AI/OCR assisted"
    document["BASE PARSER"] = base_parser
    document["AI/OCR MODE"] = "profile_context_v1"
    document["AI/OCR PROVIDER"] = external_result["provider"]
    document["AI/OCR CONFIGURED"] = bool(external_result.get("configured"))
    document["AI/OCR POLICY"] = external_result.get("policy", config.policy)
    if external_result.get("model"):
        document["AI/OCR MODEL"] = external_result["model"]
    if external_result.get("latency_ms") is not None:
        document["AI/OCR LATENCY MS"] = external_result["latency_ms"]
    document["AI PARSER CONTEXT"] = context
    if external_result["suggestions"]:
        document["AI/OCR SUGGESTIONS"] = external_result["suggestions"]
    if external_result["error"]:
        document["AI/OCR ERROR"] = external_result["error"]
    document["PARSER EVALUATION"] = evaluate_parser_payload(
        invoice,
        context=context,
        correction_signals=correction_signals or [],
        external_provider=external_result["provider"],
    )
    return payload


def build_ai_parser_context(
    client_profile: Optional[ClientProfile],
    correction_signals: List[CorrectionLearningSignal],
) -> Dict[str, Any]:
    settings = client_profile.settings if client_profile else None
    training = settings.training_profile if settings else None
    field_counts = Counter(signal.field_path for signal in correction_signals)

    return {
        "profile_id": client_profile.id if client_profile else "",
        "profile_name": client_profile.name if client_profile else "",
        "accounting_system": str(client_profile.accounting_system) if client_profile else "",
        "country_code": settings.country_code if settings else "",
        "default_currency": settings.default_currency if settings else "",
        "invoice_format": settings.invoice_format if settings else "",
        "tax_mode": settings.tax_mode if settings else "",
        "direction": settings.direction if settings else "",
        "posting_mode": str(settings.posting_mode) if settings else "",
        "purchase_ledger": settings.purchase_ledger if settings else "",
        "tax_ledger": settings.tax_ledger if settings else "",
        "tcs_ledger": settings.tcs_ledger if settings else "",
        "round_off_ledger": settings.round_off_ledger if settings else "",
        "stock_item_name": settings.stock_item_name if settings else "",
        "stock_item_hsn": settings.stock_item_hsn if settings else "",
        "stock_item_uom": settings.stock_item_uom if settings else "",
        "godown_name": settings.godown_name if settings else "",
        "item_mapping_count": len(settings.item_mappings) if settings else 0,
        "training": {
            "onboarding_status": training.onboarding_status if training else "",
            "business_process": training.business_process if training else "",
            "expected_fields": training.expected_fields if training else [],
            "sample_invoice_count": len(training.sample_invoices) if training else 0,
            "fields_confirmed_count": (
                sum(1 for sample in training.sample_invoices if sample.fields_confirmed)
                if training
                else 0
            ),
            "extraction_instructions": training.extraction_instructions if training else "",
            "validation_rules": training.validation_rules if training else [],
            "posting_expectations": training.posting_expectations if training else "",
            "llm_ready": training.llm_ready if training else False,
            "llm_policy": training.llm_policy if training else "review_only",
        },
        "correction_learning": {
            "sample_count": len(correction_signals),
            "field_counts": dict(field_counts),
            "top_fields": [field for field, _count in field_counts.most_common(8)],
        },
    }


def evaluate_parser_payload(
    invoice: Dict[str, Any],
    *,
    context: Dict[str, Any],
    correction_signals: List[CorrectionLearningSignal],
    external_provider: str = "not_configured",
) -> Dict[str, Any]:
    expected_fields = context.get("training", {}).get("expected_fields") or [
        "invoice_number",
        "supplier",
        "invoice_date",
        "currency",
        "total",
        "line_items",
    ]
    present_fields: List[str] = []
    missing_fields: List[str] = []
    issues: List[Dict[str, Any]] = []

    for field in expected_fields:
        if _field_present(invoice, field):
            present_fields.append(field)
        else:
            missing_fields.append(field)
            issues.append(
                {
                    "field": field,
                    "severity": "warning",
                    "message": f"{field.replace('_', ' ').title()} was not confidently extracted.",
                    "suggestion": "Review this field before validation or posting.",
                }
            )

    header = invoice.get("INVOICE HEADER", {}) or {}
    payment = (invoice.get("PAYMENT", {}) or {}).get("ELECTRONIC", {}) or {}
    rows = (invoice.get("LINE ITEMS", {}) or {}).get("ROWS", []) or []
    total = _to_float(header.get("INVOICE AMOUNT") or payment.get("AMOUNT"))
    line_total = round(sum(_line_total(row) for row in rows), 2)
    tax_total = _to_float((invoice.get("INVOICE TAX SUMMARY", {}) or {}).get("TOTAL TAX"))

    if total and line_total and abs(total - line_total) > max(1.0, total * 0.02):
        issues.append(
            {
                "field": "line_items",
                "severity": "warning",
                "message": "Line total does not reconcile cleanly with invoice total.",
                "suggestion": "Check whether tax, TCS, freight, or round-off rows need separate mapping.",
                "observed": {"invoice_total": total, "line_total": line_total, "tax_total": tax_total},
            }
        )

    correction_fields = sorted({signal.field_path for signal in correction_signals})
    for field in correction_fields[:8]:
        issues.append(
            {
                "field": field,
                "severity": "info",
                "message": "Past user corrections exist for this field.",
                "suggestion": "Use saved corrections as a learning signal for this vendor/profile.",
            }
        )

    issue_penalty = min(0.7, len([item for item in issues if item["severity"] == "warning"]) * 0.09)
    score = round(max(0.25, 0.92 - issue_penalty), 2)

    return {
        "engine": "profile_context_v1",
        "external_provider": external_provider,
        "score": score,
        "profile_id": context.get("profile_id", ""),
        "profile_name": context.get("profile_name", ""),
        "expected_fields": expected_fields,
        "present_fields": present_fields,
        "missing_fields": missing_fields,
        "issue_count": len(issues),
        "issues": issues,
        "correction_example_count": len(correction_signals),
        "correction_fields": correction_fields,
    }


def request_external_ai_suggestions(
    invoice: Dict[str, Any],
    context: Dict[str, Any],
    *,
    config: Optional[AiExtractorConfig] = None,
    document_text: str = "",
    pdf_bytes: bytes = b"",
) -> Dict[str, Any]:
    resolved = config or AiExtractorConfig.from_environment()
    if resolved.provider == AI_PROVIDER_ANTHROPIC:
        if not resolved.api_key:
            return _ai_result(
                provider=AI_PROVIDER_ANTHROPIC,
                configured=False,
                policy=resolved.policy,
                error="ANTHROPIC_API_KEY is not configured.",
            )
        from .anthropic_extractor import extract_with_anthropic

        outcome = extract_with_anthropic(
            document_text=document_text,
            context=context,
            api_key=resolved.api_key,
            model=resolved.model or "claude-sonnet-4-6",
            timeout_seconds=max(resolved.timeout_seconds, 45.0),
            max_payload_chars=resolved.max_payload_chars,
            pdf_bytes=pdf_bytes,
        )
        return _ai_result(
            provider=AI_PROVIDER_ANTHROPIC,
            configured=True,
            policy=resolved.policy,
            suggestions=outcome["suggestions"],
            model=outcome["model"],
            latency_ms=outcome["latency_ms"],
            error=outcome["error"],
        )
    if resolved.provider == AI_PROVIDER_OPENAI_COMPATIBLE:
        if not resolved.api_key:
            return _ai_result(
                provider=AI_PROVIDER_OPENAI_COMPATIBLE,
                configured=False,
                policy=resolved.policy,
                error="SIFTENTRY_AI_API_KEY is not configured.",
            )
        from .openai_extractor import extract_with_openai_compatible

        outcome = extract_with_openai_compatible(
            document_text=document_text,
            context=context,
            api_key=resolved.api_key,
            base_url=resolved.base_url or "https://api.openai.com/v1",
            model=resolved.model or "gpt-4o-mini",
            timeout_seconds=max(resolved.timeout_seconds, 45.0),
            max_payload_chars=resolved.max_payload_chars,
            pdf_bytes=pdf_bytes,
        )
        return _ai_result(
            provider=AI_PROVIDER_OPENAI_COMPATIBLE,
            configured=True,
            policy=resolved.policy,
            suggestions=outcome["suggestions"],
            model=outcome["model"],
            latency_ms=outcome["latency_ms"],
            error=outcome["error"],
        )
    if resolved.provider == AI_PROVIDER_DISABLED:
        return _ai_result(
            provider=AI_PROVIDER_DISABLED,
            configured=False,
            policy=resolved.policy,
        )
    if resolved.provider == AI_PROVIDER_PROFILE_CONTEXT:
        return _ai_result(
            provider=AI_PROVIDER_PROFILE_CONTEXT,
            configured=True,
            policy=resolved.policy,
        )
    if resolved.provider != AI_PROVIDER_WEBHOOK:
        return _ai_result(
            provider=resolved.provider,
            configured=False,
            policy=resolved.policy,
            error="Unsupported AI/OCR provider.",
        )
    if not resolved.endpoint:
        return _ai_result(
            provider=AI_PROVIDER_WEBHOOK,
            configured=False,
            policy=resolved.policy,
            error="SIFTENTRY_AI_EXTRACTOR_URL is not configured.",
        )

    body = json.dumps(
        _clip_payload(
            {
                "version": "profile_context_v1",
                "mode": "review_suggestions",
                "provider": resolved.provider,
                "policy": resolved.policy,
                "invoice": invoice,
                "context": context,
            },
            max_chars=resolved.max_payload_chars,
        ),
        default=str,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if resolved.token:
        headers["Authorization"] = f"Bearer {resolved.token}"

    try:
        started = time.monotonic()
        req = urlrequest.Request(resolved.endpoint, data=body, headers=headers, method="POST")
        with urlrequest.urlopen(req, timeout=resolved.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        latency_ms = int((time.monotonic() - started) * 1000)
        parsed = json.loads(raw) if raw else {}
        return _ai_result(
            provider=parsed.get("provider") or AI_PROVIDER_WEBHOOK,
            configured=True,
            policy=resolved.policy,
            suggestions=parsed.get("suggestions") or parsed.get("fields") or {},
            model=parsed.get("model") or parsed.get("engine") or "",
            latency_ms=latency_ms,
        )
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        return _ai_result(
            provider=AI_PROVIDER_WEBHOOK,
            configured=resolved.configured,
            policy=resolved.policy,
            error=str(exc),
        )


def _normalize_provider(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    if not normalized:
        return AI_PROVIDER_PROFILE_CONTEXT
    if normalized in {"off", "none", "false"}:
        return AI_PROVIDER_DISABLED
    if normalized in {"profile", "local", "fallback", "profile_context_v1"}:
        return AI_PROVIDER_PROFILE_CONTEXT
    if normalized in {"url", "http", "https", "external"}:
        return AI_PROVIDER_WEBHOOK
    if normalized in {"anthropic", "claude", "claude_api"}:
        return AI_PROVIDER_ANTHROPIC
    if normalized in {
        "openai",
        "openai_compatible",
        "gpt",
        "gemini",
        "groq",
        "deepseek",
        "openrouter",
        "ollama",
        "compatible",
    }:
        return AI_PROVIDER_OPENAI_COMPATIBLE
    return normalized


def _ai_result(
    *,
    provider: str,
    configured: bool,
    policy: str,
    suggestions: Optional[Dict[str, Any]] = None,
    error: str = "",
    model: str = "",
    latency_ms: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "provider": provider,
        "configured": configured,
        "policy": policy,
        "suggestions": suggestions or {},
        "error": error,
        "model": model,
        "latency_ms": latency_ms,
    }


def _clip_payload(value: Any, *, max_chars: int) -> Any:
    """Bound outbound AI requests without changing the original invoice payload."""

    budget = max(4_000, max_chars)
    serialized = json.dumps(value, default=str, ensure_ascii=True)
    if len(serialized) <= budget:
        return value
    return _clip_value(value, budget=max(1_000, budget // 2))


def _clip_value(value: Any, *, budget: int) -> Any:
    if isinstance(value, dict):
        return {key: _clip_value(item, budget=budget) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip_value(item, budget=budget) for item in value[:80]]
    if isinstance(value, str) and len(value) > budget:
        return value[:budget] + "...[truncated]"
    return value


def _apply_profile_hints(
    invoice: Dict[str, Any],
    client_profile: Optional[ClientProfile],
) -> None:
    if not client_profile:
        return

    settings = client_profile.settings
    header = invoice.setdefault("INVOICE HEADER", {})
    payment = invoice.setdefault("PAYMENT", {}).setdefault("ELECTRONIC", {})
    routing = invoice.setdefault("ROUTING", {})
    rows = invoice.setdefault("LINE ITEMS", {}).setdefault("ROWS", [])

    if settings.default_currency and not str(payment.get("CURRENCY") or "").strip():
        payment["CURRENCY"] = settings.default_currency
    if settings.direction in {"inbound", "outbound"}:
        routing["DIRECTION"] = settings.direction
    if settings.purchase_ledger:
        invoice.setdefault("ACCOUNTING PROFILE", {})["PURCHASE LEDGER"] = settings.purchase_ledger
    if settings.tax_ledger:
        invoice.setdefault("ACCOUNTING PROFILE", {})["TAX LEDGER"] = settings.tax_ledger
    if settings.tcs_ledger:
        invoice.setdefault("ACCOUNTING PROFILE", {})["TCS LEDGER"] = settings.tcs_ledger
    if settings.round_off_ledger:
        invoice.setdefault("ACCOUNTING PROFILE", {})["ROUND OFF LEDGER"] = settings.round_off_ledger
    if settings.godown_name:
        invoice.setdefault("ACCOUNTING PROFILE", {})["GODOWN"] = settings.godown_name

    for row in rows:
        description = str(row.get("DESCRIPTION") or "")
        mapping = _best_item_mapping(settings.item_mappings, description, row.get("HSN/SAC"))
        target_item = mapping.target_item_name if mapping else settings.stock_item_name
        target_uom = mapping.target_uom if mapping else settings.stock_item_uom
        target_hsn = mapping.source_hsn_sac if mapping else settings.stock_item_hsn
        purchase_ledger = mapping.purchase_ledger if mapping else settings.purchase_ledger
        tax_ledger = mapping.tax_ledger if mapping else settings.tax_ledger

        if target_item:
            row.setdefault("TARGET ITEM", target_item)
            if _looks_like_noise(description):
                row["DESCRIPTION"] = target_item
        if target_uom and not str(row.get("UOM") or "").strip():
            row["UOM"] = target_uom
        if target_hsn and not str(row.get("HSN/SAC") or "").strip():
            row["HSN/SAC"] = target_hsn
        if purchase_ledger:
            row.setdefault("PURCHASE LEDGER", purchase_ledger)
        if tax_ledger:
            row.setdefault("TAX LEDGER", tax_ledger)
        if mapping and mapping.metadata:
            if mapping.metadata.get("category") and not row.get("CATEGORY"):
                row["CATEGORY"] = mapping.metadata["category"]
            if mapping.metadata.get("gl_code") and not row.get("GL_CODE"):
                row["GL_CODE"] = mapping.metadata["gl_code"]

    if settings.stock_item_name:
        header.setdefault("PROFILE STOCK ITEM", settings.stock_item_name)


def _best_item_mapping(
    mappings: Iterable[Any],
    description: str,
    hsn_sac: Any,
) -> Optional[Any]:
    normalized_description = description.lower()
    normalized_hsn = str(hsn_sac or "").strip()
    for mapping in mappings:
        if mapping.source_hsn_sac and mapping.source_hsn_sac == normalized_hsn:
            return mapping
        needle = mapping.source_description_contains.lower()
        if needle and needle in normalized_description:
            return mapping
    return None


def _field_present(invoice: Dict[str, Any], field: str) -> bool:
    header = invoice.get("INVOICE HEADER", {}) or {}
    seller = invoice.get("SELLER", {}) or {}
    payment = (invoice.get("PAYMENT", {}) or {}).get("ELECTRONIC", {}) or {}
    rows = (invoice.get("LINE ITEMS", {}) or {}).get("ROWS", []) or []
    tax_summary = invoice.get("INVOICE TAX SUMMARY", {}) or {}
    aliases = {
        "invoice_number": [header.get("INVOICE NO."), header.get("INVOICE NUMBER")],
        "supplier": [seller.get("NAME")],
        "vendor": [seller.get("NAME")],
        "invoice_date": [header.get("INVOICE DATE")],
        "due_date": [header.get("DUE DATE")],
        "currency": [payment.get("CURRENCY")],
        "subtotal": [header.get("SUBTOTAL")],
        "tax_total": [tax_summary.get("TOTAL TAX"), tax_summary.get("TAX AMOUNT")],
        "total": [header.get("INVOICE AMOUNT"), payment.get("AMOUNT")],
        "line_items": [rows],
        "hsn_sac": [row.get("HSN/SAC") for row in rows],
        "purchase_order": [header.get("PO NO./CONTRACT NO."), header.get("PO NO.")],
    }
    values = aliases.get(field, [header.get(field.upper()), invoice.get(field.upper())])
    return any(_has_value(value) for value in values)


def _has_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    return value not in (None, "", [], {})


def _line_total(row: Dict[str, Any]) -> float:
    return _to_float(row.get("AMOUNT") or row.get("TOTAL") or row.get("EXTENDED AMOUNT"))


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        cleaned = (
            str(value)
            .replace(",", "")
            .replace("INR", "")
            .replace("USD", "")
            .replace("$", "")
            .strip()
        )
        try:
            return float(cleaned)
        except ValueError:
            return 0.0


def _looks_like_noise(description: str) -> bool:
    cleaned = description.strip()
    if not cleaned:
        return True
    if len(cleaned) <= 3:
        return True
    if cleaned.upper() in {"USD", "INR", "TOTAL", "SUBTOTAL"}:
        return True
    return False
