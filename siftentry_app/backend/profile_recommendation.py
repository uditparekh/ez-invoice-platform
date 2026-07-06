"""Client profile detection and recommendation for parsed invoices."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List

from .models import (
    ClientProfile,
    ClientProfileRecommendation,
    DetectedInvoiceProfile,
    Invoice,
    ProfileRecommendationResult,
)


COUNTRY_DEFAULTS: dict[str, dict[str, str]] = {
    "US": {
        "country_name": "United States",
        "currency": "USD",
        "invoice_format": "auto",
        "tax_mode": "sales_tax",
        "tax_registration_label": "Tax ID",
    },
    "IN": {
        "country_name": "India",
        "currency": "INR",
        "invoice_format": "gst_einvoice",
        "tax_mode": "gst_auto",
        "tax_registration_label": "GSTIN",
    },
    "CA": {
        "country_name": "Canada",
        "currency": "CAD",
        "invoice_format": "auto",
        "tax_mode": "gst_hst",
        "tax_registration_label": "GST/HST",
    },
    "GB": {
        "country_name": "United Kingdom",
        "currency": "GBP",
        "invoice_format": "auto",
        "tax_mode": "vat",
        "tax_registration_label": "VAT",
    },
    "EU": {
        "country_name": "European Union",
        "currency": "EUR",
        "invoice_format": "auto",
        "tax_mode": "vat",
        "tax_registration_label": "VAT",
    },
    "AE": {
        "country_name": "United Arab Emirates",
        "currency": "AED",
        "invoice_format": "auto",
        "tax_mode": "vat",
        "tax_registration_label": "TRN",
    },
}

COUNTRY_BY_CURRENCY = {
    "USD": "US",
    "INR": "IN",
    "CAD": "CA",
    "GBP": "GB",
    "EUR": "EU",
    "AED": "AE",
}

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")
EIN_RE = re.compile(r"\b\d{2}-\d{7}\b")
CANADA_TAX_RE = re.compile(r"\b\d{9}R[CT]\d{4}\b", re.IGNORECASE)
EU_VAT_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{8,12}\b")


def detect_invoice_profile(invoice: Invoice) -> DetectedInvoiceProfile:
    signals: list[str] = []
    currency = (invoice.currency or "USD").strip().upper() or "USD"
    country_code = COUNTRY_BY_CURRENCY.get(currency, "US")
    confidence = 0.18
    raw_text = _invoice_text(invoice)
    tax_ids = [
        invoice.supplier.tax_id.strip().upper(),
        invoice.customer.tax_id.strip().upper(),
    ]
    hsn_values = [
        re.sub(r"\D", "", line.hsn_sac or "")
        for line in invoice.lines
        if re.sub(r"\D", "", line.hsn_sac or "")
    ]

    if currency:
        signals.append(f"Currency {currency}")
        confidence += 0.12

    if any(GSTIN_RE.search(value) for value in tax_ids) or GSTIN_RE.search(raw_text):
        country_code = "IN"
        confidence += 0.35
        signals.append("GSTIN detected")

    if hsn_values:
        signals.append("HSN/SAC detected")
        if country_code == "IN":
            confidence += 0.12

    if EIN_RE.search(raw_text):
        country_code = "US"
        confidence += 0.2
        signals.append("US tax ID pattern detected")

    if CANADA_TAX_RE.search(raw_text):
        country_code = "CA"
        confidence += 0.22
        signals.append("Canada GST/HST pattern detected")

    if "TRN" in raw_text.upper() or currency == "AED":
        country_code = "AE"
        confidence += 0.14
        signals.append("UAE tax/currency signal detected")

    if country_code != "IN" and ("VAT" in raw_text.upper() or EU_VAT_RE.search(raw_text)):
        if currency == "GBP":
            country_code = "GB"
        elif currency == "EUR":
            country_code = "EU"
        confidence += 0.12
        signals.append("VAT signal detected")

    tax_mode = _detect_tax_mode(country_code, raw_text, invoice)
    invoice_format = _detect_invoice_format(country_code, raw_text, invoice)
    defaults = COUNTRY_DEFAULTS.get(country_code, COUNTRY_DEFAULTS["US"])
    currency = currency or defaults["currency"]

    return DetectedInvoiceProfile(
        country_code=country_code,
        country_name=defaults["country_name"],
        currency=currency,
        invoice_format=invoice_format or defaults["invoice_format"],
        tax_mode=tax_mode or defaults["tax_mode"],
        tax_registration_label=defaults["tax_registration_label"],
        confidence=min(1.0, round(confidence, 2)),
        signals=list(dict.fromkeys(signals)),
    )


def recommend_client_profiles(
    invoice: Invoice,
    profiles: Iterable[ClientProfile],
) -> ProfileRecommendationResult:
    detected = detect_invoice_profile(invoice)
    recommendations = [
        _score_profile(invoice, detected, profile) for profile in profiles
    ]
    recommendations = sorted(
        recommendations,
        key=lambda recommendation: (
            recommendation.score,
            recommendation.profile.is_default,
            recommendation.profile.updated_at,
        ),
        reverse=True,
    )
    auto_profile_id = (
        recommendations[0].profile.id
        if recommendations and recommendations[0].score >= 0.48
        else None
    )
    return ProfileRecommendationResult(
        invoice_id=invoice.id,
        detected=detected,
        recommendations=recommendations,
        auto_profile_id=auto_profile_id,
    )


def _score_profile(
    invoice: Invoice,
    detected: DetectedInvoiceProfile,
    profile: ClientProfile,
) -> ClientProfileRecommendation:
    settings = profile.settings
    score = 0.0
    reasons: list[str] = []

    profile_country = (settings.country_code or "").upper()
    profile_currency = (settings.default_currency or "").upper()
    profile_tax_mode = (settings.tax_mode or "").lower()
    profile_format = (settings.invoice_format or "").lower()

    if profile_country and profile_country == detected.country_code:
        score += 0.28
        reasons.append(f"Country matches {detected.country_name}")

    if profile_currency and profile_currency == detected.currency:
        score += 0.2
        reasons.append(f"Currency matches {detected.currency}")

    if _tax_modes_match(profile_tax_mode, detected.tax_mode):
        score += 0.18
        reasons.append(f"Tax mode matches {detected.tax_mode.replace('_', ' ')}")

    if _formats_match(profile_format, detected.invoice_format):
        score += 0.12
        reasons.append(f"Format matches {detected.invoice_format.replace('_', ' ')}")

    if (settings.direction or "").lower() == (invoice.direction or "").lower():
        score += 0.05
        reasons.append(f"Direction matches {invoice.direction or 'inbound'}")

    mapping_score, mapping_reasons = _score_item_mappings(invoice, profile)
    score += mapping_score
    reasons.extend(mapping_reasons)

    if profile.is_default:
        score += 0.04
        reasons.append("Default profile for this accounting system")

    if not reasons:
        reasons.append("Available profile for selected accounting system")

    return ClientProfileRecommendation(
        profile=profile,
        score=min(1.0, round(score, 2)),
        reasons=list(dict.fromkeys(reasons))[:5],
    )


def _score_item_mappings(invoice: Invoice, profile: ClientProfile) -> tuple[float, List[str]]:
    mappings = profile.settings.item_mappings or []
    if not mappings:
        return 0.0, []

    invoice_hsns = {
        re.sub(r"\D", "", line.hsn_sac or "")
        for line in invoice.lines
        if re.sub(r"\D", "", line.hsn_sac or "")
    }
    descriptions = " ".join(line.description for line in invoice.lines).lower()
    score = 0.0
    reasons: list[str] = []

    for mapping in mappings:
        mapping_hsn = re.sub(r"\D", "", mapping.source_hsn_sac or "")
        if mapping_hsn and mapping_hsn in invoice_hsns:
            score += 0.16
            reasons.append(f"HSN/SAC mapping matches {mapping_hsn}")

        contains = (mapping.source_description_contains or "").strip().lower()
        if contains and contains in descriptions:
            score += 0.12
            reasons.append(f"Item mapping matches {mapping.source_description_contains}")

    return min(score, 0.24), reasons


def _detect_tax_mode(country_code: str, raw_text: str, invoice: Invoice) -> str:
    upper = raw_text.upper()
    if country_code == "IN":
        has_igst = "IGST" in upper
        has_cgst_sgst = "CGST" in upper or "SGST" in upper
        if has_igst and not has_cgst_sgst:
            return "gst_igst"
        if has_cgst_sgst:
            return "gst_cgst_sgst"
        if invoice.tax_total > 0:
            return "gst_auto"
        return "gst_auto"
    if country_code in {"GB", "EU", "AE"}:
        return "vat"
    if country_code == "CA":
        return "gst_hst"
    if country_code == "US":
        return "sales_tax" if invoice.tax_total > 0 else "auto"
    return "auto"


def _detect_invoice_format(country_code: str, raw_text: str, invoice: Invoice) -> str:
    parser = (invoice.parser or "").lower()
    upper = raw_text.upper()
    if country_code == "IN" and (
        "GST" in upper or "HSN" in upper or "SAC" in upper or "gst" in parser
    ):
        return "gst_einvoice"
    if "PEPPOL" in upper:
        return "peppol"
    if invoice.extraction_engine.lower().find("ocr") >= 0:
        return "scanned_ocr"
    return "auto"


def _tax_modes_match(profile_tax_mode: str, detected_tax_mode: str) -> bool:
    if not profile_tax_mode:
        return False
    if profile_tax_mode == detected_tax_mode:
        return True
    if profile_tax_mode == "auto":
        return True
    if profile_tax_mode == "gst_auto" and detected_tax_mode.startswith("gst_"):
        return True
    if profile_tax_mode == "vat" and detected_tax_mode == "vat":
        return True
    return False


def _formats_match(profile_format: str, detected_format: str) -> bool:
    if not profile_format:
        return False
    return profile_format == detected_format or profile_format == "auto"


def _invoice_text(invoice: Invoice) -> str:
    pieces: list[str] = [
        invoice.source_file,
        invoice.parser,
        invoice.extraction_engine,
        invoice.currency,
        invoice.supplier.name,
        invoice.supplier.tax_id,
        invoice.customer.name,
        invoice.customer.tax_id,
        invoice.invoice_number,
    ]
    pieces.extend(invoice.supplier.address)
    pieces.extend(invoice.customer.address)
    pieces.extend(
        " ".join(
            [
                line.description,
                line.hsn_sac,
                line.category,
                line.gl_code,
            ]
        )
        for line in invoice.lines
    )
    pieces.append(_json_text(invoice.raw_payload))
    return "\n".join(piece for piece in pieces if piece)


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value or "")
