"""Zoho Books integration for universal supplier invoice processing."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets as pysecrets
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode, urlparse

import streamlit as st
import streamlit.components.v1 as components

from erp_connector import ConnectorResult, PreflightIssue

try:
    import requests
except ImportError:
    requests = None


def _config_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


CLIENT_ID = _config_value("ZOHO_CLIENT_ID")
CLIENT_SECRET = _config_value("ZOHO_CLIENT_SECRET")
REDIRECT_URI = _config_value("ZOHO_REDIRECT_URI", "http://localhost:8001/zoho/callback")
ACCOUNTS_BASE_URL = _config_value("ZOHO_ACCOUNTS_BASE_URL", "https://accounts.zoho.in").rstrip("/")
API_BASE_URL = _config_value("ZOHO_API_BASE_URL", "https://www.zohoapis.in/books/v3").rstrip("/")
OAUTH_SCOPE = _config_value("ZOHO_SCOPE", "ZohoBooks.fullaccess.all")

_SETTINGS_FILE = Path(__file__).with_name("zoho_account_mappings.json")
_callback_data = {"code": None, "state": None, "location": None, "error": None}
_STATE_TTL_SECONDS = 10 * 60
_consumed_states: Dict[str, float] = {}
_state_lock = threading.Lock()

LINE_CATEGORIES = [
    ("materials", "Materials / goods"),
    ("services", "Services / labour"),
    ("freight", "Freight / logistics"),
    ("fees", "Other fees"),
    ("tax", "Taxes"),
    ("general", "Default / other"),
]


def _state_signature(message: str) -> str:
    key = (CLIENT_SECRET or CLIENT_ID or "ez-invoice-zoho-local").encode("utf-8")
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _new_state() -> str:
    message = "zoho." + str(int(time.time())) + "." + pysecrets.token_urlsafe(24)
    return message + "." + _state_signature(message)


def _state_is_valid(state: Any) -> bool:
    if not state:
        return False
    state = str(state)
    expected = st.session_state.get("_zoho_oauth_state")
    if expected and not hmac.compare_digest(state, str(expected)):
        return False
    try:
        provider, timestamp_text, nonce, signature = state.split(".", 3)
        issued_at = int(timestamp_text)
    except (TypeError, ValueError):
        return False
    if provider != "zoho":
        return False
    message = provider + "." + timestamp_text + "." + nonce
    if not hmac.compare_digest(signature, _state_signature(message)):
        return False
    now = time.time()
    if issued_at > now + 60 or now - issued_at > _STATE_TTL_SECONDS:
        return False
    with _state_lock:
        expired = [item for item, used_at in _consumed_states.items() if now - used_at > _STATE_TTL_SECONDS]
        for item in expired:
            _consumed_states.pop(item, None)
        if state in _consumed_states:
            return False
        _consumed_states[state] = now
    return True


def _redirect_host() -> str:
    try:
        return (urlparse(REDIRECT_URI).hostname or "").lower()
    except Exception:
        return ""


def _uses_local_callback() -> bool:
    explicit = _config_value("ZOHO_USE_LOCAL_CALLBACK", "").strip().lower()
    if explicit in {"1", "true", "yes", "y"}:
        return True
    if explicit in {"0", "false", "no", "n"}:
        return False
    return _redirect_host() in {"localhost", "127.0.0.1"}


def _auth_url() -> str:
    state = _new_state()
    st.session_state["_zoho_oauth_state"] = state
    return ACCOUNTS_BASE_URL + "/oauth/v2/auth?" + urlencode(
        {
            "scope": OAUTH_SCOPE,
            "client_id": CLIENT_ID,
            "state": state,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "access_type": "offline",
            "prompt": "consent",
        }
    )


def _start_callback_server() -> None:
    try:
        from flask import Flask, request as flask_request
    except ImportError:
        st.error("Flask is required for local Zoho OAuth. Run: pip install flask")
        return

    parsed = urlparse(REDIRECT_URI)
    port = parsed.port or 8001
    callback_path = parsed.path or "/zoho/callback"
    app = Flask("ez_invoice_zoho_oauth")

    @app.route(callback_path)
    def callback():
        _callback_data["code"] = flask_request.args.get("code")
        _callback_data["state"] = flask_request.args.get("state")
        _callback_data["location"] = flask_request.args.get("location")
        _callback_data["error"] = flask_request.args.get("error")
        if _callback_data["code"]:
            return (
                "<h2 style='font-family:system-ui;color:#4A6741;text-align:center;padding:64px'>"
                "Zoho Books connected. Return to EZ-Invoice.</h2>"
            )
        return (
            "<h2 style='font-family:system-ui;color:#B33A2B;text-align:center;padding:64px'>"
            "Zoho authorization failed.</h2>"
        )

    import logging

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    ).start()
    time.sleep(0.8)


def _capture_callback_from_query() -> bool:
    try:
        code = st.query_params.get("code")
        state = st.query_params.get("state")
        location = st.query_params.get("location")
        error = st.query_params.get("error")
    except Exception:
        return False
    if not any([code, error]) or (state and not str(state).startswith("zoho.")):
        return False
    _callback_data.update(code=code, state=state, location=location, error=error)
    return True


def _clear_callback_query() -> None:
    try:
        for key in ["code", "state", "location", "error", "error_description", "zoho_auth"]:
            if key in st.query_params:
                del st.query_params[key]
        st.query_params["page"] = "Zoho Books"
        st.query_params["target"] = "Zoho Books"
    except Exception:
        pass


def _token_request(data: Dict[str, Any]) -> Dict[str, Any]:
    if not requests:
        return {}
    try:
        response = requests.post(ACCOUNTS_BASE_URL + "/oauth/v2/token", data=data, timeout=30)
    except Exception:
        return {}
    if response.status_code != 200:
        return {}
    body = response.json()
    return body if isinstance(body, dict) and body.get("access_token") else {}


def _exchange_code(code: str) -> Dict[str, Any]:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        }
    )


def _refresh_token(refresh_token: str) -> Dict[str, Any]:
    return _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
    )


def _set_auth_pending(pending: bool) -> None:
    st.session_state["_zoho_auth_pending"] = bool(pending)
    try:
        if pending:
            st.query_params["zoho_auth"] = "pending"
        elif "zoho_auth" in st.query_params:
            del st.query_params["zoho_auth"]
    except Exception:
        pass


def _request_auth_refresh() -> None:
    components.html(
        "<script>setTimeout(function(){window.parent.location.reload();},1500);</script>",
        height=0,
    )


def complete_zoho_auth_if_ready() -> bool:
    _capture_callback_from_query()
    if _callback_data.get("error"):
        error = str(_callback_data.get("error"))
        _callback_data.update(code=None, state=None, location=None, error=None)
        _set_auth_pending(False)
        _clear_callback_query()
        st.error("Zoho Books authorization failed: " + error)
        return True
    if not _callback_data.get("code"):
        return False

    code = str(_callback_data.get("code"))
    state = _callback_data.get("state")
    _callback_data.update(code=None, state=None, location=None, error=None)
    if not _state_is_valid(state):
        _set_auth_pending(False)
        _clear_callback_query()
        st.error("Zoho Books authorization state did not match. Please connect again.")
        return True

    tokens = _exchange_code(code)
    if not tokens:
        _set_auth_pending(False)
        _clear_callback_query()
        st.error("Zoho Books did not return an access token. Please reconnect.")
        return True

    st.session_state["zoho_access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        st.session_state["zoho_refresh_token"] = tokens["refresh_token"]
    if tokens.get("api_domain"):
        st.session_state["zoho_api_domain"] = str(tokens["api_domain"]).rstrip("/")
    expires_in = tokens.get("expires_in") or tokens.get("expires_in_sec") or 3600
    st.session_state["zoho_token_expires_at"] = time.time() + int(expires_in)
    st.session_state.pop("_zoho_oauth_state", None)
    st.session_state.pop("_zoho_auth_url", None)
    _set_auth_pending(False)
    _clear_callback_query()
    st.success("Zoho Books connected.")
    st.rerun()
    return True


def zoho_is_connected() -> bool:
    return bool(st.session_state.get("zoho_access_token"))


def _ensure_token() -> bool:
    if not zoho_is_connected():
        return False
    if time.time() <= st.session_state.get("zoho_token_expires_at", 0) - 60:
        return True
    refresh_token = st.session_state.get("zoho_refresh_token")
    if not refresh_token:
        return False
    tokens = _refresh_token(refresh_token)
    if not tokens:
        return False
    st.session_state["zoho_access_token"] = tokens["access_token"]
    if tokens.get("api_domain"):
        st.session_state["zoho_api_domain"] = str(tokens["api_domain"]).rstrip("/")
    expires_in = tokens.get("expires_in") or tokens.get("expires_in_sec") or 3600
    st.session_state["zoho_token_expires_at"] = time.time() + int(expires_in)
    return True


def _api_request(method: str, path: str, *, params=None, json_body=None) -> Dict[str, Any]:
    if not _ensure_token() or not requests:
        return {"_error": "Zoho Books is not connected."}
    headers = {
        "Authorization": "Zoho-oauthtoken " + st.session_state["zoho_access_token"],
        "Accept": "application/json",
    }
    api_base = API_BASE_URL
    if st.session_state.get("zoho_api_domain"):
        api_base = str(st.session_state["zoho_api_domain"]).rstrip("/") + "/books/v3"
    try:
        response = requests.request(
            method,
            api_base + path,
            headers=headers,
            params=params,
            json=json_body,
            timeout=45,
        )
    except Exception as exc:
        return {"_error": "Zoho Books request failed: " + str(exc)}
    try:
        body = response.json()
    except Exception:
        body = {}
    if response.status_code not in {200, 201}:
        message = body.get("message") if isinstance(body, dict) else ""
        return {"_error": message or ("Zoho Books error " + str(response.status_code))}
    return body if isinstance(body, dict) else {}


def _load_all_settings() -> Dict[str, Any]:
    try:
        if _SETTINGS_FILE.exists():
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_all_settings(data: Dict[str, Any]) -> bool:
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return True
    except Exception:
        return False


def _organization_settings(organization_id: str) -> Dict[str, Any]:
    value = _load_all_settings().get(str(organization_id), {})
    return value if isinstance(value, dict) else {}


def _save_organization_settings(organization_id: str, **updates: Any) -> bool:
    data = _load_all_settings()
    current = data.get(str(organization_id), {})
    if not isinstance(current, dict):
        current = {}
    current.update(updates)
    data[str(organization_id)] = current
    return _save_all_settings(data)


def _fetch_organizations(force: bool = False) -> List[Dict[str, Any]]:
    if not force and st.session_state.get("zoho_organizations"):
        return st.session_state["zoho_organizations"]
    body = _api_request("GET", "/organizations")
    organizations = body.get("organizations", []) if not body.get("_error") else []
    st.session_state["zoho_organizations"] = organizations
    return organizations


def _organization_id() -> str:
    return str(st.session_state.get("zoho_organization_id", "") or "")


def _fetch_accounts(organization_id: str, force: bool = False) -> List[Dict[str, Any]]:
    key = "zoho_accounts_" + organization_id
    if not force and st.session_state.get(key):
        return st.session_state[key]
    body = _api_request("GET", "/chartofaccounts", params={"organization_id": organization_id})
    accounts = body.get("chartofaccounts", []) if not body.get("_error") else []
    usable = [
        account
        for account in accounts
        if account.get("is_active", True)
        and str(account.get("account_type", "")).lower()
        not in {"bank", "accounts_receivable", "accounts_payable", "cash"}
    ]
    st.session_state[key] = usable or accounts
    return st.session_state[key]


def _fetch_taxes(organization_id: str, force: bool = False) -> List[Dict[str, Any]]:
    key = "zoho_taxes_" + organization_id
    if not force and st.session_state.get(key):
        return st.session_state[key]
    body = _api_request("GET", "/settings/taxes", params={"organization_id": organization_id})
    taxes = body.get("taxes", []) if not body.get("_error") else []
    st.session_state[key] = [tax for tax in taxes if tax.get("is_active", True)]
    return st.session_state[key]


def _account_ref(account: Dict[str, Any]) -> Dict[str, str]:
    return {
        "account_id": str(account.get("account_id", "")),
        "account_name": str(account.get("account_name", "") or account.get("name", "")),
    }


def _account_label(account: Dict[str, Any]) -> str:
    name = str(account.get("account_name", "") or account.get("name", "") or "Unnamed account")
    code = str(account.get("account_code", "") or "")
    return name + (" (" + code + ")" if code else "")


def _find_account(accounts: List[Dict[str, Any]], hints: List[str]) -> Dict[str, str]:
    for hint in hints:
        for account in accounts:
            if hint.lower() in _account_label(account).lower():
                return _account_ref(account)
    return {}


def _default_mapping(accounts: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    first = _account_ref(accounts[0]) if accounts else {}
    return {
        "materials": _find_account(accounts, ["purchase", "material", "inventory", "goods"]) or first,
        "services": _find_account(accounts, ["service", "labour", "labor", "expense"]) or first,
        "freight": _find_account(accounts, ["freight", "shipping", "transport", "delivery"]) or first,
        "fees": _find_account(accounts, ["fee", "charge", "miscellaneous"]) or first,
        "tax": _find_account(accounts, ["tax", "gst", "duties"]) or first,
        "general": _find_account(accounts, ["purchase", "expense", "general"]) or first,
    }


def _mapping(organization_id: str, accounts: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    key = "zoho_mapping_" + organization_id
    if key not in st.session_state:
        saved = _organization_settings(organization_id).get("mapping")
        st.session_state[key] = saved if isinstance(saved, dict) and saved else _default_mapping(accounts)
    return st.session_state[key]


def _classify_line(description: str) -> str:
    value = (description or "").upper()
    if any(word in value for word in ["CGST", "SGST", "IGST", "GST", "VAT", "TAX"]):
        return "tax"
    if any(word in value for word in ["FREIGHT", "SHIPPING", "TRANSPORT", "LOGISTICS", "DELIVERY"]):
        return "freight"
    if any(word in value for word in ["SERVICE", "LABOUR", "LABOR", "INSTALLATION", "REPAIR"]):
        return "services"
    if any(word in value for word in ["FEE", "CHARGE", "ADMIN", "PROCESSING"]):
        return "fees"
    if any(word in value for word in ["MATERIAL", "GOODS", "PRODUCT", "CHEMICAL", "RESIN", "STEEL", "PART"]):
        return "materials"
    return "general"


def _to_api_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _invoice_parts(payload: Dict[str, Any]) -> Dict[str, Any]:
    invoice = payload.get("INVOICE", {})
    header = invoice.get("INVOICE HEADER", {}) or {}
    rows = invoice.get("LINE ITEMS", {}).get("ROWS", []) or []
    payment = invoice.get("PAYMENT", {}).get("ELECTRONIC", {}) or {}
    return {
        "header": header,
        "rows": rows,
        "supplier": str(invoice.get("SELLER", {}).get("NAME", "") or "").strip(),
        "currency": str(payment.get("CURRENCY", "") or "").strip().upper(),
    }


def zoho_preflight(payload: Dict[str, Any]) -> List[PreflightIssue]:
    parts = _invoice_parts(payload)
    issues: List[PreflightIssue] = []
    if not zoho_is_connected():
        issues.append(PreflightIssue("not_connected", "Connect Zoho Books before posting."))
    if not _organization_id():
        issues.append(PreflightIssue("organization_missing", "Select a Zoho Books organization."))
    if not parts["supplier"]:
        issues.append(PreflightIssue("supplier_missing", "Supplier name is required.", "seller.name"))
    if not str(parts["header"].get("INVOICE NO.", "") or "").strip():
        issues.append(PreflightIssue("invoice_number_missing", "Invoice number is required.", "invoice_number"))
    if not parts["rows"]:
        issues.append(PreflightIssue("line_items_missing", "At least one invoice line is required.", "line_items"))
    for index, row in enumerate(parts["rows"], start=1):
        amount = _number(row.get("AMOUNT", 0) or row.get("EXTENDED AMOUNT", 0))
        if amount <= 0:
            issues.append(
                PreflightIssue(
                    "line_amount_invalid",
                    "Line " + str(index) + " needs a positive amount.",
                    "line_items." + str(index - 1) + ".amount",
                )
            )
    return issues


def _find_or_create_vendor(organization_id: str, supplier: str) -> Dict[str, Any]:
    body = _api_request(
        "GET",
        "/contacts",
        params={
            "organization_id": organization_id,
            "contact_type": "vendor",
            "search_text": supplier,
        },
    )
    contacts = body.get("contacts", []) if not body.get("_error") else []
    supplier_lower = supplier.casefold()
    for contact in contacts:
        names = {
            str(contact.get("contact_name", "")).casefold(),
            str(contact.get("company_name", "")).casefold(),
        }
        if supplier_lower in names:
            return contact
    created = _api_request(
        "POST",
        "/contacts",
        params={"organization_id": organization_id},
        json_body={
            "contact_name": supplier,
            "company_name": supplier,
            "contact_type": "vendor",
        },
    )
    return created.get("contact", {}) if not created.get("_error") else {"_error": created["_error"]}


def build_zoho_bill_payload(
    payload: Dict[str, Any],
    vendor_id: str,
    mapping: Dict[str, Dict[str, str]],
    classifier=None,
    default_tax_id: str = "",
) -> Dict[str, Any]:
    parts = _invoice_parts(payload)
    header = parts["header"]
    rows = parts["rows"]
    if classifier:
        try:
            rows = classifier.classify_invoice_rows(rows)
        except Exception:
            pass
    bill = {
        "vendor_id": vendor_id,
        "bill_number": str(header.get("INVOICE NO.", "") or "").strip(),
        "date": _to_api_date(header.get("INVOICE DATE", "")),
        "due_date": _to_api_date(header.get("DUE DATE", "")),
        "currency_code": parts["currency"],
        "reference_number": str(header.get("PO NO./CONTRACT NO.", "") or "").strip(),
        "notes": "Imported by EZ-Invoice",
        "line_items": [],
    }
    bill = {key: value for key, value in bill.items() if value != "" and value is not None}
    for row in rows:
        description = str(row.get("DESCRIPTION", "") or "Invoice line").strip()
        category = str(
            row.get("CLIENT_CATEGORY")
            or row.get("PLATFORM_CATEGORY")
            or row.get("CATEGORY")
            or _classify_line(description)
        ).strip().lower()
        if category not in dict(LINE_CATEGORIES):
            category = _classify_line(description)
        account = mapping.get(category) or mapping.get("general") or {}
        account_id = str(account.get("account_id", "") or "")
        if not account_id:
            raise ValueError("No Zoho Books account is mapped for line: " + description)
        amount = abs(_number(row.get("AMOUNT", 0) or row.get("EXTENDED AMOUNT", 0)))
        quantity = abs(_number(row.get("QUANTITY", 0))) or 1.0
        rate = abs(_number(row.get("UNIT PRICE", 0)))
        if rate <= 0:
            rate = amount / quantity if quantity else amount
        elif amount > 0 and abs((quantity * rate) - amount) > 0.02:
            rate = amount / quantity
        line = {
            "account_id": account_id,
            "description": description,
            "quantity": quantity,
            "rate": round(rate, 6),
        }
        unit = str(row.get("UOM", "") or "").strip()
        if unit:
            line["unit"] = unit
        tax_amount = abs(_number(row.get("TAX AMOUNT", 0)))
        explicit_tax_id = str(row.get("ZOHO_TAX_ID", "") or "").strip()
        selected_tax_id = explicit_tax_id or (default_tax_id if tax_amount > 0 else "")
        if selected_tax_id:
            line["tax_id"] = selected_tax_id
        bill["line_items"].append(line)
    return bill


def _sent_invoices(organization_id: str) -> Dict[str, str]:
    key = "zoho_sent_" + organization_id
    if key not in st.session_state:
        saved = _organization_settings(organization_id).get("sent_invoices")
        st.session_state[key] = saved if isinstance(saved, dict) else {}
    return st.session_state[key]


def _mark_sent(organization_id: str, invoice_number: str, bill_id: str) -> None:
    key = "zoho_sent_" + organization_id
    sent = dict(_sent_invoices(organization_id))
    sent[invoice_number] = bill_id
    st.session_state[key] = sent
    _save_organization_settings(organization_id, sent_invoices=sent)


def send_to_zoho(payload: Dict[str, Any], classifier=None) -> Dict[str, Any]:
    issues = zoho_preflight(payload)
    if issues:
        return ConnectorResult(False, issues[0].message, issues=issues).as_dict()
    organization_id = _organization_id()
    parts = _invoice_parts(payload)
    invoice_number = str(parts["header"].get("INVOICE NO.", "") or "").strip()
    duplicate_key = parts["supplier"].casefold() + "|" + invoice_number.casefold()
    sent = _sent_invoices(organization_id)
    if duplicate_key in sent:
        return ConnectorResult(
            False,
            "Already posted to Zoho Books as Bill #" + sent[duplicate_key],
            external_id=sent[duplicate_key],
        ).as_dict()

    vendor = _find_or_create_vendor(organization_id, parts["supplier"])
    vendor_id = str(vendor.get("contact_id", "") or "")
    if not vendor_id:
        return ConnectorResult(False, vendor.get("_error", "Zoho Books vendor could not be resolved.")).as_dict()
    accounts = _fetch_accounts(organization_id)
    mapping = _mapping(organization_id, accounts)
    default_tax_id = str(_organization_settings(organization_id).get("default_tax_id", "") or "")
    try:
        bill_payload = build_zoho_bill_payload(
            payload,
            vendor_id,
            mapping,
            classifier=classifier,
            default_tax_id=default_tax_id,
        )
    except (TypeError, ValueError) as exc:
        return ConnectorResult(False, str(exc)).as_dict()
    body = _api_request(
        "POST",
        "/bills",
        params={"organization_id": organization_id},
        json_body=bill_payload,
    )
    if body.get("_error"):
        return ConnectorResult(False, str(body["_error"]), raw=body).as_dict()
    bill = body.get("bill", {})
    bill_id = str(bill.get("bill_id", "") or "")
    if not bill_id:
        return ConnectorResult(False, "Zoho Books did not return a Bill ID.", raw=body).as_dict()
    _mark_sent(organization_id, duplicate_key, bill_id)
    total = bill.get("total", "")
    return ConnectorResult(
        True,
        "Zoho Books Bill #" + bill_id + " created for invoice " + invoice_number + ((" (" + str(total) + ")") if total != "" else ""),
        external_id=bill_id,
        raw=body,
    ).as_dict()


def build_zoho_export(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a readable export preview without requiring live Zoho IDs."""
    parts = _invoice_parts(payload)
    header = parts["header"]
    rows = []
    for row in parts["rows"]:
        amount = abs(_number(row.get("AMOUNT", 0) or row.get("EXTENDED AMOUNT", 0)))
        quantity = abs(_number(row.get("QUANTITY", 0))) or 1.0
        rate = abs(_number(row.get("UNIT PRICE", 0))) or (amount / quantity if quantity else amount)
        if amount > 0 and abs((quantity * rate) - amount) > 0.02:
            rate = amount / quantity
        rows.append(
            {
                "description": row.get("DESCRIPTION", ""),
                "quantity": quantity,
                "rate": rate,
                "unit": row.get("UOM", ""),
                "suggested_category": _classify_line(str(row.get("DESCRIPTION", ""))),
            }
        )
    return {
        "document_type": "bill",
        "vendor_name": parts["supplier"],
        "bill_number": header.get("INVOICE NO.", ""),
        "date": _to_api_date(header.get("INVOICE DATE", "")),
        "due_date": _to_api_date(header.get("DUE DATE", "")),
        "currency_code": parts["currency"],
        "reference_number": header.get("PO NO./CONTRACT NO.", ""),
        "line_items": rows,
    }


def _mapping_ui(
    organization_id: str,
    accounts: List[Dict[str, Any]],
    taxes: List[Dict[str, Any]],
) -> None:
    if not accounts:
        st.info("Refresh the Zoho Chart of Accounts before configuring mappings.")
        return
    labels: List[str] = []
    refs: Dict[str, Dict[str, str]] = {}
    for account in accounts:
        label = _account_label(account)
        if label in refs:
            label += " #" + str(account.get("account_id", ""))
        labels.append(label)
        refs[label] = _account_ref(account)
    mapping = dict(_mapping(organization_id, accounts))
    with st.expander("Zoho Account Mapping", expanded=True):
        st.caption("Map universal invoice categories to this organization's expense or purchase accounts.")
        for category, category_label in LINE_CATEGORIES:
            current_id = str((mapping.get(category) or {}).get("account_id", ""))
            selected_index = next(
                (index for index, label in enumerate(labels) if refs[label]["account_id"] == current_id),
                0,
            )
            selected = st.selectbox(
                category_label,
                labels,
                index=selected_index,
                key="zoho_map_" + organization_id + "_" + category,
            )
            mapping[category] = refs[selected]
        settings = _organization_settings(organization_id)
        tax_labels = ["No automatic tax"]
        tax_refs = {"No automatic tax": ""}
        for tax in taxes:
            name = str(tax.get("tax_name", "") or tax.get("name", "") or "Tax")
            percentage = tax.get("tax_percentage", "")
            label = name + ((" · " + str(percentage) + "%") if percentage != "" else "")
            tax_labels.append(label)
            tax_refs[label] = str(tax.get("tax_id", "") or "")
        current_tax_id = str(settings.get("default_tax_id", "") or "")
        current_tax_index = next(
            (index for index, label in enumerate(tax_labels) if tax_refs[label] == current_tax_id),
            0,
        )
        selected_tax = st.selectbox(
            "Default purchase tax for lines containing extracted tax",
            tax_labels,
            index=current_tax_index,
            key="zoho_default_purchase_tax_" + organization_id,
        )
        if st.button("Save Zoho account mapping", type="primary", key="zoho_save_mapping"):
            st.session_state["zoho_mapping_" + organization_id] = mapping
            if _save_organization_settings(
                organization_id,
                mapping=mapping,
                default_tax_id=tax_refs[selected_tax],
            ):
                st.success("Zoho Books account mapping saved.")
            else:
                st.warning("Mapping is active for this session, but local persistence failed.")


def zoho_sidebar(show_heading: bool = True) -> None:
    if show_heading:
        st.markdown("### Zoho Books")
    if not CLIENT_ID or not CLIENT_SECRET:
        st.warning("Set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in environment variables or Streamlit secrets.")
        st.caption(
            "Register `http://localhost:8001/zoho/callback` in the Zoho API Console. "
            "The complete environment-variable commands are in `ZOHO_BOOKS_SETUP.md`."
        )
        return

    complete_zoho_auth_if_ready()
    if not zoho_is_connected():
        if st.button("Connect Zoho Books", type="primary", key="zoho_connect"):
            url = _auth_url()
            st.session_state["_zoho_auth_url"] = url
            if _uses_local_callback() and not st.session_state.get("_zoho_server_started"):
                _start_callback_server()
                st.session_state["_zoho_server_started"] = True
            if _uses_local_callback():
                webbrowser.open(url)
            _set_auth_pending(True)
            st.rerun()
        if st.session_state.get("_zoho_auth_pending"):
            st.info("Finish signing in to Zoho Books, then return here.")
            url = st.session_state.get("_zoho_auth_url")
            if url:
                st.link_button("Continue to Zoho sign-in", url, type="primary")
            if _uses_local_callback():
                _request_auth_refresh()
        return

    st.success("Zoho Books connected")
    refresh_orgs = st.button("Refresh organizations", key="zoho_refresh_orgs")
    organizations = _fetch_organizations(force=refresh_orgs)
    if not organizations:
        st.warning("No Zoho Books organizations were returned for this account.")
    else:
        labels = [
            str(org.get("name", "Organization")) + " (" + str(org.get("organization_id", "")) + ")"
            for org in organizations
        ]
        by_label = {label: org for label, org in zip(labels, organizations)}
        current_id = _organization_id()
        index = next(
            (
                item_index
                for item_index, org in enumerate(organizations)
                if str(org.get("organization_id", "")) == current_id
            ),
            0,
        )
        selected_label = st.selectbox("Zoho Books organization", labels, index=index, key="zoho_org_selector")
        selected_org = by_label[selected_label]
        organization_id = str(selected_org.get("organization_id", ""))
        st.session_state["zoho_organization_id"] = organization_id
        st.caption(
            str(selected_org.get("currency_code", ""))
            + (" · " + str(selected_org.get("country", "")) if selected_org.get("country") else "")
        )
        refresh_accounts = st.button("Refresh Chart of Accounts", key="zoho_refresh_accounts")
        accounts = _fetch_accounts(organization_id, force=refresh_accounts)
        taxes = _fetch_taxes(organization_id, force=refresh_accounts)
        if accounts:
            st.caption(str(len(accounts)) + " accounts available for mapping")
        if taxes:
            st.caption(str(len(taxes)) + " tax codes available")
        _mapping_ui(organization_id, accounts, taxes)

    if st.button("Disconnect Zoho Books", key="zoho_disconnect"):
        for key in [
            "zoho_access_token",
            "zoho_refresh_token",
            "zoho_token_expires_at",
            "zoho_api_domain",
            "zoho_organization_id",
            "_zoho_auth_pending",
            "_zoho_oauth_state",
            "_zoho_auth_url",
        ]:
            st.session_state.pop(key, None)
        st.rerun()
