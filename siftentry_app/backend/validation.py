"""Deterministic invoice validation used before accounting-system posting."""

from __future__ import annotations

from typing import List

from .models import Invoice, InvoiceStatus, ValidationResult


def validate_invoice(invoice: Invoice, tolerance: float = 1.0) -> ValidationResult:
    issues: List[str] = []

    if not invoice.invoice_number.strip():
        issues.append("Invoice number is required.")
    if not invoice.invoice_date.strip():
        issues.append("Invoice date is required.")
    if not invoice.supplier.name.strip():
        issues.append("Supplier name is required.")
    if not invoice.lines:
        issues.append("At least one invoice line is required.")
    if invoice.total <= 0:
        issues.append("Invoice total must be greater than zero.")

    for index, line in enumerate(invoice.lines, start=1):
        if not line.description.strip():
            issues.append(f"Line {index}: description is required.")
        if line.total_amount < 0 or line.net_amount < 0 or line.tax_amount < 0:
            issues.append(f"Line {index}: amounts cannot be negative.")

    line_total = round(sum(line.total_amount for line in invoice.lines), 2)
    if invoice.lines and invoice.total > 0 and abs(line_total - invoice.total) > tolerance:
        issues.append(
            f"Line totals ({line_total:.2f}) do not match invoice total "
            f"({invoice.total:.2f}) within {tolerance:.2f}."
        )

    status = InvoiceStatus.VALIDATED if not issues else InvoiceStatus.NEEDS_REVIEW
    return ValidationResult(
        invoice_id=invoice.id,
        valid=not issues,
        status=status,
        issues=issues,
    )
