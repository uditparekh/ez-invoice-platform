"""Platform-side client for the local EZ-Invoice Tally Connector."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


CONNECTOR_SETTINGS_FILE = Path(__file__).with_name("tally_connector_settings.json")


def _env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def load_connector_settings() -> Dict[str, Any]:
    settings = {
        "enabled": True,
        "url": _env_value("EZ_TALLY_CONNECTOR_URL", "http://127.0.0.1:8765"),
        "token": _env_value("EZ_TALLY_CONNECTOR_TOKEN", "client-test-token"),
        "workspace_id": _env_value("EZ_WORKSPACE_ID", "client-test"),
    }
    try:
        if CONNECTOR_SETTINGS_FILE.exists():
            saved = json.loads(CONNECTOR_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update({k: v for k, v in saved.items() if v is not None})
    except Exception:
        pass
    return settings


def save_connector_settings(settings: Dict[str, Any]) -> bool:
    try:
        CONNECTOR_SETTINGS_FILE.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
        return True
    except Exception:
        return False


def _headers(token: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-EZ-Connector-Token"] = token
    return headers


def connector_request(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    method: str = "POST",
    timeout: int = 20,
) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed"}
    settings = settings or load_connector_settings()
    base_url = str(settings.get("url") or "").rstrip("/")
    if not base_url:
        return {"success": False, "message": "Set the connector URL first."}
    url = base_url + "/" + path.lstrip("/")
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=_headers(str(settings.get("token", ""))), timeout=timeout)
        else:
            response = requests.post(url, json=payload or {}, headers=_headers(str(settings.get("token", ""))), timeout=timeout)
    except Exception as exc:
        return {"success": False, "message": "Connector request failed: " + str(exc)}
    try:
        data = response.json()
    except Exception:
        data = {"message": response.text[:300]}
    data.setdefault("status_code", response.status_code)
    if response.status_code >= 400:
        data["success"] = False
        data.setdefault("message", "Connector HTTP " + str(response.status_code))
    return data


def connector_health(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return connector_request("/health", settings=settings, method="GET", timeout=5)


def connector_test_tally(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = settings or load_connector_settings()
    return connector_request(
        "/connector/test-tally",
        payload={"workspace_id": settings.get("workspace_id", "")},
        settings=settings,
        timeout=15,
    )


def send_xml_batch_to_connector(
    vouchers: List[Dict[str, str]],
    settings: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    settings = settings or load_connector_settings()
    payload = {
        "workspace_id": settings.get("workspace_id", ""),
        "dry_run": bool(dry_run),
        "vouchers": vouchers,
    }
    return connector_request("/connector/vouchers", payload=payload, settings=settings, timeout=60)
