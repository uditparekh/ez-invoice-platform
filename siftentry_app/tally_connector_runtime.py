"""Runtime helpers for the SiftEntry Tally connector.

This module is intentionally UI-free. The command-line connector, local Flask
bridge, and Windows status window all call the same functions so posting
behavior stays consistent.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


APP_VERSION = "0.3.0"


@dataclass(frozen=True)
class ConnectorConfig:
    cloud_url: str = ""
    workspace_id: str = "local-workspace"
    token: str = ""
    tally_url: str = "http://localhost:9000"
    poll_interval: int = 15
    claim_limit: int = 5
    dry_run: bool = False


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SiftEntry" / "TallyConnector" / "connector_config.json"
    return Path.home() / ".siftentry" / "tally_connector_config.json"


def default_status_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SiftEntry" / "TallyConnector" / "connector_status.json"
    return Path.home() / ".siftentry" / "tally_connector_status.json"


def load_config(path: Optional[Path] = None) -> ConnectorConfig:
    config_path = path or default_config_path()
    raw: Dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw.update(loaded)
        except Exception:
            pass
    return ConnectorConfig(
        cloud_url=str(raw.get("cloud_url") or os.environ.get("SIFTENTRY_CLOUD_URL", "")),
        workspace_id=str(raw.get("workspace_id") or os.environ.get("EZ_WORKSPACE_ID", "local-workspace")),
        token=str(raw.get("token") or os.environ.get("EZ_TALLY_CONNECTOR_TOKEN", "")),
        tally_url=str(raw.get("tally_url") or os.environ.get("TALLY_URL", "http://localhost:9000")),
        poll_interval=max(5, int(raw.get("poll_interval") or os.environ.get("EZ_TALLY_POLL_INTERVAL", "15"))),
        claim_limit=max(1, min(25, int(raw.get("claim_limit") or os.environ.get("EZ_TALLY_CLAIM_LIMIT", "5")))),
        dry_run=bool(raw.get("dry_run", False)),
    )


def save_config(config: ConnectorConfig, path: Optional[Path] = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cloud_url": config.cloud_url,
        "workspace_id": config.workspace_id,
        "token": config.token,
        "tally_url": config.tally_url,
        "poll_interval": config.poll_interval,
        "claim_limit": config.claim_limit,
        "dry_run": config.dry_run,
    }
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return config_path


def write_status(status: Dict[str, Any], path: Optional[Path] = None) -> Path:
    status_path = path or default_status_path()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(status)
    payload.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    payload.setdefault("host", socket.gethostname())
    status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return status_path


def auth_headers(token: str, content_type: str = "application/json") -> Dict[str, str]:
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-SiftEntry-Connector-Token"] = token
    return headers


def parse_tally_response(text: str) -> Dict[str, Any]:
    result = {
        "created": 0,
        "altered": 0,
        "errors": 0,
        "line_error": "",
        "voucher_number": "",
        "raw": text,
    }
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        result["line_error"] = text[:500]
        result["errors"] = 1
        return result
    for tag, key in [
        ("CREATED", "created"),
        ("ALTERED", "altered"),
        ("ERRORS", "errors"),
        ("VCHNUMBER", "voucher_number"),
        ("LINEERROR", "line_error"),
    ]:
        node = root.find(".//" + tag)
        if node is None or node.text is None:
            continue
        if key in ("created", "altered", "errors"):
            try:
                result[key] = int(float(node.text.strip()))
            except ValueError:
                result[key] = 0
        else:
            result[key] = node.text.strip()
    return result


def post_xml_to_tally(tally_url: str, invoice_id: str, xml: str, dry_run: bool = False) -> Dict[str, Any]:
    if not xml.strip():
        return {"invoice_id": invoice_id, "success": False, "message": "Missing XML"}
    try:
        ET.fromstring(xml)
    except ET.ParseError as exc:
        return {"invoice_id": invoice_id, "success": False, "message": "Invalid XML: " + str(exc)}
    if dry_run:
        return {"invoice_id": invoice_id, "success": True, "message": "Dry run accepted"}
    if not requests:
        return {"invoice_id": invoice_id, "success": False, "message": "requests is not installed"}
    try:
        response = requests.post(
            tally_url,
            data=xml.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            timeout=30,
        )
    except Exception as exc:
        return {"invoice_id": invoice_id, "success": False, "message": "Tally post failed: " + str(exc)}
    parsed = parse_tally_response(response.text)
    ok = response.status_code == 200 and parsed.get("errors") == 0 and (
        parsed.get("created") or parsed.get("altered")
    )
    return {
        "invoice_id": invoice_id,
        "success": bool(ok),
        "message": "Posted to Tally" if ok else (parsed.get("line_error") or response.text[:300]),
        "status_code": response.status_code,
        "response": parsed,
        "external_id": str(parsed.get("voucher_number") or parsed.get("master_id") or "") or None,
        "raw": {
            "status_code": response.status_code,
            "response": parsed,
        },
    }


def test_tally_connection(tally_url: str) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests not installed"}
    try:
        response = requests.get(tally_url, timeout=6)
        text = response.text.strip()
        if response.status_code == 200 and text:
            return {"success": True, "message": "Tally responded on " + tally_url + ": " + text[:120]}
        if response.status_code == 200:
            return {"success": True, "message": "Tally responded on " + tally_url}
    except Exception:
        return {
            "success": False,
            "message": "Tally port check failed. Open TallyPrime, load the company, and confirm port 9000 is enabled.",
        }
    return {"success": False, "message": "HTTP " + str(response.status_code) + ": " + response.text[:160]}



def cloud_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def connector_metadata(tally_detected: Optional[bool] = None) -> Dict[str, Any]:
    return {
        "connector_host": socket.gethostname(),
        "connector_version": APP_VERSION,
        "tally_detected": tally_detected,
    }


def send_cloud_heartbeat(config: ConnectorConfig, tally_detected: Optional[bool] = None) -> Dict[str, Any]:
    """Tell SiftEntry the connector is alive even when no jobs can be claimed."""
    if not requests:
        return {"success": False, "message": "requests is not installed"}
    try:
        response = requests.post(
            cloud_url(config.cloud_url, "/api/v1/connectors/tally/heartbeat"),
            json={
                "workspace_id": config.workspace_id,
                **connector_metadata(tally_detected),
            },
            headers=auth_headers(config.token),
            timeout=15,
        )
    except Exception as exc:
        return {"success": False, "message": "Cloud heartbeat failed: " + str(exc)}
    try:
        data = response.json()
    except Exception:
        data = {"message": response.text[:300]}
    data.setdefault("success", response.status_code < 400)
    data["status_code"] = response.status_code
    return data


def claim_cloud_jobs(config: ConnectorConfig) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed", "jobs": []}
    try:
        response = requests.post(
            cloud_url(config.cloud_url, "/api/v1/connectors/tally/jobs/claim"),
            json={
                "workspace_id": config.workspace_id,
                "limit": config.claim_limit,
                "dry_run": config.dry_run,
                **connector_metadata(tally_detected=True),
            },
            headers=auth_headers(config.token),
            timeout=30,
        )
    except Exception as exc:
        return {"success": False, "message": "Cloud claim failed: " + str(exc), "jobs": []}
    try:
        data = response.json()
    except Exception:
        data = {"message": response.text[:500]}
    data.setdefault("success", response.status_code < 400)
    data.setdefault("jobs", [])
    data["status_code"] = response.status_code
    return data


def submit_cloud_results(config: ConnectorConfig, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed"}
    try:
        response = requests.post(
            cloud_url(config.cloud_url, "/api/v1/connectors/tally/jobs/results"),
            json={"workspace_id": config.workspace_id, "results": results},
            headers=auth_headers(config.token),
            timeout=30,
        )
    except Exception as exc:
        return {"success": False, "message": "Cloud result submit failed: " + str(exc)}
    try:
        data = response.json()
    except Exception:
        data = {"message": response.text[:500]}
    data.setdefault("success", response.status_code < 400)
    data["status_code"] = response.status_code
    return data


def poll_once(config: ConnectorConfig) -> Dict[str, Any]:
    if not config.cloud_url.strip():
        return {
            "success": False,
            "connected_to_siftentry": False,
            "tally_detected": False,
            "message": "SiftEntry cloud URL is missing.",
            "claimed": 0,
            "submitted": 0,
            "failed_jobs": 0,
        }
    if not config.token.strip():
        return {
            "success": False,
            "connected_to_siftentry": False,
            "tally_detected": False,
            "message": "Connector token is missing.",
            "claimed": 0,
            "submitted": 0,
            "failed_jobs": 0,
        }

    tally_result = {"success": True, "message": "Dry run does not require Tally."}
    if not config.dry_run:
        tally_result = test_tally_connection(config.tally_url)
        if not tally_result.get("success"):
            # Stay visible to SiftEntry so the web app shows the connector as
            # online with Tally down, instead of silently disappearing.
            heartbeat = send_cloud_heartbeat(config, tally_detected=False)
            return {
                "success": False,
                "connected_to_siftentry": bool(heartbeat.get("success")),
                "tally_detected": False,
                "message": str(tally_result.get("message") or "TallyPrime is not reachable."),
                "claimed": 0,
                "submitted": 0,
                "failed_jobs": 0,
                "tally": tally_result,
                "heartbeat": heartbeat,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

    claimed = claim_cloud_jobs(config)
    jobs = claimed.get("jobs") or []
    results: List[Dict[str, Any]] = []
    last_invoice = ""
    for job in jobs:
        tally_url = str(job.get("tally_url") or config.tally_url)
        result = post_xml_to_tally(
            tally_url,
            invoice_id=str(job.get("invoice_id") or ""),
            xml=str(job.get("xml") or ""),
            dry_run=bool(job.get("dry_run")),
        )
        result["posting_id"] = str(job.get("posting_id") or "")
        results.append(result)
        last_invoice = str(job.get("invoice_number") or job.get("invoice_id") or last_invoice)

    submitted: Dict[str, Any] = {"success": True, "accepted": 0}
    if results:
        submitted = submit_cloud_results(config, results)

    failed_jobs = len([result for result in results if not result.get("success")])
    success = bool(claimed.get("success")) and bool(submitted.get("success"))
    message = "Idle. No approved Tally jobs."
    if not claimed.get("success"):
        message = str(claimed.get("message") or "Could not reach SiftEntry.")
    elif results:
        message = str(submitted.get("message") or f"Submitted {submitted.get('accepted', len(results))} result(s).")
    return {
        "success": success,
        "connected_to_siftentry": bool(claimed.get("success")),
        "tally_detected": True,
        "message": message,
        "claimed": len(jobs),
        "submitted": int(submitted.get("accepted", len(results)) or 0),
        "failed_jobs": failed_jobs,
        "last_posted_invoice": last_invoice,
        "claim": claimed,
        "submit": submitted,
        "results": results,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
