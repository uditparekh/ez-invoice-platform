"""Explainable invoice review checks for accountant-facing workflows."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Iterable, List, Optional

from .models import (
    DetectedInvoiceProfile,
    ExtractionEvidence,
    Invoice,
    InvoiceReviewField,
    InvoiceReviewInsight,
    InvoiceReviewResult,
    InvoiceReviewSeverity,
    ProfileRecommendationResult,
)
from .profile_recommendation import detect_invoice_profile


FIELD_LABELS = {
    "invoice_number": "Invoice number",
    "supplier.name": "Supplier",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "currency": "Currency",
    "total": "Total",
    "tax_total": "Tax total",
    "lines": "Line items",
}


def build_invoice_review(
    invoice: Invoice,
    profile_result: Optional[ProfileRecommendationResult] = None,
) -> InvoiceReviewResult:
    detected = profile_result.detected if profile_result else detect_invoice_profile(invoice)
    evidence = list(invoice.evidence or [])
    fields = [
        _review_required_text(
            invoice,
            "invoice_number",
            invoice.invoice_number,
            evidence,
            suspicious_values={"invoice", "tax invoice", "bill"},
            suspicious_issue="The parsed value looks like a document title, not the actual invoice number.",
            suspicious_suggestion="Confirm the invoice number from the supplier header before posting.",
        ),
        _review_required_text(
            invoice,
            "supplier.name",
            invoice.supplier.name,
            evidence,
            suspicious_tokens=("tel:", "email:", "phone:", "www.", "@"),
            suspicious_issue="The supplier value includes contact details, so the parser may have captured the wrong text block.",
            suspicious_suggestion="Replace this with the supplier legal name from the invoice.",
        ),
        _review_date(invoice, "invoice_date", invoice.invoice_date, evidence),
        _review_date(invoice, "due_date", invoice.due_date, evidence, required=False),
        _review_currency(invoice, detected, evidence),
        _review_amount(invoice, "total", invoice.total, evidence),
        _review_amount(invoice, "tax_total", invoice.tax_total, evidence, required=False),
        _review_lines(invoice, evidence),
    ]

    insights = _build_insights(invoice, fields, detected, profile_result)
    suggested_patch = _suggest_patch(invoice, detected, fields)
    needs_attention = sum(
        1 for field in fields if field.severity != InvoiceReviewSeverity.OK
    ) + sum(1 for insight in insights if insight.severity != InvoiceReviewSeverity.OK)
    field_scores = [field.confidence for field in fields if field.confidence is not None]
    base_score = sum(field_scores) / len(field_scores) if field_scores else 0.0
    penalty = min(0.5, needs_attention * 0.06)
    overall_score = max(0.0, min(1.0, round(base_score - penalty, 2)))

    recommended_profile_id = None
    profile_reasons: List[str] = []
    if profile_result and profile_result.recommendations:
        top = profile_result.recommendations[0]
        recommended_profile_id = profile_result.auto_profile_id or top.profile.id
        profile_reasons = top.reasons

    return InvoiceReviewResult(
        invoice_id=invoice.id,
        overall_score=overall_score,
        needs_attention=needs_attention,
        fields=fields,
        insights=insights,
        suggested_patch=suggested_patch,
        detected=detected,
        recommended_profile_id=recommended_profile_id,
        profile_reasons=profile_reasons,
    )


def _review_required_text(
    invoice: Invoice,
    field_path: str,
    value: str,
    evidence: List[ExtractionEvidence],
    suspicious_values: Optional[set[str]] = None,
    suspicious_tokens: Iterable[str] = (),
    suspicious_issue: str = "",
    suspicious_suggestion: str = "",
) -> InvoiceReviewField:
    clean = (value or "").strip()
    field_evidence = _field_evidence(evidence, field_path, clean)
    confidence = _confidence(invoice, field_evidence, clean)
    if not clean:
        return _field(
            field_path,
            clean,
            confidence=0.12,
            severity=InvoiceReviewSeverity.ERROR,
            issue=f"{FIELD_LABELS[field_path]} was not found.",
            suggestion=f"Enter the {FIELD_LABELS[field_path].lower()} from the PDF.",
            evidence=field_evidence,
        )

    lower = clean.lower()
    if suspicious_values and lower in suspicious_values:
        return _field(
            field_path,
            clean,
            confidence=min(confidence, 0.35),
            severity=InvoiceReviewSeverity.REVIEW,
            issue=suspicious_issue,
            suggestion=suspicious_suggestion,
            evidence=field_evidence,
        )
    if any(token in lower for token in suspicious_tokens):
        return _field(
            field_path,
            clean,
            confidence=min(confidence, 0.42),
            severity=InvoiceReviewSeverity.REVIEW,
            issue=suspicious_issue,
            suggestion=suspicious_suggestion,
            evidence=field_evidence,
        )
    return _field(field_path, clean, confidence=confidence, evidence=field_evidence)


def _review_date(
    invoice: Invoice,
    field_path: str,
    value: str,
    evidence: List[ExtractionEvidence],
    required: bool = True,
) -> InvoiceReviewField:
    clean = (value or "").strip()
    field_evidence = _field_evidence(evidence, field_path, clean)
    confidence = _confidence(invoice, field_evidence, clean)
    if not clean and required:
        return _field(
            field_path,
            clean,
            confidence=0.15,
            severity=InvoiceReviewSeverity.ERROR,
            issue=f"{FIELD_LABELS[field_path]} was not found.",
            suggestion="Select the date shown in the invoice header.",
            evidence=field_evidence,
        )
    if not clean:
        return _field(
            field_path,
            clean,
            confidence=0.45,
            severity=InvoiceReviewSeverity.REVIEW,
            issue="No due date was found.",
            suggestion="Use the invoice date only if payment terms are immediate.",
            evidence=field_evidence,
        )
    if _looks_like_date(clean):
        return _field(field_path, clean, confidence=confidence, evidence=field_evidence)
    return _field(
        field_path,
        clean,
        confidence=min(confidence, 0.5),
        severity=InvoiceReviewSeverity.REVIEW,
        issue="The date format could not be normalized confidently.",
        suggestion="Confirm the date against the PDF before approving.",
        evidence=field_evidence,
    )


def _review_currency(
    invoice: Invoice,
    detected: DetectedInvoiceProfile,
    evidence: List[ExtractionEvidence],
) -> InvoiceReviewField:
    clean = (invoice.currency or "USD").strip().upper()
    field_evidence = _field_evidence(evidence, "currency", clean)
    confidence = _confidence(invoice, field_evidence, clean)
    if clean == detected.currency:
        return _field("currency", clean, confidence=confidence, evidence=field_evidence)
    return _field(
        "currency",
        clean,
        confidence=min(confidence, 0.62),
        severity=InvoiceReviewSeverity.REVIEW,
        issue=f"Detected invoice profile suggests {detected.currency}, but the parsed currency is {clean}.",
        suggestion=f"Change currency to {detected.currency} if the PDF uses that currency.",
        evidence=field_evidence,
    )


def _review_amount(
    invoice: Invoice,
    field_path: str,
    value: float,
    evidence: List[ExtractionEvidence],
    required: bool = True,
) -> InvoiceReviewField:
    clean = _money_text(value, invoice.currency)
    field_evidence = _field_evidence(evidence, field_path, clean)
    if required and value <= 0:
        return _field(
            field_path,
            clean,
            confidence=0.18,
            severity=InvoiceReviewSeverity.ERROR,
            issue=f"{FIELD_LABELS[field_path]} is missing or zero.",
            suggestion="Enter the amount payable from the invoice totals section.",
            evidence=field_evidence,
        )
    line_total = round(sum(line.total_amount or line.net_amount for line in invoice.lines), 2)
    if field_path == "total" and value > 0 and line_total > 0:
        tolerance = max(1.0, abs(value) * 0.03)
        if abs(line_total - value) > tolerance:
            return _field(
                field_path,
                clean,
                confidence=0.56,
                severity=InvoiceReviewSeverity.REVIEW,
                issue="Invoice total does not match the extracted line-item total.",
                suggestion="Review the line items and totals. The parser may have captured footer or bank-detail rows.",
                evidence=field_evidence,
            )
    return _field(field_path, clean, confidence=_confidence(invoice, field_evidence, clean), evidence=field_evidence)


def _review_lines(
    invoice: Invoice,
    evidence: List[ExtractionEvidence],
) -> InvoiceReviewField:
    count = len(invoice.lines)
    field_evidence = _field_evidence(evidence, "lines", str(count))
    if count == 0:
        return _field(
            "lines",
            "0",
            confidence=0.12,
            severity=InvoiceReviewSeverity.ERROR,
            issue="No line items were extracted.",
            suggestion="Enter at least one line item before posting to accounting.",
            evidence=field_evidence,
        )

    suspicious = [
        line
        for line in invoice.lines
        if _line_looks_noisy(line.description)
        or (invoice.total > 0 and abs(line.total_amount or line.net_amount) > invoice.total * 5)
    ]
    if suspicious:
        return _field(
            "lines",
            str(count),
            confidence=0.48,
            severity=InvoiceReviewSeverity.REVIEW,
            issue=f"{len(suspicious)} extracted line item(s) look like address, date, bank, or footer text.",
            suggestion="Remove noisy rows and keep only billable invoice line items.",
            evidence=field_evidence,
        )
    return _field("lines", str(count), confidence=0.82, evidence=field_evidence)


def _build_insights(
    invoice: Invoice,
    fields: List[InvoiceReviewField],
    detected: DetectedInvoiceProfile,
    profile_result: Optional[ProfileRecommendationResult],
) -> List[InvoiceReviewInsight]:
    insights: List[InvoiceReviewInsight] = []
    if detected.signals:
        insights.append(
            InvoiceReviewInsight(
                title=f"{detected.country_name} format detected",
                detail=f"{detected.invoice_format} · {detected.tax_mode} · {detected.currency}",
                severity=InvoiceReviewSeverity.OK,
                action="Use this to choose the right client profile and tax mapping.",
            )
        )
    if profile_result and profile_result.recommendations:
        top = profile_result.recommendations[0]
        severity = (
            InvoiceReviewSeverity.OK
            if top.score >= 0.72
            else InvoiceReviewSeverity.REVIEW
        )
        insights.append(
            InvoiceReviewInsight(
                title=f"Recommended profile: {top.profile.name}",
                detail=f"{round(top.score * 100)}% match · {', '.join(top.reasons[:3])}",
                severity=severity,
                action="Select this profile before validation if the accounting system matches.",
            )
        )
    elif invoice.organization_id:
        insights.append(
            InvoiceReviewInsight(
                title="No matching client profile selected",
                detail="Posting rules, ledgers, taxes, and item mappings are safer when a profile is attached.",
                severity=InvoiceReviewSeverity.REVIEW,
                action="Choose or create a client profile before posting.",
            )
        )

    errors = [field for field in fields if field.severity == InvoiceReviewSeverity.ERROR]
    reviews = [field for field in fields if field.severity == InvoiceReviewSeverity.REVIEW]
    if errors:
        insights.append(
            InvoiceReviewInsight(
                title="Required fields missing",
                detail=", ".join(field.label for field in errors),
                severity=InvoiceReviewSeverity.ERROR,
                action="Fill these fields before validation.",
            )
        )
    elif reviews:
        insights.append(
            InvoiceReviewInsight(
                title="Review suggested before approval",
                detail=", ".join(field.label for field in reviews[:4]),
                severity=InvoiceReviewSeverity.REVIEW,
                action="Check highlighted fields against the PDF.",
            )
        )
    else:
        insights.append(
            InvoiceReviewInsight(
                title="Extraction looks posting-ready",
                detail="Required fields and line-item totals passed the first review checks.",
                severity=InvoiceReviewSeverity.OK,
                action="Validate, approve, then post to the selected accounting system.",
            )
        )
    return insights


def _suggest_patch(
    invoice: Invoice,
    detected: DetectedInvoiceProfile,
    fields: List[InvoiceReviewField],
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    noisy_supplier = next(
        (field for field in fields if field.field_path == "supplier.name"),
        None,
    )
    if noisy_supplier and noisy_supplier.severity != InvoiceReviewSeverity.OK:
        patch["supplier.name"] = ""
    if invoice.currency and invoice.currency != detected.currency:
        patch["currency"] = detected.currency
    if not invoice.due_date and invoice.invoice_date:
        patch["due_date"] = invoice.invoice_date
    if not invoice.total and invoice.lines:
        patch["total"] = round(
            sum(line.total_amount or line.net_amount for line in invoice.lines),
            2,
        )
    return patch


def _field(
    field_path: str,
    value: str,
    confidence: Optional[float],
    evidence: List[ExtractionEvidence],
    severity: InvoiceReviewSeverity = InvoiceReviewSeverity.OK,
    issue: str = "",
    suggestion: str = "",
) -> InvoiceReviewField:
    return InvoiceReviewField(
        field_path=field_path,
        label=FIELD_LABELS[field_path],
        value=value,
        confidence=confidence,
        severity=severity,
        issue=issue,
        suggestion=suggestion,
        evidence=evidence,
    )


def _field_evidence(
    evidence: List[ExtractionEvidence],
    field_path: str,
    value: str,
) -> List[ExtractionEvidence]:
    direct = [item for item in evidence if item.field == field_path]
    if direct:
        return direct[:3]
    if value:
        return [
            ExtractionEvidence(
                field=field_path,
                value=value,
                page=1,
                snippet=f"Parsed value: {value}",
                confidence=0.68,
            )
        ]
    return []


def _confidence(
    invoice: Invoice,
    evidence: List[ExtractionEvidence],
    value: str,
) -> float:
    if evidence:
        scores = [item.confidence for item in evidence if item.confidence is not None]
        if scores:
            return round(sum(scores) / len(scores), 2)
    if invoice.confidence is not None:
        return round(invoice.confidence, 2)
    return 0.78 if value else 0.2


def _looks_like_date(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    for fmt in (
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            datetime.strptime(normalized.title(), fmt)
            return True
        except ValueError:
            continue
    return bool(
        re.search(
            r"\b(?:\d{1,2}[-/ .][A-Za-z]{3,9}[-/ .,]*\d{2,4}|"
            r"[A-Za-z]{3,9}[-/ .]\d{1,2}[-/ .,]*\d{2,4}|"
            r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _line_looks_noisy(description: str) -> bool:
    upper = (description or "").upper()
    noisy_tokens = (
        "IBAN",
        "ACCT",
        "SORT CODE",
        "CUSTOMER CARD",
        "EMAIL",
        "TEL:",
        "MIAMI",
        "STREET",
        "SUITE",
        "INVOICE",
        "DUE DATE",
    )
    if any(token in upper for token in noisy_tokens):
        return True
    months = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    if len(upper) <= 10 and any(month in upper for month in months):
        return True
    return False


def _money_text(value: float, currency: str) -> str:
    return f"{(currency or 'USD').upper()} {value:,.2f}"
