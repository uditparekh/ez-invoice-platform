"""PDF extraction service independent from Streamlit UI state."""

from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from ..accounting_routing import apply_accounting_route
from ..gst_invoice_parser import looks_like_gst_invoice, parse_gst_invoice
from ..universal_parser import parse_generic_invoice
from .domain import legacy_payload_to_invoice
from .models import InvoiceCreate


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
) -> InvoiceCreate:
    text, engine, pages = extract_pdf_text(pdf_bytes)
    extracted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    normalized_mode = parser_mode.strip().lower()

    use_gst = normalized_mode in {"gst", "gst/e-invoice", "gst/e-invoice adapter"} or (
        normalized_mode == "auto" and looks_like_gst_invoice(text)
    )
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
    return legacy_payload_to_invoice(
        payload,
        organization_id=organization_id,
        source_file=filename,
        source_path=source_path,
    )
