"""Anthropic (Claude) adapter — transport only.

All extraction intelligence (prompt, briefing, shaping, evidence) lives in
extraction_common; this module speaks the Anthropic Messages API dialect.
API key from ANTHROPIC_API_KEY; never logged, never persisted.
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

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 2000


def extract_with_anthropic(
    *,
    document_text: str,
    context: Dict[str, Any],
    api_key: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = 45.0,
    max_payload_chars: int = 120_000,
    pdf_bytes: bytes = b"",
) -> Dict[str, Any]:
    if not api_key:
        return _outcome(model, error="ANTHROPIC_API_KEY is not configured.")
    if not document_text.strip():
        return _outcome(model, error="No extractable text to send to the AI provider.")

    body = json.dumps(
        {
            "model": model or DEFAULT_MODEL,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": build_user_content(
                        context, document_text, max_payload_chars
                    ),
                }
            ],
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    try:
        started = time.monotonic()
        req = urlrequest.Request(
            ANTHROPIC_API_URL, data=body, headers=headers, method="POST"
        )
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        latency_ms = int((time.monotonic() - started) * 1000)
    except (OSError, URLError, TimeoutError) as exc:
        return _outcome(model, error=str(exc))

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _outcome(model, error=f"Anthropic response was not JSON: {exc}")
    if envelope.get("type") == "error":
        detail = (envelope.get("error") or {}).get("message", "unknown error")
        return _outcome(model, latency_ms=latency_ms, error=f"Anthropic API error: {detail}")

    text = "".join(
        block.get("text", "")
        for block in envelope.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
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
