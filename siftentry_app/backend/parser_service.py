"""PDF extraction service independent from Streamlit UI state."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..accounting_routing import apply_accounting_route
from ..gst_invoice_parser import looks_like_gst_invoice, parse_gst_invoice
from ..universal_parser import parse_generic_invoice
from .ai_parser import AiExtractorConfig, apply_ai_parser_context
from .extraction_common import locate_field_evidence
from .domain import legacy_payload_to_invoice
from .models import ClientProfile, CorrectionLearningSignal, InvoiceCreate


def extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, str, int]:
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")

    try:
        import fitz

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in document)
        pages = max(1, document.page_count)
        document.close()
        if text.strip():
            return text, "pymupdf", pages
    except Exception:
        pass

    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text, "pypdf", max(1, len(reader.pages))
    except Exception as exc:
        raise ValueError(f"Unable to read the uploaded PDF: {exc}") from exc

    raise ValueError(
        "The PDF contains no extractable text. OCR support will be added in a later extraction worker."
    )


def parse_pdf_invoice(
    filename: str,
    pdf_bytes: bytes,
    organization_id: str,
    legal_names: List[str],
    source_path: str = "",
    parser_mode: str = "auto",
    client_profile: Optional[ClientProfile] = None,
    correction_signals: Optional[List[CorrectionLearningSignal]] = None,
    ai_config: Optional[AiExtractorConfig] = None,
    ai_gate: Optional[Callable[[str, str], bool]] = None,
) -> InvoiceCreate:
    text, engine, pages = extract_pdf_text(pdf_bytes)
    extracted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    normalized_mode = parser_mode.strip().lower()

    use_gst = normalized_mode in {
        "gst",
        "gst/e-invoice",
        "gst/e-invoice adapter",
        "gst_einvoice",
    } or (normalized_mode == "auto" and looks_like_gst_invoice(text))
    payload = None
    if use_gst:
        payload = parse_gst_invoice(
            filename=filename,
            pdf_bytes=pdf_bytes,
            text=text,
            engine=engine,
            pages=pages,
            extracted_at=extracted_at,
        )

    if not payload:
        payload = parse_generic_invoice(
            filename=filename,
            text=text,
            engine=engine,
            pages=pages,
            extracted_at=extracted_at,
        )

    apply_accounting_route(payload, homes=legal_names)

    # Phase B routing: in `auto` mode with a live provider configured, the
    # deterministic parse runs first so the supplier is known, then the gate
    # decides — external AI only for training/unseen formats, never trusted.
    effective_mode = parser_mode
    if (
        normalized_mode == "auto"
        and ai_gate is not None
        and ai_config is not None
        and ai_config.live_provider
    ):
        supplier_name, supplier_tax_id = _supplier_identity(payload)
        if ai_gate(supplier_name, supplier_tax_id):
            effective_mode = "ai"

    apply_ai_parser_context(
        payload,
        parser_mode=effective_mode,
        client_profile=client_profile,
        correction_signals=correction_signals or [],
        ai_config=ai_config,
        document_text=text,
        pdf_bytes=pdf_bytes,
    )
    if effective_mode != parser_mode:
        document = (payload.get("INVOICE", payload) or {}).get("DOCUMENT")
        if isinstance(document, dict):
            document["AI/OCR TRIGGER"] = "training_format"
    invoice_create = legacy_payload_to_invoice(
        payload,
        organization_id=organization_id,
        source_file=filename,
        source_path=source_path,
    )
    invoice_create.evidence = build_parse_evidence(pdf_bytes, invoice_create)
    return invoice_create


def _supplier_identity(payload: Dict[str, Any]) -> Tuple[str, str]:
    """Supplier name + tax id from the parsed payload (same keys domain uses)."""
    invoice = payload.get("INVOICE", payload) or {}
    seller = invoice.get("SELLER", {}) or {}
    name = str(seller.get("NAME") or seller.get("LEGAL NAME") or "").strip()
    tax_id = str(
        seller.get("GSTIN") or seller.get("GSTIN/UIN") or seller.get("TAX ID") or ""
    ).strip()
    return name, tax_id


def build_parse_evidence(pdf_bytes: bytes, invoice) -> list:
    """Locate the parsed values in the PDF text layer -> evidence with real
    page + bounding boxes (normalized 0..1). Free, deterministic, provider-
    independent. Scanned PDFs without a text layer yield no evidence rather
    than fabricated coordinates."""
    from .models import ExtractionEvidence

    targets = {}
    if invoice.invoice_number:
        targets["invoice_number"] = invoice.invoice_number
    if invoice.supplier and invoice.supplier.name:
        targets["supplier.name"] = invoice.supplier.name
    if getattr(invoice.supplier, "tax_id", ""):
        targets["supplier.tax_id"] = invoice.supplier.tax_id
    for field, amount in (
        ("total", invoice.total),
        ("tax_total", invoice.tax_total),
        ("subtotal", invoice.subtotal),
    ):
        if amount:
            targets[field] = f"{amount:.2f}"
    if not targets:
        return []
    try:
        located = locate_field_evidence(pdf_bytes, targets)
    except (OSError, ValueError, RuntimeError):
        # Unreadable/odd PDFs yield no evidence; programming errors surface.
        return []
    evidence = []
    for field, box in located.items():
        if not box:
            continue
        evidence.append(
            ExtractionEvidence(
                field=field,
                value=targets[field],
                page=box["page"],
                snippet=f"Found on page {box['page']}: {targets[field]}",
                confidence=0.95,
                x0=box["x0"],
                y0=box["y0"],
                x1=box["x1"],
                y1=box["y1"],
            )
        )
    return evidence
