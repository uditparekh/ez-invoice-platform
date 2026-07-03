"""OpenAI-compatible adapter — transport only.

One adapter, many brains: OpenAI itself, Google Gemini's compatible
endpoint, Groq, DeepSeek, OpenRouter, and local models via Ollama all
speak the /chat/completions dialect. Point SIFTENTRY_AI_BASE_URL at any
of them; the extraction intelligence in extraction_common is identical.

Key from SIFTENTRY_AI_API_KEY (or OPENAI_API_KEY); never logged or persisted.
Local servers (Ollama) typically need no key — pass anything non-empty.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict
from urllib import request as urlrequest
from urllib.error import URLError

from .extraction_common import (
    SYSTEM_PROMPT,
    attach_evidence,
    build_user_content,
    parse_json_block,
    shape_suggestions,
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_OUTPUT_TOKENS = 2000


def extract_with_openai_compatible(
    *,
    document_text: str,
    context: Dict[str, Any],
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = 45.0,
    max_payload_chars: int = 120_000,
    pdf_bytes: bytes = b"",
) -> Dict[str, Any]:
    if not api_key:
        return _outcome(model, error="SIFTENTRY_AI_API_KEY is not configured.")
    if not document_text.strip():
        return _outcome(model, error="No extractable text to send to the AI provider.")

    endpoint = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model or DEFAULT_MODEL,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_content(
                        context, document_text, max_payload_chars
                    ),
                },
            ],
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        started = time.monotonic()
        req = urlrequest.Request(endpoint, data=body, headers=headers, method="POST")
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        latency_ms = int((time.monotonic() - started) * 1000)
    except (OSError, URLError, TimeoutError) as exc:
        return _outcome(model, error=str(exc))

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _outcome(model, error=f"Provider response was not JSON: {exc}")
    if envelope.get("error"):
        detail = envelope["error"].get("message", "unknown error")
        return _outcome(model, latency_ms=latency_ms, error=f"Provider API error: {detail}")

    choices = envelope.get("choices") or []
    text = (
        (choices[0].get("message") or {}).get("content", "") if choices else ""
    )
    parsed, parse_error = parse_json_block(text)
    if parse_error:
        return _outcome(model, latency_ms=latency_ms, error=parse_error)

    suggestions = shape_suggestions(parsed)
    if pdf_bytes:
        attach_evidence(suggestions, pdf_bytes)
    return {
        "suggestions": suggestions,
        "model": envelope.get("model") or model or DEFAULT_MODEL,
        "latency_ms": latency_ms,
        "error": "",
    }


def _outcome(model: str, *, latency_ms: Any = None, error: str = "") -> Dict[str, Any]:
    return {"suggestions": {}, "model": model or DEFAULT_MODEL, "latency_ms": latency_ms, "error": error}
