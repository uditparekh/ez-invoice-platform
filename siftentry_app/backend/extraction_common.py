"""Provider-agnostic extraction core.

Everything that does NOT depend on which AI vendor answers lives here:
the field contract, the system prompt, the client-context briefing,
response shaping, and text-layer evidence location. Adapters
(anthropic_extractor, openai_extractor, or any future provider) handle
transport only — every brain eats identical food. Swapping providers is
an environment-variable change, never a code change.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

EXTRACTION_FIELDS = (
    "invoice_number",
    "invoice_date",
    "due_date",
    "supplier_name",
    "supplier_tax_id",
    "currency",
    "subtotal",
    "tax_total",
    "total",
)

SYSTEM_PROMPT = """You are SiftEntry's invoice extraction specialist. You read supplier \
invoice text and return structured field values for accounts-payable posting.

Rules:
- Return ONLY a JSON object, no prose, no markdown fences.
- Shape: {"fields": {<name>: {"value": <string>, "confidence": <0..1>, "reason": <short string>}}, \
"lines": [{"description": str, "quantity": str, "uom": str, "unit_price": str, "amount": str, \
"hsn_sac": str, "confidence": <0..1>}]}
- Field names: invoice_number, invoice_date (YYYY-MM-DD), due_date (YYYY-MM-DD), supplier_name, \
supplier_tax_id, currency (ISO 4217), subtotal, tax_total, total. Amounts as plain numbers \
without thousands separators or currency symbols.
- Omit a field entirely if it is not present in the document; never invent values.
- Use the client context: expected fields, extraction instructions, tax mode, and the \
correction-learning summary tell you what this client's reviewers repeatedly fix — be extra \
careful on those fields and say so in the reason.
- For India GST invoices: supplier_tax_id is the GSTIN; tax_total is the sum of IGST or \
CGST+SGST; verify subtotal + tax_total reconciles with total and lower confidence if not."""



def parse_json_block(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse the model's JSON output, tolerating accidental code fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned), ""
    except json.JSONDecodeError as exc:
        return {}, f"Model output was not valid JSON: {exc}"


def build_user_content(
    context: Dict[str, Any],
    document_text: str,
    max_payload_chars: int,
) -> str:
    """The briefing package: identical for every provider."""
    return json.dumps(
        {
            "client_context": context,
            "document_text": document_text[:max_payload_chars],
        },
        ensure_ascii=False,
        default=str,
    )


def shape_suggestions(parsed: Dict[str, Any]) -> Dict[str, Any]:
    suggestions: Dict[str, Any] = {}
    fields = parsed.get("fields") or {}
    for name in EXTRACTION_FIELDS:
        entry = fields.get(name)
        if not isinstance(entry, dict):
            continue
        value = str(entry.get("value", "")).strip()
        if not value:
            continue
        suggestions[name] = {
            "value": value,
            "confidence": _clamp_confidence(entry.get("confidence")),
            "reason": str(entry.get("reason", "")).strip()[:300],
        }
    lines = parsed.get("lines")
    if isinstance(lines, list) and lines:
        suggestions["lines"] = [
            {
                "description": str(line.get("description", "")).strip(),
                "quantity": str(line.get("quantity", "")).strip(),
                "uom": str(line.get("uom", "")).strip(),
                "unit_price": str(line.get("unit_price", "")).strip(),
                "amount": str(line.get("amount", "")).strip(),
                "hsn_sac": str(line.get("hsn_sac", "")).strip(),
                "confidence": _clamp_confidence(line.get("confidence")),
            }
            for line in lines[:50]
            if isinstance(line, dict) and str(line.get("description", "")).strip()
        ]
    return suggestions


def _clamp_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def attach_evidence(suggestions: Dict[str, Any], pdf_bytes: bytes) -> None:
    """Locate each suggested value in the PDF text layer → normalized bbox."""
    targets = {
        name: entry["value"]
        for name, entry in suggestions.items()
        if isinstance(entry, dict) and entry.get("value")
    }
    if not targets:
        return
    evidence = locate_field_evidence(pdf_bytes, targets)
    for name, box in evidence.items():
        if box and isinstance(suggestions.get(name), dict):
            suggestions[name]["evidence"] = box


def locate_field_evidence(
    pdf_bytes: bytes,
    targets: Dict[str, str],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """For each target value, find its bounding box in the PDF text layer.

    Returns {field: {page, x0, y0, x1, y1} | None} with coordinates normalized
    to 0..1 of the page size — renderer-independent, ready for a pdf.js
    highlight layer. Scanned PDFs without a text layer yield None (honest).
    """
    results: Dict[str, Optional[Dict[str, Any]]] = {name: None for name in targets}
    try:
        import fitz  # PyMuPDF — already an API dependency via parser_service
    except ImportError:
        return results

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return results

    try:
        pages_words: List[Tuple[int, float, float, List[Tuple[float, float, float, float, str]]]] = []
        for page_index in range(document.page_count):
            page = document[page_index]
            width, height = float(page.rect.width) or 1.0, float(page.rect.height) or 1.0
            words = [
                (word[0], word[1], word[2], word[3], _normalize_token(word[4]))
                for word in page.get_text("words")
            ]
            pages_words.append((page_index, width, height, words))

        for name, raw_target in targets.items():
            target = _normalize_token(raw_target)
            if not target:
                continue
            for page_index, width, height, words in pages_words:
                box = _find_in_words(words, target)
                if box:
                    x0, y0, x1, y1 = box
                    results[name] = {
                        "page": page_index + 1,
                        "x0": round(x0 / width, 4),
                        "y0": round(y0 / height, 4),
                        "x1": round(x1 / width, 4),
                        "y1": round(y1 / height, 4),
                    }
                    break
    finally:
        document.close()
    return results


def _normalize_token(value: str) -> str:
    return re.sub(r"[\s,]", "", str(value)).lower()


def _find_in_words(
    words: List[Tuple[float, float, float, float, str]],
    target: str,
) -> Optional[Tuple[float, float, float, float]]:
    """Slide a window of consecutive words; match when the joined, normalized
    text contains the target. Returns the union bbox of the matched span."""
    count = len(words)
    for start in range(count):
        joined = ""
        for end in range(start, min(start + 12, count)):
            joined += words[end][4]
            if target in joined:
                span = words[start : end + 1]
                return (
                    min(word[0] for word in span),
                    min(word[1] for word in span),
                    max(word[2] for word in span),
                    max(word[3] for word in span),
                )
            if len(joined) > len(target) + 24:
                break
    return None
