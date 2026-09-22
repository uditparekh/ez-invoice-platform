"""Versioned Tally approval contracts. No network calls or credentials in plans.

The human-readable entry is decoded from the SAME XML the connector receives.
Master-name verification and uncertain-result reconciliation remain separate.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

from .adapters import _profiled_legacy_payload, _tally_settings_from_profile
from .models import ClientProfile, Invoice
from ..tally_integration import build_tally_xml, _tally_preflight_issues

SCHEMA_VERSION = 1


class ApprovalConflict(ValueError):
    """A stale or unsafe workflow action; exposed as HTTP 409."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def invoice_fingerprint(invoice: Invoice) -> str:
    data = invoice.model_dump(
        mode="json",
        exclude={
            "status",
            "updated_at",
            "validation_issues",
            "document_retention",
        },
    )
    return digest(data)


def accounting_config(profile: ClientProfile) -> dict:
    # An allow-list, not a secret-name deny-list. Token rotation, descriptions,
    # training guidance and heartbeat changes do not change an accounting entry.
    settings = _tally_settings_from_profile(profile) or {}
    connection = profile.settings.connection_settings or {}
    return {
        "profile_id": profile.id,
        "organization_id": profile.organization_id,
        "accounting_system": str(profile.accounting_system),
        "settings": settings,
        "direction": profile.settings.direction,
        "item_mappings": [
            item.model_dump(mode="json") for item in profile.settings.item_mappings
        ],
        "workspace_id": str(connection.get("workspace_id") or ""),
        "connector_enabled": bool(connection.get("connector_enabled", False)),
        "connector_url": str(
            connection.get("connector_url")
            or connection.get("tally_connector_url")
            or ""
        ),
    }


def profile_fingerprint(profile: ClientProfile) -> str:
    return digest(accounting_config(profile))


def _entry(node: ET.Element) -> dict:
    amount = node.findtext("AMOUNT", "0")
    value = Decimal(amount)
    return {
        "ledger": node.findtext("LEDGERNAME", ""),
        "amount": str(abs(value)),
        "side": "debit" if value < 0 else "credit",
        "party": node.findtext("ISPARTYLEDGER", "No") == "Yes",
    }


def _allocation(node: ET.Element) -> dict:
    return {
        "item": node.findtext("STOCKITEMNAME", ""),
        "quantity": node.findtext("ACTUALQTY", ""),
        "billed_quantity": node.findtext("BILLEDQTY", ""),
        "rate": node.findtext("RATE", ""),
        "amount": node.findtext("AMOUNT", ""),
        "godowns": [
            item.findtext("GODOWNNAME", "")
            for item in node.findall("BATCHALLOCATIONS.LIST")
        ],
        "accounting": [
            _entry(item) for item in node.findall("ACCOUNTINGALLOCATIONS.LIST")
        ],
    }


def build_plan(invoice: Invoice, profile: ClientProfile) -> dict:
    numbers = [invoice.total, invoice.subtotal, invoice.tax_total]
    for line in invoice.lines:
        numbers.extend(
            [
                line.quantity,
                line.unit_price,
                line.net_amount,
                line.tax_amount,
                line.total_amount,
            ]
        )
    if not all(math.isfinite(value) for value in numbers):
        raise ApprovalConflict(
            "Invoice amounts and quantities must be finite numbers before preview or approval."
        )
    config = accounting_config(profile)
    payload = _profiled_legacy_payload(invoice, profile)
    issues = _tally_preflight_issues(payload, config["settings"])
    blocking = [issue["message"] for issue in issues if issue.get("blocking", True)]
    if not profile.settings.company_name.strip():
        blocking.append("Set the exact Tally company name before approval.")
    if invoice.currency.upper() != profile.settings.default_currency.upper():
        blocking.append(
            "Invoice currency does not match the profile currency. Foreign-currency conversion is not supported by this Tally plan."
        )
    xml = build_tally_xml(payload, settings=config["settings"], classifier=None)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ApprovalConflict(
            "Invoice or profile values contain characters that are not valid in Tally XML."
        ) from exc
    voucher = root.find(".//VOUCHER")
    if voucher is None:
        raise ApprovalConflict(
            "Could not build a Tally voucher. Check the posting rules."
        )
    ledgers = [
        _entry(node)
        for node in voucher.findall("ALLLEDGERENTRIES.LIST")
        + voucher.findall("LEDGERENTRIES.LIST")
    ]
    inventory = [
        _allocation(node)
        for node in voucher.findall("ALLINVENTORYENTRIES.LIST")
        + voucher.findall("INVENTORYENTRIES.LIST")
    ]
    for ledger_node in voucher.findall("ALLLEDGERENTRIES.LIST") + voucher.findall(
        "LEDGERENTRIES.LIST"
    ):
        inventory.extend(
            _allocation(node)
            for node in ledger_node.findall("INVENTORYALLOCATIONS.LIST")
        )
    # Item-invoice accounting allocations carry the debit outside the top-level
    # ledger entries. Include those when checking balance, but never double-count
    # voucher-with-inventory nested stock allocations.
    balance = sum(
        (
            Decimal(node.findtext("AMOUNT", "0"))
            for node in voucher.findall("ALLLEDGERENTRIES.LIST")
            + voucher.findall("LEDGERENTRIES.LIST")
        ),
        Decimal(0),
    )
    for node in voucher.findall("ALLINVENTORYENTRIES.LIST") + voucher.findall(
        "INVENTORYENTRIES.LIST"
    ):
        balance += Decimal(node.findtext("AMOUNT", "0"))
    if abs(balance) > Decimal("0.01"):
        blocking.append(
            "The proposed entry does not balance. Check tax, totals and ledger mappings."
        )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "target": "tally",
        "invoice_id": invoice.id,
        "organization_id": invoice.organization_id,
        "client_profile_id": profile.id,
        "client_profile_name": profile.name,
        "invoice_fingerprint": invoice_fingerprint(invoice),
        "profile_fingerprint": profile_fingerprint(profile),
        "company": config["settings"]["company"],
        "workspace_id": config["workspace_id"],
        "tally_url": config["settings"]["url"],
        "invoice_number": voucher.findtext("VOUCHERNUMBER", ""),
        "voucher_type": voucher.findtext("VOUCHERTYPENAME", ""),
        "voucher_date": voucher.findtext("DATE", ""),
        "posting_mode": config["settings"]["posting_mode"],
        "currency": invoice.currency,
        "total": invoice.total,
        "ledgers": ledgers,
        "inventory": inventory,
        "blocking_issues": list(dict.fromkeys(blocking)),
        "warnings": [
            "Check the profile's latest Tally master snapshot. A name's presence does not prove its accounting mapping is correct.",
            "Confirm that the profile currency matches the Tally company's base currency. This entry does not include an exchange rate.",
        ],
        "xml": xml,
    }
    plan["preview_hash"] = digest(plan)
    return plan
