"""Accounting routing helpers for normalized EZ-Invoice payloads."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_HOME_COMPANIES = [
]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def home_company_names(extra: Optional[Iterable[str]] = None) -> List[str]:
    values: List[str] = []
    if extra:
        values.extend(str(part).strip() for part in extra)
    else:
        env_value = os.environ.get("EZ_INVOICE_HOME_COMPANY", "")
        if env_value:
            values.extend(part.strip() for part in env_value.split(","))
        values.extend(DEFAULT_HOME_COMPANIES)
    return [value for value in values if value]


def party_matches_home(value: str, homes: Optional[Iterable[str]] = None) -> bool:
    normalized = _norm(value)
    if not normalized:
        return False
    for home in home_company_names(homes):
        home_norm = _norm(home)
        if home_norm and (home_norm in normalized or normalized in home_norm):
            return True
    return False


def infer_accounting_route(payload: Dict[str, Any], homes: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    inv = payload.get("INVOICE", {})
    seller = inv.get("SELLER", {}).get("NAME", "")
    bill_to = inv.get("BILL TO", {}).get("NAME", "")
    seller_is_home = party_matches_home(seller, homes)
    bill_to_is_home = party_matches_home(bill_to, homes)

    if bill_to_is_home and not seller_is_home:
        direction = "inbound"
        transaction_type = "purchase"
        party_role = "vendor"
        party_name = seller
        quickbooks_target = "Bill"
        tally_voucher_type = "Purchase"
        confidence = "high"
    elif seller_is_home and not bill_to_is_home:
        direction = "outbound"
        transaction_type = "sales"
        party_role = "customer"
        party_name = bill_to
        quickbooks_target = "Invoice"
        tally_voucher_type = "Sales"
        confidence = "high"
    else:
        direction = "unknown"
        transaction_type = "review"
        party_role = "party"
        party_name = seller or bill_to
        quickbooks_target = "Review"
        tally_voucher_type = "Purchase"
        confidence = "low"

    return {
        "DIRECTION": direction,
        "TRANSACTION TYPE": transaction_type,
        "PARTY ROLE": party_role,
        "PARTY NAME": party_name,
        "SELLER IS HOME": seller_is_home,
        "BILL TO IS HOME": bill_to_is_home,
        "QUICKBOOKS TARGET": quickbooks_target,
        "TALLY VOUCHER TYPE": tally_voucher_type,
        "CONFIDENCE": confidence,
    }


def apply_accounting_route(payload: Dict[str, Any], homes: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    inv = payload.setdefault("INVOICE", {})
    route = infer_accounting_route(payload, homes)
    inv["ROUTING"] = route
    inv.setdefault("DOCUMENT", {})["DIRECTION"] = route["DIRECTION"]
    return payload
