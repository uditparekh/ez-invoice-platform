"""HTTP client and compatibility helpers for the Streamlit-to-FastAPI bridge."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests


class SiftEntryApiError(RuntimeError):
    """Raised when the SiftEntry API cannot complete a request."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SiftEntryApiClient:
    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 30.0
    access_token: str = ""
    refresh_token: str = ""
    current_user: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        authenticated: bool = True,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        timeout = kwargs.pop("timeout", self.timeout)
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated and self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        try:
            response = requests.request(
                method,
                self.base_url + path,
                timeout=timeout,
                headers=headers,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise SiftEntryApiError(f"SiftEntry API is unavailable: {exc}") from exc

        if (
            response.status_code == 401
            and authenticated
            and retry_auth
            and self.refresh_token
        ):
            self.refresh()
            return self._request(
                method,
                path,
                authenticated=authenticated,
                retry_auth=False,
                **kwargs,
            )

        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else body
            except ValueError:
                detail = response.text
            message = str(detail or f"API request failed with HTTP {response.status_code}.")
            raise SiftEntryApiError(message, status_code=response.status_code)

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise SiftEntryApiError("SiftEntry API returned an invalid response.") from exc

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health", authenticated=False, timeout=1.5)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        tokens = self._request(
            "POST",
            "/api/v1/auth/login",
            authenticated=False,
            json={"email": email, "password": password},
        )
        self._apply_tokens(tokens)
        return tokens

    def bootstrap_owner(
        self,
        email: str,
        password: str,
        full_name: str,
        organization_name: str,
        legal_names: Iterable[str],
        default_currency: str = "USD",
    ) -> Dict[str, Any]:
        tokens = self._request(
            "POST",
            "/api/v1/auth/bootstrap",
            authenticated=False,
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
                "organization_name": organization_name,
                "legal_names": list(legal_names),
                "default_currency": default_currency,
            },
        )
        self._apply_tokens(tokens)
        return tokens

    def authenticate_for_pilot(
        self,
        email: str,
        password: str,
        full_name: str,
        organization_name: str,
        legal_names: Iterable[str],
        default_currency: str = "USD",
    ) -> Dict[str, Any]:
        try:
            return self.login(email, password)
        except SiftEntryApiError as login_error:
            if login_error.status_code != 401:
                raise
        try:
            return self.bootstrap_owner(
                email=email,
                password=password,
                full_name=full_name,
                organization_name=organization_name,
                legal_names=legal_names,
                default_currency=default_currency,
            )
        except SiftEntryApiError as bootstrap_error:
            if bootstrap_error.status_code == 409:
                raise SiftEntryApiError(
                    "FastAPI authentication failed. Check EZ_API_EMAIL and "
                    "EZ_API_PASSWORD for the existing owner account.",
                    status_code=401,
                ) from bootstrap_error
            raise

    def refresh(self) -> Dict[str, Any]:
        if not self.refresh_token:
            raise SiftEntryApiError("No refresh token is available.", status_code=401)
        tokens = self._request(
            "POST",
            "/api/v1/auth/refresh",
            authenticated=False,
            retry_auth=False,
            json={"refresh_token": self.refresh_token},
        )
        self._apply_tokens(tokens)
        return tokens

    def me(self) -> Dict[str, Any]:
        user = self._request("GET", "/api/v1/auth/me")
        self.current_user = user
        return user

    def _apply_tokens(self, tokens: Dict[str, Any]) -> None:
        self.access_token = str(tokens.get("access_token") or "")
        self.refresh_token = str(tokens.get("refresh_token") or "")
        self.current_user = tokens.get("user") or None

    def list_organizations(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/v1/organizations")

    def ensure_organization(
        self,
        name: str,
        legal_names: Optional[Iterable[str]] = None,
        default_currency: str = "USD",
        organization_id: str = "",
    ) -> Dict[str, Any]:
        organizations = self.list_organizations()
        if organization_id:
            match = next(
                (organization for organization in organizations if organization.get("id") == organization_id),
                None,
            )
            if match:
                return match
            raise SiftEntryApiError("The configured SiftEntry organization was not found.")

        normalized_name = name.strip().casefold()
        match = next(
            (
                organization
                for organization in organizations
                if str(organization.get("name", "")).strip().casefold() == normalized_name
            ),
            None,
        )
        if match:
            return match
        return self._request(
            "POST",
            "/api/v1/organizations",
            json={
                "name": name.strip() or "Client Workspace",
                "legal_names": [value.strip() for value in legal_names or [] if value.strip()],
                "default_currency": (default_currency or "USD").strip().upper(),
            },
        )

    def list_client_profiles(
        self,
        organization_id: str,
        accounting_system: str = "",
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if accounting_system:
            params["accounting_system"] = accounting_system
        return self._request(
            "GET",
            f"/api/v1/organizations/{organization_id}/client-profiles",
            params=params,
        )

    def create_client_profile(
        self,
        organization_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/organizations/{organization_id}/client-profiles",
            json=payload,
        )

    def update_client_profile(
        self,
        organization_id: str,
        profile_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._request(
            "PATCH",
            f"/api/v1/organizations/{organization_id}/client-profiles/{profile_id}",
            json=payload,
        )

    def set_default_client_profile(
        self,
        organization_id: str,
        profile_id: str,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/set-default",
        )

    def delete_client_profile(self, organization_id: str, profile_id: str) -> None:
        self._request(
            "DELETE",
            f"/api/v1/organizations/{organization_id}/client-profiles/{profile_id}",
        )

    def upload_invoice(
        self,
        organization_id: str,
        filename: str,
        pdf_bytes: bytes,
        parser_mode: str = "auto",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/invoices/upload",
            params={"organization_id": organization_id, "parser_mode": parser_mode},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            timeout=max(self.timeout, 90),
        )

    def list_invoices(self, organization_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self._request(
            "GET",
            "/api/v1/invoices",
            params={"organization_id": organization_id, "limit": limit},
        )

    def validate_invoice(self, invoice_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/invoices/{invoice_id}/validate")

    def approve_invoice(self, invoice_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/invoices/{invoice_id}/approve")

    def post_invoice(
        self,
        invoice_id: str,
        target: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/invoices/{invoice_id}/post",
            json={"target": target, "dry_run": bool(dry_run)},
            timeout=max(self.timeout, 90),
        )

    def record_posting_result(
        self,
        invoice_id: str,
        target: str,
        result: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        external_id = (
            result.get("external_id")
            or result.get("bill_id")
            or result.get("voucher_number")
        )
        return self._request(
            "POST",
            f"/api/v1/invoices/{invoice_id}/posting-results",
            json={
                "target": target,
                "success": bool(result.get("success")),
                "dry_run": bool(dry_run),
                "message": str(result.get("message", "Posting completed.")),
                "external_id": str(external_id) if external_id else None,
                "issues": result.get("issues", []) or [],
                "raw": _json_safe(result),
            },
        )

    def clear_invoices(self, organization_id: str) -> Dict[str, Any]:
        return self._request(
            "DELETE",
            f"/api/v1/organizations/{organization_id}/invoices",
        )


def parser_mode_for_api(value: str) -> str:
    normalized = (value or "Auto").strip().lower()
    if "ai" in normalized or "ocr" in normalized:
        return "ai_assisted"
    if "gst" in normalized:
        return "gst/e-invoice adapter"
    if normalized == "auto":
        return "auto"
    return "universal extraction"


def invoice_to_legacy_payload(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay an API invoice onto the payload format consumed by the pilot UI."""

    payload = copy.deepcopy(invoice.get("raw_payload") or {})
    legacy = payload.setdefault("INVOICE", {})
    document = legacy.setdefault("DOCUMENT", {})
    header = legacy.setdefault("INVOICE HEADER", {})
    payment = legacy.setdefault("PAYMENT", {}).setdefault("ELECTRONIC", {})

    document["SOURCE FILE"] = invoice.get("source_file", "")
    document["PARSER"] = invoice.get("parser", "Generic")
    document["EXTRACTION ENGINE"] = invoice.get("extraction_engine", "")
    document["PAGES"] = invoice.get("page_count", 1)

    header["INVOICE NO."] = invoice.get("invoice_number", "")
    header["INVOICE DATE"] = invoice.get("invoice_date", "")
    header["DUE DATE"] = invoice.get("due_date", "")
    header["PO NO./CONTRACT NO."] = invoice.get("purchase_order") or "N/A"
    header["INVOICE AMOUNT"] = invoice.get("total", 0)
    header["AMOUNT TO BE EFT DRAFTED"] = invoice.get("total", 0)

    payment["CURRENCY"] = invoice.get("currency", "USD")
    payment["AMOUNT"] = invoice.get("total", 0)
    legacy["SELLER"] = _legacy_party(invoice.get("supplier") or {})
    legacy["BILL TO"] = _legacy_party(invoice.get("customer") or {})
    legacy["ROUTING"] = {"DIRECTION": invoice.get("direction", "inbound")}
    legacy["INVOICE TAX SUMMARY"] = {"TOTAL TAX": invoice.get("tax_total", 0)}

    rows = []
    for line in invoice.get("lines", []) or []:
        rows.append(
            {
                "DESCRIPTION": line.get("description", ""),
                "QUANTITY": line.get("quantity", 0),
                "UOM": line.get("uom", ""),
                "UNIT PRICE": line.get("unit_price", 0),
                "EXTENDED AMOUNT": line.get("net_amount", 0),
                "TAX AMOUNT": line.get("tax_amount", 0),
                "AMOUNT": line.get("total_amount", 0),
                "HSN/SAC": line.get("hsn_sac", ""),
                "CATEGORY": line.get("category", ""),
                "PLATFORM_CATEGORY": line.get("category", ""),
                "GL_CODE": line.get("gl_code", ""),
            }
        )
    legacy["LINE ITEMS"] = {
        "COLUMNS": [
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
        ],
        "ROWS": rows,
    }
    return payload


def invoice_to_session_data(invoice: Dict[str, Any]) -> Dict[str, Any]:
    status = str(invoice.get("status", "extracted"))
    return {
        "payload": invoice_to_legacy_payload(invoice),
        "text": "",
        "bytes": b"",
        "engine": invoice.get("extraction_engine", ""),
        "pages": invoice.get("page_count", 1),
        "ok": status in {"validated", "approved", "posting", "posted"},
        "issues": invoice.get("validation_issues", []) or [],
        "missing_df": None,
        "api_invoice_id": invoice.get("id", ""),
        "api_status": status,
        "api_created_at": invoice.get("created_at", ""),
        "api_updated_at": invoice.get("updated_at", ""),
        "source_file": invoice.get("source_file", ""),
    }


def session_key_for_invoice(invoice: Dict[str, Any], used: set[str]) -> str:
    filename = str(invoice.get("source_file") or "invoice.pdf")
    candidate = filename
    if candidate in used:
        stem, dot, suffix = filename.rpartition(".")
        token = str(invoice.get("id", ""))[:8]
        candidate = f"{stem or filename}__{token}{dot}{suffix}" if dot else f"{filename}__{token}"
    used.add(candidate)
    return candidate


def _legacy_party(party: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "NAME": party.get("name", ""),
        "ADDRESS": party.get("address", []) or [],
        "GSTIN": party.get("tax_id", ""),
        "EMAIL": party.get("email", ""),
        "PHONE": party.get("phone", ""),
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)
