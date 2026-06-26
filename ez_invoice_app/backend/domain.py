"""Conversion between the legacy normalized payload and the universal API model."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .models import Invoice, InvoiceCreate, InvoiceLine, InvoiceStatus, Party


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        cleaned = str(value).replace(",", "").replace("INR", "").replace("$", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0


def _address(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _first(mapping: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def _party(data: Dict[str, Any]) -> Party:
    return Party(
        name=str(_first(data, ["NAME", "name", "LEGAL NAME"], "")).strip(),
        tax_id=str(_first(data, ["GSTIN", "GSTIN/UIN", "TAX ID", "tax_id"], "")).strip(),
        address=_address(_first(data, ["ADDRESS", "address"], [])),
        email=str(_first(data, ["EMAIL", "email"], "")).strip(),
        phone=str(_first(data, ["PHONE", "phone"], "")).strip(),
    )


def _invoice_lines(rows: List[Dict[str, Any]]) -> List[InvoiceLine]:
    output: List[InvoiceLine] = []
    for index, row in enumerate(rows, start=1):
        net_amount = _number(
            _first(row, ["EXTENDED AMOUNT", "NET AMOUNT", "TAXABLE VALUE", "net_amount"], 0)
        )
        tax_amount = _number(_first(row, ["TAX AMOUNT", "tax_amount"], 0))
        total_amount = _number(_first(row, ["AMOUNT", "TOTAL", "total_amount"], 0))
        if not total_amount:
            total_amount = round(net_amount + tax_amount, 2)
        if not net_amount and total_amount:
            net_amount = round(max(0.0, total_amount - tax_amount), 2)

        output.append(
            InvoiceLine(
                line_number=index,
                description=str(_first(row, ["DESCRIPTION", "description"], "")).strip(),
                quantity=_number(_first(row, ["QUANTITY", "QTY", "quantity"], 0)),
                uom=str(_first(row, ["UOM", "UNIT", "uom"], "")).strip(),
                unit_price=_number(_first(row, ["UNIT PRICE", "RATE", "unit_price"], 0)),
                net_amount=net_amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
                hsn_sac=str(_first(row, ["HSN/SAC", "HSN", "SAC", "hsn_sac"], "")).strip(),
                category=str(
                    _first(row, ["CATEGORY", "PLATFORM_CATEGORY", "platform_category"], "")
                ).strip(),
                gl_code=str(_first(row, ["GL CODE", "GL_CODE", "gl_code"], "")).strip(),
            )
        )
    return output


def legacy_payload_to_invoice(
    payload: Dict[str, Any],
    organization_id: str,
    source_file: str,
    source_path: str = "",
) -> InvoiceCreate:
    invoice = payload.get("INVOICE", payload)
    document = invoice.get("DOCUMENT", {}) or {}
    header = invoice.get("INVOICE HEADER", {}) or {}
    payment = (invoice.get("PAYMENT", {}) or {}).get("ELECTRONIC", {}) or {}
    line_rows = (invoice.get("LINE ITEMS", {}) or {}).get("ROWS", []) or []
    lines = _invoice_lines(line_rows)

    total = _number(
        _first(
            header,
            ["INVOICE AMOUNT", "AMOUNT TO BE EFT DRAFTED", "invoice_amount"],
            payment.get("AMOUNT", 0),
        )
    )
    tax_summary = invoice.get("INVOICE TAX SUMMARY", {}) or {}
    tax_total = _number(_first(tax_summary, ["TOTAL TAX", "TAX AMOUNT", "tax_total"], 0))
    if not tax_total:
        tax_total = round(sum(line.tax_amount for line in lines), 2)
    subtotal = round(sum(line.net_amount for line in lines), 2)
    if not subtotal and total:
        subtotal = round(max(0.0, total - tax_total), 2)

    parser = str(
        _first(document, ["PARSER", "ADAPTER", "parser"], "Generic")
    ).strip() or "Generic"
    route = invoice.get("ROUTING", invoice.get("ACCOUNTING ROUTE", {})) or {}
    direction = str(_first(route, ["DIRECTION", "direction"], "inbound")).lower()
    if direction not in {"inbound", "outbound"}:
        direction = "inbound"

    return InvoiceCreate(
        organization_id=organization_id,
        source_file=source_file,
        source_path=source_path,
        parser=parser,
        extraction_engine=str(
            _first(document, ["EXTRACTION ENGINE", "engine"], "")
        ).strip(),
        page_count=max(1, int(_number(_first(document, ["PAGES", "pages"], 1)) or 1)),
        status=InvoiceStatus.EXTRACTED,
        invoice_number=str(
            _first(header, ["INVOICE NO.", "INVOICE NUMBER", "invoice_number"], "")
        ).strip(),
        invoice_date=str(_first(header, ["INVOICE DATE", "invoice_date"], "")).strip(),
        due_date=str(_first(header, ["DUE DATE", "due_date"], "")).strip(),
        purchase_order=str(
            _first(header, ["PO NO./CONTRACT NO.", "PO NO.", "purchase_order"], "")
        ).strip(),
        currency=str(_first(payment, ["CURRENCY", "currency"], "USD")).strip().upper(),
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        supplier=_party(invoice.get("SELLER", {}) or {}),
        customer=_party(invoice.get("BILL TO", {}) or {}),
        direction=direction,
        lines=lines,
        raw_payload=payload,
    )


def invoice_to_legacy_payload(invoice: Invoice) -> Dict[str, Any]:
    """Overlay reviewed universal fields onto the original connector payload."""

    payload = dict(invoice.raw_payload or {})
    legacy_invoice = payload.setdefault("INVOICE", {})
    document = legacy_invoice.setdefault("DOCUMENT", {})
    header = legacy_invoice.setdefault("INVOICE HEADER", {})
    payment = legacy_invoice.setdefault("PAYMENT", {}).setdefault("ELECTRONIC", {})
    line_items = legacy_invoice.setdefault("LINE ITEMS", {})

    document["SOURCE FILE"] = invoice.source_file
    document["PARSER"] = invoice.parser
    document["EXTRACTION ENGINE"] = invoice.extraction_engine
    document["PAGES"] = invoice.page_count

    header["INVOICE NO."] = invoice.invoice_number
    header["INVOICE DATE"] = invoice.invoice_date
    header["DUE DATE"] = invoice.due_date
    header["PO NO./CONTRACT NO."] = invoice.purchase_order or "N/A"
    header["INVOICE AMOUNT"] = invoice.total
    header["AMOUNT TO BE EFT DRAFTED"] = invoice.total

    payment["CURRENCY"] = invoice.currency
    payment["AMOUNT"] = invoice.total

    legacy_invoice["SELLER"] = {
        "NAME": invoice.supplier.name,
        "ADDRESS": invoice.supplier.address,
        "GSTIN": invoice.supplier.tax_id,
        "EMAIL": invoice.supplier.email,
        "PHONE": invoice.supplier.phone,
    }
    legacy_invoice["BILL TO"] = {
        "NAME": invoice.customer.name,
        "ADDRESS": invoice.customer.address,
        "GSTIN": invoice.customer.tax_id,
        "EMAIL": invoice.customer.email,
        "PHONE": invoice.customer.phone,
    }
    legacy_invoice["ROUTING"] = {"DIRECTION": invoice.direction}
    line_items["COLUMNS"] = [
        "DESCRIPTION",
        "QUANTITY",
        "UOM",
        "UNIT PRICE",
        "EXTENDED AMOUNT",
        "TAX AMOUNT",
        "AMOUNT",
        "HSN/SAC",
        "CATEGORY",
        "GL_CODE",
    ]
    line_items["ROWS"] = [
        {
            "DESCRIPTION": line.description,
            "QUANTITY": line.quantity,
            "UOM": line.uom,
            "UNIT PRICE": line.unit_price,
            "EXTENDED AMOUNT": line.net_amount,
            "TAX AMOUNT": line.tax_amount,
            "AMOUNT": line.total_amount,
            "HSN/SAC": line.hsn_sac,
            "CATEGORY": line.category,
            "PLATFORM_CATEGORY": line.category,
            "GL_CODE": line.gl_code,
        }
        for line in invoice.lines
    ]
    legacy_invoice["INVOICE TAX SUMMARY"] = {"TOTAL TAX": invoice.tax_total}
    return payload
