"""QuickBooks Online integration for universal supplier invoice processing."""

import time
import base64
import hashlib
import hmac
import threading
import webbrowser
import json
import os
import secrets as pysecrets
from pathlib import Path
from urllib.parse import urlencode, urlparse

import streamlit as st
import streamlit.components.v1 as components

try:
    import requests
except ImportError:
    requests = None

def _config_value(name, default=""):
    process_env = globals().get("_PROCESS_ENV", {})
    value = process_env.get(name)
    if value:
        return value
    value = os.environ.get(name)
    if value:
        return value
    try:
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


_PROCESS_ENV = dict(os.environ)

CLIENT_ID = _config_value("QB_CLIENT_ID")
CLIENT_SECRET = _config_value("QB_CLIENT_SECRET")
REDIRECT_URI = _config_value("QB_REDIRECT_URI", "http://localhost:8003/callback")
QB_ENVIRONMENT = (_config_value("QB_ENVIRONMENT", _config_value("QB_ENV", "sandbox")) or "sandbox").strip().lower()
if QB_ENVIRONMENT not in {"sandbox", "production"}:
    QB_ENVIRONMENT = "sandbox"
_QB_DEFAULT_BASE_URL = (
    "https://quickbooks.api.intuit.com"
    if QB_ENVIRONMENT == "production"
    else "https://sandbox-quickbooks.api.intuit.com"
)
_QB_BASE_URL_OVERRIDE = _PROCESS_ENV.get("QB_BASE_URL", "")
if not _QB_BASE_URL_OVERRIDE and not (_PROCESS_ENV.get("QB_ENVIRONMENT") or _PROCESS_ENV.get("QB_ENV")):
    _QB_BASE_URL_OVERRIDE = _config_value("QB_BASE_URL", "")
QB_BASE_URL = _QB_BASE_URL_OVERRIDE or _QB_DEFAULT_BASE_URL

_callback_data = {"code": None, "realm_id": None, "state": None, "error": None}
_QB_SETTINGS_FILE = Path(__file__).with_name("qb_account_mappings.json")
_QB_OAUTH_STATE_TTL_SECONDS = 10 * 60
_consumed_oauth_states = {}
_oauth_state_lock = threading.Lock()

QB_LINE_CATEGORIES = [
    ("materials", "Materials / goods"),
    ("services", "Services / labour"),
    ("freight", "Freight / logistics"),
    ("fees", "Other fees"),
    ("tax", "Taxes"),
    ("general", "Default / other"),
]

_CATEGORY_LABELS = dict(QB_LINE_CATEGORIES)
_RULE_FIELDS = [
    ("description", "Description"),
    ("category", "Category"),
    ("supplier", "Supplier"),
    ("customer", "Customer"),
    ("invoice_no", "Invoice number"),
    ("currency", "Currency"),
    ("hsn", "HSN / SAC"),
    ("uom", "Unit of measure"),
    ("amount", "Amount"),
]
_RULE_OPERATORS = ["contains", "equals", "starts with", "ends with", "not contains", ">=", "<="]

def _oauth_state_signature(message):
    key = (CLIENT_SECRET or CLIENT_ID or "ez-invoice-local-oauth").encode("utf-8")
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _new_oauth_state():
    message = "qb." + str(int(time.time())) + "." + pysecrets.token_urlsafe(24)
    return message + "." + _oauth_state_signature(message)


def _prune_consumed_oauth_states(now=None):
    current = float(now if now is not None else time.time())
    expired = [
        state
        for state, consumed_at in _consumed_oauth_states.items()
        if current - consumed_at > _QB_OAUTH_STATE_TTL_SECONDS
    ]
    for state in expired:
        _consumed_oauth_states.pop(state, None)


def _get_auth_url():
    state = _new_oauth_state()
    st.session_state["_qb_oauth_state"] = state
    return "https://appcenter.intuit.com/connect/oauth2?" + urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": REDIRECT_URI, "state": state})


def _redirect_host():
    try:
        return (urlparse(REDIRECT_URI).hostname or "").lower()
    except Exception:
        return ""


def _uses_local_callback():
    explicit = str(_config_value("QB_USE_LOCAL_CALLBACK", "")).strip().lower()
    if explicit in {"1", "true", "yes", "y"}:
        return True
    if explicit in {"0", "false", "no", "n"}:
        return False
    return _redirect_host() in {"localhost", "127.0.0.1"}


def _production_config_warnings():
    warnings = []
    if QB_ENVIRONMENT == "production":
        parsed = urlparse(REDIRECT_URI)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}:
            warnings.append("Production QuickBooks redirect URI must be a registered HTTPS URL.")
        if "sandbox-quickbooks" in QB_BASE_URL:
            warnings.append("QuickBooks is set to production, but the API base URL still points to sandbox.")
    return warnings

def _exchange_code(auth_code):
    ah = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()
    r = requests.post("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        headers={"Authorization": "Basic " + ah, "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "code": auth_code, "redirect_uri": REDIRECT_URI})
    return r.json() if r.status_code == 200 else None

def _refresh_tok(rt):
    ah = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()
    r = requests.post("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        headers={"Authorization": "Basic " + ah, "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": rt})
    return r.json() if r.status_code == 200 else None

def _start_callback_server():
    try:
        from flask import Flask, request as freq
    except ImportError:
        st.error("Flask not installed. Run: pip install flask")
        return
    app = Flask(__name__)
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    parsed = urlparse(REDIRECT_URI)
    callback_path = parsed.path or "/callback"
    callback_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    callback_host = parsed.hostname or "127.0.0.1"

    @app.route(callback_path)
    def cb():
        c = freq.args.get("code")
        rm = freq.args.get("realmId")
        state = freq.args.get("state")
        e = freq.args.get("error")
        if c:
            _callback_data["code"] = c
            _callback_data["realm_id"] = rm
            _callback_data["state"] = state
            _callback_data["error"] = None
            return "<h1 style='color:green;text-align:center;padding:60px'>QuickBooks Connected! Close this tab.</h1>"
        _callback_data["error"] = e or "QuickBooks authorization failed"
        return "<h1 style='color:red;text-align:center;padding:60px'>Failed: " + str(e) + "</h1>"
    threading.Thread(
        target=lambda: app.run(
            host=callback_host,
            port=callback_port,
            debug=False,
        ),
        daemon=True,
    ).start()
    time.sleep(1)


def _set_qb_auth_pending(pending):
    st.session_state["_qb_auth_pending"] = bool(pending)
    try:
        if pending:
            st.query_params["qb_auth"] = "pending"
        elif "qb_auth" in st.query_params:
            del st.query_params["qb_auth"]
    except Exception:
        pass


def _is_qb_auth_pending():
    try:
        if st.query_params.get("qb_auth") == "pending":
            return True
    except Exception:
        pass
    return bool(st.session_state.get("_qb_auth_pending"))


def _request_qb_auth_refresh():
    components.html(
        """
        <script>
        setTimeout(function() {
            window.parent.location.reload();
        }, 1500);
        </script>
        """,
        height=0,
    )


def _capture_qb_callback_from_query():
    try:
        code = st.query_params.get("code")
        realm = st.query_params.get("realmId") or st.query_params.get("realm_id")
        state = st.query_params.get("state")
        error = st.query_params.get("error")
    except Exception:
        return False

    if not any([code, realm, error]):
        return False
    if state and not str(state).startswith("qb."):
        return False

    _callback_data["code"] = code
    _callback_data["realm_id"] = realm
    _callback_data["state"] = state
    _callback_data["error"] = error
    return True


def _clear_qb_callback_query_params():
    try:
        for key in ["code", "realmId", "realm_id", "state", "error", "error_description", "qb_auth"]:
            if key in st.query_params:
                del st.query_params[key]
        st.query_params["page"] = "QuickBooks"
        st.query_params["target"] = "QuickBooks"
    except Exception:
        pass


def _qb_state_is_valid(state):
    if not state:
        return False

    state = str(state)
    expected = st.session_state.get("_qb_oauth_state")
    if expected and not hmac.compare_digest(state, str(expected)):
        return False

    try:
        provider, timestamp_text, nonce, signature = state.split(".", 3)
        if provider != "qb":
            return False
        issued_at = int(timestamp_text)
    except (TypeError, ValueError):
        return False

    message = provider + "." + timestamp_text + "." + nonce
    if not hmac.compare_digest(signature, _oauth_state_signature(message)):
        return False

    now = time.time()
    if issued_at > now + 60 or now - issued_at > _QB_OAUTH_STATE_TTL_SECONDS:
        return False

    with _oauth_state_lock:
        _prune_consumed_oauth_states(now)
        if state in _consumed_oauth_states:
            return False
        _consumed_oauth_states[state] = now
    return True


def _complete_qb_auth_if_ready():
    _capture_qb_callback_from_query()

    if _callback_data.get("error"):
        err = _callback_data["error"]
        _callback_data["error"] = None
        _callback_data["code"] = None
        _callback_data["realm_id"] = None
        _callback_data["state"] = None
        _set_qb_auth_pending(False)
        _clear_qb_callback_query_params()
        st.error("QuickBooks authorization failed: " + str(err))
        return True

    if not _callback_data.get("code"):
        return False

    code = _callback_data["code"]
    realm = _callback_data["realm_id"]
    state = _callback_data["state"]
    _callback_data["code"] = None
    _callback_data["realm_id"] = None
    _callback_data["state"] = None

    if not _qb_state_is_valid(state):
        _set_qb_auth_pending(False)
        _clear_qb_callback_query_params()
        st.error("QuickBooks authorization state did not match. Please connect again.")
        return True

    tokens = _exchange_code(code)
    if tokens:
        st.session_state["qb_access_token"] = tokens["access_token"]
        st.session_state["qb_refresh_token"] = tokens.get("refresh_token", "")
        st.session_state["qb_realm_id"] = realm
        st.session_state["qb_token_expires_at"] = time.time() + tokens.get("expires_in", 3600)
        st.session_state.pop("_qb_oauth_state", None)
        st.session_state.pop("_qb_auth_url", None)
        _set_qb_auth_pending(False)
        _clear_qb_callback_query_params()
        st.success("QuickBooks connected!")
        st.rerun()

    _set_qb_auth_pending(False)
    _clear_qb_callback_query_params()
    st.error("Failed to get QuickBooks token. Try connecting again.")
    return True


def complete_qb_auth_if_ready():
    """Complete a local or hosted QuickBooks OAuth callback."""
    return _complete_qb_auth_if_ready()


def is_connected():
    return bool(st.session_state.get("qb_access_token")) and bool(st.session_state.get("qb_realm_id"))

def _ensure_token():
    if time.time() > st.session_state.get("qb_token_expires_at", 0) - 60:
        rt = st.session_state.get("qb_refresh_token")
        if rt:
            t = _refresh_tok(rt)
            if t:
                st.session_state["qb_access_token"] = t["access_token"]
                st.session_state["qb_refresh_token"] = t.get("refresh_token", rt)
                st.session_state["qb_token_expires_at"] = time.time() + t.get("expires_in", 3600)
                return True
        return False
    return True


def classify_qb_line(description):
    """Coarse QuickBooks category from the parsed line DESCRIPTION."""
    desc = (description or "").upper()

    if any(k in desc for k in ["CGST", "SGST", "IGST", "GST", "VAT", "TAX", "EXCISE"]):
        return "tax"
    if any(k in desc for k in ["FREIGHT", "SHIPPING", "TRANSPORT", "LOGISTICS", "DELIVERY"]):
        return "freight"
    if any(k in desc for k in ["SERVICE", "LABOUR", "LABOR", "INSTALLATION", "REPAIR", "MAINTENANCE"]):
        return "services"
    if any(k in desc for k in ["POLYETHYLENE", "GLYCOL", "PTA", "LLDPE", "RESIN", "CHEMICAL", "MATERIAL", "GOODS", "PRODUCT"]):
        return "materials"
    if any(k in desc for k in ["FEE", "CHARGE", "ADMIN", "PROCESSING"]):
        return "fees"
    return "general"


def _settings_key(rid, name):
    return "qb_" + name + "_" + str(rid or "default")


def _load_all_qb_settings():
    try:
        if _QB_SETTINGS_FILE.exists():
            with _QB_SETTINGS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_all_qb_settings(data):
    try:
        with _QB_SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        return True
    except Exception:
        return False


def _load_client_qb_settings(rid):
    data = _load_all_qb_settings()
    settings = data.get(str(rid), {})
    return settings if isinstance(settings, dict) else {}


def _save_client_qb_settings(rid, mapping=None, rules=None):
    data = _load_all_qb_settings()
    current = data.get(str(rid), {})
    if not isinstance(current, dict):
        current = {}
    if mapping is not None:
        current["mapping"] = mapping
    if rules is not None:
        current["rules"] = rules
    data[str(rid)] = current
    return _save_all_qb_settings(data)


def _account_ref(account):
    if not account:
        return {}
    return {
        "name": account.get("Name") or account.get("name", ""),
        "value": str(account.get("Id") or account.get("value", "")),
    }


def _account_label(account):
    name = account.get("Name") or account.get("name", "Unnamed")
    acct_type = account.get("AccountType") or account.get("type", "")
    detail = account.get("AccountSubType") or account.get("SubAccount", "")
    suffix = " / ".join(str(x) for x in [acct_type, detail] if x)
    return name + (" (" + suffix + ")" if suffix else "")


def _query_qb_accounts(at, rid):
    if not requests:
        return []
    try:
        r = requests.get(
            QB_BASE_URL + "/v3/company/" + rid + "/query",
            headers={"Authorization": "Bearer " + at, "Accept": "application/json"},
            params={"query": "SELECT * FROM Account MAXRESULTS 1000"},
            timeout=30,
        )
    except Exception:
        return []
    if r.status_code != 200:
        return []

    accounts = r.json().get("QueryResponse", {}).get("Account", []) or []
    expense_types = {"Expense", "Other Expense", "Cost of Goods Sold"}
    filtered = [
        a for a in accounts
        if a.get("Active", True) and (a.get("AccountType") in expense_types or not a.get("AccountType"))
    ]
    return filtered or accounts


def _get_qb_accounts(at, rid, force=False):
    key = _settings_key(rid, "accounts")
    if not force and st.session_state.get(key):
        return st.session_state[key]
    accounts = _query_qb_accounts(at, rid)
    st.session_state[key] = accounts
    return accounts


def _find_account_by_hints(accounts, hints):
    for hint in hints:
        h = hint.lower()
        for account in accounts:
            if h in _account_label(account).lower():
                return _account_ref(account)
    return {}


def _smart_default_mapping(accounts):
    first = _account_ref(accounts[0]) if accounts else {}
    return {
        "materials": _find_account_by_hints(accounts, ["material", "purchase", "inventory", "goods"]) or first,
        "services": _find_account_by_hints(accounts, ["service", "labour", "labor", "expense"]) or first,
        "freight": _find_account_by_hints(accounts, ["freight", "shipping", "transport", "delivery"]) or first,
        "fees": _find_account_by_hints(accounts, ["fee", "charge", "admin", "misc"]) or first,
        "tax": _find_account_by_hints(accounts, ["tax", "gst", "vat", "excise"]) or first,
        "general": _find_account_by_hints(accounts, ["general", "expense", "misc"]) or first,
    }


def _get_account_mapping(rid, accounts):
    key = _settings_key(rid, "account_mapping")
    if key not in st.session_state:
        saved = _load_client_qb_settings(rid).get("mapping")
        st.session_state[key] = saved if isinstance(saved, dict) and saved else _smart_default_mapping(accounts)
    return st.session_state[key]


def _get_qb_rules(rid):
    key = _settings_key(rid, "account_rules")
    if key not in st.session_state:
        saved = _load_client_qb_settings(rid).get("rules")
        st.session_state[key] = saved if isinstance(saved, list) else []
    return st.session_state[key]


def _get_sent_invoices(rid):
    key = _settings_key(rid, "sent_invoices")
    if key not in st.session_state:
        saved = _load_client_qb_settings(rid).get("sent_invoices")
        st.session_state[key] = saved if isinstance(saved, dict) else {}
    return st.session_state[key]


def _mark_invoice_sent(rid, inv_no, bill_id):
    key = _settings_key(rid, "sent_invoices")
    sent = dict(st.session_state.get(key, {}))
    sent[inv_no] = bill_id
    st.session_state[key] = sent

    data = _load_all_qb_settings()
    current = data.get(str(rid), {})
    if not isinstance(current, dict):
        current = {}
    current["sent_invoices"] = sent
    data[str(rid)] = current
    _save_all_qb_settings(data)


def _line_context(payload, row):
    inv = payload.get("INVOICE", {})
    h = inv.get("INVOICE HEADER", {}) or {}
    payment = inv.get("PAYMENT", {}).get("ELECTRONIC", {}) or {}
    desc = row.get("DESCRIPTION", "")
    category = classify_qb_line(desc)
    return {
        "description": desc,
        "category": category,
        "category_label": _CATEGORY_LABELS.get(category, category),
        "supplier": inv.get("SELLER", {}).get("NAME", ""),
        "customer": inv.get("BILL TO", {}).get("NAME", ""),
        "invoice_no": h.get("INVOICE NO.", ""),
        "currency": payment.get("CURRENCY", ""),
        "hsn": row.get("HSN/SAC", ""),
        "uom": row.get("UOM", ""),
        "amount": float(row.get("AMOUNT", 0) or 0),
    }


def _normalize_category(value):
    v = str(value or "").strip().lower()
    for key, label in QB_LINE_CATEGORIES:
        if v in {key.lower(), label.lower()}:
            return key
    return v


def _rule_matches(rule, context):
    if not rule.get("enabled", True):
        return False

    field = rule.get("field", "description")
    op = rule.get("operator", "contains")
    expected = rule.get("value", "")
    actual = context.get(field, "")

    if field == "category":
        actual_norm = _normalize_category(actual)
        expected_norm = _normalize_category(expected)
        if op == "equals":
            return actual_norm == expected_norm
        actual = actual_norm + " " + str(context.get("category_label", ""))

    if field == "amount" or op in {">=", "<="}:
        try:
            actual_num = float(actual or 0)
            expected_num = float(str(expected).replace(",", "") or 0)
        except Exception:
            return False
        return actual_num >= expected_num if op == ">=" else actual_num <= expected_num

    actual_text = str(actual or "").lower()
    expected_text = str(expected or "").lower()
    if op == "equals":
        return actual_text == expected_text
    if op == "starts with":
        return actual_text.startswith(expected_text)
    if op == "ends with":
        return actual_text.endswith(expected_text)
    if op == "not contains":
        return expected_text not in actual_text
    return expected_text in actual_text


def _resolve_line_account(payload, row, accounts, mapping, rules, fallback_acct):
    context = _line_context(payload, row)
    for rule in rules:
        if _rule_matches(rule, context):
            acct = rule.get("account", {})
            if acct.get("value"):
                return acct, context["category"], rule.get("name", "")

    mapped = mapping.get(context["category"]) or mapping.get("general") or fallback_acct
    if mapped and mapped.get("value"):
        return mapped, context["category"], ""
    return fallback_acct, context["category"], ""


def _classifier_account(classifier, row, accounts):
    if not classifier:
        return None, ""
    try:
        gl_info = classifier.get_gl_info(row.get("DESCRIPTION", ""))
    except Exception:
        return None, ""

    gl_code = str(gl_info.get("gl_code", "")).strip()
    if not gl_code:
        return None, gl_info.get("subcategory", "")

    for account in accounts:
        if str(account.get("Id", "")).strip() == gl_code or str(account.get("AcctNum", "")).strip() == gl_code:
            return _account_ref(account), gl_info.get("subcategory", "")
    return None, gl_info.get("subcategory", "")


def _resolve_line_account_with_classifier(payload, row, accounts, mapping, rules, fallback_acct, classifier=None):
    line_acct, category, rule_name = _resolve_line_account(payload, row, accounts, mapping, rules, fallback_acct)
    source = "Tier 3 rule" if rule_name else "Tier 2 QB category mapping"
    if not rule_name:
        classifier_acct, classifier_category = _classifier_account(classifier, row, accounts)
        if classifier_acct and classifier_acct.get("value"):
            line_acct = classifier_acct
            category = classifier_category or category
            source = "Client worksheet GL"
    return line_acct, category, rule_name, source


def resolve_line_account_for_export(payload, row, classifier=None):
    """Return QuickBooks Tier 2/3 routing details for Excel/export display."""
    if not requests or not is_connected() or not _ensure_token():
        return {}
    at = st.session_state["qb_access_token"]
    rid = st.session_state["qb_realm_id"]
    accounts = _get_qb_accounts(at, rid)
    fallback_acct = _find_expense_account(at, rid, accounts=accounts)
    mapping = _get_account_mapping(rid, accounts)
    rules = _get_qb_rules(rid)
    line_acct, category, rule_name, source = _resolve_line_account_with_classifier(
        payload, row, accounts, mapping, rules, fallback_acct, classifier
    )
    return {
        "QB_CATEGORY": _CATEGORY_LABELS.get(category, category),
        "QB_CATEGORY_KEY": category,
        "QB_ACCOUNT": line_acct.get("name", ""),
        "QB_ACCOUNT_ID": line_acct.get("value", ""),
        "QB_RULE": rule_name,
        "QB_MAPPING_SOURCE": source,
    }


def _find_expense_account(at, rid, accounts=None):
    if accounts:
        default_mapping = _smart_default_mapping(accounts)
        if default_mapping.get("general"):
            return default_mapping["general"]
    try:
        r = requests.get(
            QB_BASE_URL + "/v3/company/" + rid + "/query",
            headers={"Authorization": "Bearer " + at, "Accept": "application/json"},
            params={"query": "SELECT * FROM Account WHERE AccountType = 'Expense' MAXRESULTS 5"},
            timeout=30,
        )
    except Exception:
        return {}
    if r.status_code == 200:
        accts = r.json().get("QueryResponse", {}).get("Account", [])
        if accts:
            return {"name": accts[0]["Name"], "value": accts[0]["Id"]}
    return {}

def _find_or_create_vendor(at, rid, vn):
    clean_name = str(vn or "").strip()
    if not clean_name:
        return {"_error": "Invoice supplier name is missing."}
    query_name = clean_name.replace("\\", "\\\\").replace("'", "\\'")
    try:
        r = requests.get(
            QB_BASE_URL + "/v3/company/" + rid + "/query",
            headers={"Authorization": "Bearer " + at, "Accept": "application/json"},
            params={"query": "SELECT * FROM Vendor WHERE DisplayName = '" + query_name + "'"},
            timeout=30,
        )
    except Exception as exc:
        return {"_error": "QuickBooks vendor lookup failed: " + str(exc)}
    if r.status_code == 200:
        vs = r.json().get("QueryResponse", {}).get("Vendor", [])
        if vs:
            return {"name": vs[0]["DisplayName"], "value": vs[0]["Id"]}
    try:
        r = requests.post(
            QB_BASE_URL + "/v3/company/" + rid + "/vendor",
            headers={"Authorization": "Bearer " + at, "Content-Type": "application/json", "Accept": "application/json"},
            json={"DisplayName": clean_name},
            timeout=30,
        )
    except Exception as exc:
        return {"_error": "QuickBooks vendor creation failed: " + str(exc)}
    if r.status_code == 200:
        v = r.json()["Vendor"]
        return {"name": v["DisplayName"], "value": v["Id"]}
    return {"_error": "QuickBooks vendor error " + str(r.status_code) + ": " + _qb_error_message(r)}

def _to_qb_date(value: str) -> str:
    """Normalize common invoice date formats for the QuickBooks API."""
    from datetime import datetime

    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _qb_error_message(response):
    try:
        fault = response.json().get("Fault", {})
        errors = fault.get("Error", []) or []
        details = []
        for error in errors:
            message = str(error.get("Message") or "").strip()
            detail = str(error.get("Detail") or "").strip()
            code = str(error.get("code") or "").strip()
            text = ": ".join(part for part in [message, detail] if part)
            if code:
                text = ("[" + code + "] " + text).strip()
            if text:
                details.append(text)
        if details:
            return "; ".join(details)
    except Exception:
        pass
    return str(getattr(response, "text", "") or "")[:500] or "Unknown QuickBooks error"


def _quickbooks_bill_payload(payload, vendor_ref, accounts, mapping, rules, fallback_acct, classifier=None):
    inv = payload.get("INVOICE", {})
    header = inv.get("INVOICE HEADER", {}) or {}
    rows = inv.get("LINE ITEMS", {}).get("ROWS", []) or []
    payment = inv.get("PAYMENT", {}).get("ELECTRONIC", {}) or {}
    inv_no = str(header.get("INVOICE NO.", "") or "").strip()
    currency = str(payment.get("CURRENCY", "") or "").strip().upper()

    bill = {
        "VendorRef": vendor_ref,
        "DocNumber": inv_no,
        "PrivateNote": "Imported by EZ-Invoice",
        "Line": [],
    }
    txn_date = _to_qb_date(header.get("INVOICE DATE", ""))
    due_date = _to_qb_date(header.get("DUE DATE", ""))
    if txn_date:
        bill["TxnDate"] = txn_date
    if due_date:
        bill["DueDate"] = due_date
    if currency:
        bill["CurrencyRef"] = {"value": currency}

    po_no = str(header.get("PO NO./CONTRACT NO.", "") or "").strip()
    if po_no and po_no.upper() != "N/A":
        bill["PrivateNote"] += " | PO: " + po_no

    for row in rows:
        line_acct, _category, rule_name, _source = _resolve_line_account_with_classifier(
            payload, row, accounts, mapping, rules, fallback_acct, classifier
        )
        if not line_acct or not line_acct.get("value"):
            raise ValueError("No QuickBooks expense account is mapped for line: " + str(row.get("DESCRIPTION", "")))
        try:
            amount = abs(float(row.get("AMOUNT", 0) or row.get("EXTENDED AMOUNT", 0) or 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        line_note = str(row.get("DESCRIPTION", "") or "Invoice line").strip()
        if rule_name:
            line_note += " [Rule: " + rule_name + "]"
        bill["Line"].append(
            {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": round(amount, 2),
                "Description": line_note,
                "AccountBasedExpenseLineDetail": {"AccountRef": line_acct},
            }
        )
    return bill

def send_to_quickbooks(payload, classifier=None):
    if not requests:
        return {"success": False, "message": "requests not installed", "bill_id": None}
    if not is_connected():
        return {"success": False, "message": "QuickBooks not connected", "bill_id": None}
    if not _ensure_token():
        return {"success": False, "message": "Token expired. Reconnect.", "bill_id": None}
    at = st.session_state["qb_access_token"]
    rid = st.session_state["qb_realm_id"]
    inv = payload["INVOICE"]
    h = inv["INVOICE HEADER"]
    rows = inv.get("LINE ITEMS", {}).get("ROWS", []) or []
    inv_no = str(h.get("INVOICE NO.", "") or "").strip()
    if not inv_no:
        return {"success": False, "message": "Invoice number is required before sending to QuickBooks.", "bill_id": None}
    if not rows:
        return {"success": False, "message": "No line items", "bill_id": None}
    sent = _get_sent_invoices(rid)
    if inv_no in sent:
        return {"success": False, "message": "Already sent (Bill #" + sent[inv_no] + ")", "bill_id": sent[inv_no]}
    accounts = _get_qb_accounts(at, rid)
    acct = _find_expense_account(at, rid, accounts=accounts)
    if not acct or not acct.get("value"):
        return {
            "success": False,
            "message": "No QuickBooks expense or cost-of-goods account is available. Refresh the Chart of Accounts and configure mapping.",
            "bill_id": None,
        }
    mapping = _get_account_mapping(rid, accounts)
    rules = _get_qb_rules(rid)
    vn = str(inv.get("SELLER", {}).get("NAME", "") or "").strip()
    if not vn or vn.lower() == "unknown supplier":
        return {"success": False, "message": "Supplier name is required before sending to QuickBooks.", "bill_id": None}
    vref = _find_or_create_vendor(at, rid, vn)
    if not vref.get("value"):
        return {"success": False, "message": vref.get("_error", "QuickBooks vendor could not be resolved."), "bill_id": None}
    try:
        bill = _quickbooks_bill_payload(payload, vref, accounts, mapping, rules, acct, classifier)
    except ValueError as exc:
        return {"success": False, "message": str(exc), "bill_id": None}
    if not bill["Line"]:
        return {"success": False, "message": "No positive invoice line amounts are available for QuickBooks.", "bill_id": None}

    endpoint = QB_BASE_URL + "/v3/company/" + rid + "/bill"
    headers = {
        "Authorization": "Bearer " + at,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        r = requests.post(endpoint, headers=headers, json=bill, timeout=45)
    except Exception as exc:
        return {"success": False, "message": "QuickBooks bill request failed: " + str(exc), "bill_id": None}
    if r.status_code == 200:
        res = r.json()["Bill"]
        bid = res["Id"]
        _mark_invoice_sent(rid, inv_no, bid)
        currency = str(inv.get("PAYMENT", {}).get("ELECTRONIC", {}).get("CURRENCY", "") or "")
        total_label = (currency + " " if currency else "") + str(res.get("TotalAmt", ""))
        return {
            "success": True,
            "message": "QuickBooks Bill #" + bid + " created for invoice " + inv_no + " (" + total_label.strip() + ")",
            "bill_id": bid,
        }
    if r.status_code in (429, 500, 502, 503):
        time.sleep(1)
        try:
            r = requests.post(endpoint, headers=headers, json=bill, timeout=45)
        except Exception as exc:
            return {"success": False, "message": "QuickBooks retry failed: " + str(exc), "bill_id": None}
        if r.status_code == 200:
            res = r.json()["Bill"]
            bid = res["Id"]
            _mark_invoice_sent(rid, inv_no, bid)
            return {
                "success": True,
                "message": "QuickBooks Bill #" + bid + " created for invoice " + inv_no + " after retry.",
                "bill_id": bid,
            }
    return {
        "success": False,
        "message": "QuickBooks error " + str(r.status_code) + ": " + _qb_error_message(r),
        "bill_id": None,
    }


def _account_select_options(accounts):
    labels = []
    refs = {}
    for account in accounts:
        label = _account_label(account)
        if label in refs:
            label = label + " #" + str(account.get("Id", ""))
        labels.append(label)
        refs[label] = _account_ref(account)
    return labels, refs


def _account_index(labels, refs, selected_ref):
    selected_value = str((selected_ref or {}).get("value", ""))
    for idx, label in enumerate(labels):
        if str(refs[label].get("value", "")) == selected_value:
            return idx
    return 0


def _qb_account_mapping_ui(rid, accounts):
    if not accounts:
        st.info("Connect QuickBooks and refresh the Chart of Accounts to configure account mapping.")
        return

    labels, refs = _account_select_options(accounts)
    mapping_key = _settings_key(rid, "account_mapping")
    mapping = dict(_get_account_mapping(rid, accounts))

    with st.expander("QB Account Mapping", expanded=False):
        st.caption("Tier 2: choose where each invoice line category posts in this client's QuickBooks.")

        if st.button("Use smart defaults", key="qb_use_smart_defaults"):
            mapping = _smart_default_mapping(accounts)
            st.session_state[mapping_key] = mapping
            _save_client_qb_settings(rid, mapping=mapping)
            st.success("Smart defaults saved.")
            st.rerun()

        for category, label in QB_LINE_CATEGORIES:
            current = mapping.get(category) or refs[labels[0]]
            selected = st.selectbox(
                label,
                labels,
                index=_account_index(labels, refs, current),
                key="qb_map_" + category + "_" + str(rid),
            )
            mapping[category] = refs[selected]

        if st.button("Save QB account mapping", key="qb_save_account_mapping"):
            st.session_state[mapping_key] = mapping
            if _save_client_qb_settings(rid, mapping=mapping):
                st.success("QuickBooks account mapping saved.")
            else:
                st.warning("Mapping saved for this session, but local file persistence failed.")


def _qb_rules_ui(rid, accounts):
    if not accounts:
        return

    labels, refs = _account_select_options(accounts)
    rules_key = _settings_key(rid, "account_rules")
    rules = list(_get_qb_rules(rid))

    with st.expander("Advanced QB Rules", expanded=False):
        st.caption("Tier 3: first matching rule overrides the category mapping for a bill line.")

        with st.form("qb_add_rule_" + str(rid)):
            name = st.text_input("Rule name", value="", placeholder="GST materials to purchase account")
            col1, col2 = st.columns(2)
            with col1:
                field_labels = [label for _, label in _RULE_FIELDS]
                field_lookup = {label: key for key, label in _RULE_FIELDS}
                field_label = st.selectbox("If field", field_labels, index=0)
            with col2:
                operator = st.selectbox("Operator", _RULE_OPERATORS, index=0)
            value = st.text_input("Value", placeholder="Example: GST, freight, material, vendor name")
            account_label = st.selectbox("Post to account", labels, index=0)
            enabled = st.checkbox("Enabled", value=True, key="qb_new_rule_enabled_" + str(rid))
            submitted = st.form_submit_button("Add rule")

        if submitted:
            rule = {
                "enabled": enabled,
                "name": name.strip() or field_label + " " + operator + " " + value,
                "field": field_lookup[field_label],
                "operator": operator,
                "value": value.strip(),
                "account": refs[account_label],
            }
            rules.append(rule)
            st.session_state[rules_key] = rules
            _save_client_qb_settings(rid, rules=rules)
            st.success("Rule added.")
            st.rerun()

        if not rules:
            st.caption("No advanced rules yet.")
            return

        changed = False
        delete_idx = None
        for idx, rule in enumerate(rules):
            cols = st.columns([0.12, 0.68, 0.2])
            with cols[0]:
                enabled_value = st.checkbox(
                    "Enabled",
                    value=bool(rule.get("enabled", True)),
                    key="qb_rule_enabled_" + str(rid) + "_" + str(idx),
                    label_visibility="collapsed",
                )
                if enabled_value != rule.get("enabled", True):
                    rule["enabled"] = enabled_value
                    changed = True
            with cols[1]:
                acct_name = rule.get("account", {}).get("name", "")
                st.caption(
                    rule.get("name", "Rule") + ": " +
                    rule.get("field", "description") + " " +
                    rule.get("operator", "contains") + " " +
                    repr(rule.get("value", "")) + " -> " + acct_name
                )
            with cols[2]:
                if st.button("Delete", key="qb_delete_rule_" + str(rid) + "_" + str(idx)):
                    delete_idx = idx

        if delete_idx is not None:
            rules.pop(delete_idx)
            st.session_state[rules_key] = rules
            _save_client_qb_settings(rid, rules=rules)
            st.rerun()

        if changed and st.button("Save rule changes", key="qb_save_rule_changes_" + str(rid)):
            st.session_state[rules_key] = rules
            _save_client_qb_settings(rid, rules=rules)
            st.success("Rule changes saved.")


def qb_sidebar(show_heading=True):
    if show_heading:
        st.markdown("### QuickBooks")
    if not CLIENT_ID or not CLIENT_SECRET:
        st.warning("Set QB_CLIENT_ID and QB_CLIENT_SECRET in Streamlit secrets or environment variables.")
        return
    for warning in _production_config_warnings():
        st.warning(warning)
    _complete_qb_auth_if_ready()
    if is_connected():
        realm = st.session_state.get("qb_realm_id", "")
        sn = len(_get_sent_invoices(realm))
        st.success("Connected (Realm: " + realm + ")")
        st.caption("Environment: " + QB_ENVIRONMENT.title())
        if sn:
            st.caption(str(sn) + " invoice(s) sent this session")
        at = st.session_state.get("qb_access_token", "")
        refresh_accounts = st.button("Refresh Chart of Accounts", key="qb_refresh_accounts")
        accounts = _get_qb_accounts(at, realm, force=refresh_accounts) if at and realm else []
        if accounts:
            st.caption(str(len(accounts)) + " expense account(s) available for mapping")
        _qb_account_mapping_ui(realm, accounts)
        _qb_rules_ui(realm, accounts)
        if st.button("Disconnect", key="qb_disconnect"):
            for k in [
                "qb_access_token",
                "qb_refresh_token",
                "qb_realm_id",
                "qb_token_expires_at",
                "_qb_auth_pending",
                "_qb_oauth_state",
                "_qb_auth_url",
            ]:
                st.session_state.pop(k, None)
            st.rerun()
    else:
        if st.button("Connect QuickBooks", key="qb_connect", type="primary"):
            auth_url = _get_auth_url()
            st.session_state["_qb_auth_url"] = auth_url
            if _uses_local_callback() and not st.session_state.get("_qb_server_started"):
                _start_callback_server()
                st.session_state["_qb_server_started"] = True
            if _uses_local_callback():
                webbrowser.open(auth_url)
            _set_qb_auth_pending(True)
            st.rerun()
        if _is_qb_auth_pending():
            st.info("Finish signing in to QuickBooks, then return here.")
            auth_url = st.session_state.get("_qb_auth_url")
            if auth_url:
                st.link_button("Continue to QuickBooks sign-in", auth_url, type="primary")
            if _uses_local_callback():
                _request_qb_auth_refresh()
