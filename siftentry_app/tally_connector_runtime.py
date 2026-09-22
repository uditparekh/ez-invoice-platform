"""Runtime helpers for the SiftEntry Tally connector.

This module is intentionally UI-free. The command-line connector, local Flask
bridge, and Windows status window all call the same functions so posting
behavior stays consistent.
"""

from __future__ import annotations

import json
import os
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

try:
    from .connector_credentials import valid_connector_token, TOKEN_FORMAT_MESSAGE
    from .tally_master_sync import read_snapshot, MasterSyncError
except ImportError:  # direct script / frozen desktop entrypoint
    from connector_credentials import valid_connector_token, TOKEN_FORMAT_MESSAGE
    from tally_master_sync import read_snapshot, MasterSyncError

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


APP_VERSION = "0.6.0"


@dataclass(frozen=True)
class ConnectorConfig:
    cloud_url: str = ""
    workspace_id: str = "local-workspace"
    token: str = ""
    tally_url: str = "http://localhost:9000"
    poll_interval: int = 15
    claim_limit: int = 5
    dry_run: bool = False
    config_path: str = ""


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SiftEntry" / "TallyConnector" / "connector_config.json"
    return Path.home() / ".siftentry" / "tally_connector_config.json"


# ---------------------------------------------------------------------------
# Durable acknowledgement outbox
#
# A Tally posting can succeed while the acknowledgement to SiftEntry fails
# (network blip, laptop lid closed). If that result only lived in memory it
# would be lost, SiftEntry would keep the invoice as "posting", and nobody
# could safely tell whether the voucher exists. So every result is written to
# disk BEFORE the first acknowledgement attempt, and every poll drains the
# outbox first. A voucher is never re-posted because the cloud did not hear
# about it; only the acknowledgement is retried.
# ---------------------------------------------------------------------------

def default_outbox_path(config_path: str = "") -> Path:
    base = Path(config_path) if config_path else default_config_path()
    if base.name in {"connector_config.json", "tally_connector_config.json"}:
        return base.with_name("results_outbox.json")
    return base.with_suffix(".results-outbox.json")


class OutboxUnreadable(RuntimeError):
    """The on-disk outbox exists but cannot be parsed. Never treat as empty."""


def read_outbox(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        raise OutboxUnreadable(f"{path} is unreadable: {exc}") from exc
    if not isinstance(data, list):
        raise OutboxUnreadable(f"{path} has unexpected content")
    seen = set()
    for item in data:
        if (not isinstance(item, dict) or not isinstance(item.get("posting_id"), str)
                or not item["posting_id"].strip() or not isinstance(item.get("success"), bool)
                or item["posting_id"] in seen):
            raise OutboxUnreadable(f"{path} contains an invalid or duplicate result")
        seen.add(item["posting_id"])
    return data


def write_outbox(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as output:
        json.dump(items, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    tmp.replace(path)
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def append_outbox(path: Path, results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    items = read_outbox(path)
    known = {str(item.get("posting_id") or "") for item in items}
    for result in results:
        if str(result.get("posting_id") or "") not in known:
            items.append(dict(result, queued_at=datetime.now().isoformat(timespec="seconds")))
            known.add(str(result.get("posting_id") or ""))
    write_outbox(path, items)


def drain_outbox(config: "ConnectorConfig", path: Path) -> Dict[str, Any]:
    """Retry acknowledgement for everything still on disk. Never re-posts."""
    pending = read_outbox(path)
    if not pending:
        return {"success": True, "accepted": 0, "pending": 0}
    for item in pending:
        if (item.get("connector_workspace_id", config.workspace_id) != config.workspace_id
                or item.get("connector_cloud_url", config.cloud_url.rstrip("/")) != config.cloud_url.rstrip("/")):
            raise OutboxUnreadable(f"{path} belongs to different connector settings; restore the original workspace")
    # A timeout is not proof Tally rejected a voucher. Never turn an uncertain
    # outcome into a retryable failure. Keep evidence until manual reconciliation.
    uncertain = [item for item in pending if item.get("outcome_uncertain")]
    confirmed = [item for item in pending if not item.get("outcome_uncertain")]
    if not confirmed:
        return {"success": False, "pending": len(pending), "uncertain": True,
                "message": "Outcome uncertain. Check Tally with support before retrying; do not re-enter vouchers."}
    submitted = submit_cloud_results(config, confirmed)
    if (submitted.get("success") and submitted.get("accepted") == len(confirmed)
            and not submitted.get("rejected")):
        write_outbox(path, uncertain)
        if uncertain:
            return {"success": False, "pending": len(uncertain), "uncertain": True,
                    "message": "Outcome uncertain. Check Tally with support before retrying; do not re-enter vouchers."}
        return {"success": True, "accepted": len(confirmed), "pending": 0}
    return {
        "success": False,
        "accepted": 0,
        "pending": len(pending),
        "message": str(submitted.get("message") or "Acknowledgement failed; will retry."),
    }



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
        config_path=str(config_path),
    )


def save_config(config: ConnectorConfig, path: Optional[Path] = None) -> Path:
    config_path = path or (Path(config.config_path) if config.config_path else default_config_path())
    pending = read_outbox(default_outbox_path(str(config_path)))
    for item in pending:
        if (item.get("connector_workspace_id", config.workspace_id) != config.workspace_id
                or item.get("connector_cloud_url", config.cloud_url.rstrip("/")) != config.cloud_url.rstrip("/")):
            raise OutboxUnreadable("Pending results belong to the original URL/workspace. Reconcile them before changing connection identity.")
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
    temp = status_path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(status_path)
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
    except Exception:
        return {"invoice_id": invoice_id, "success": False, "outcome_uncertain": True,
                "message": "Tally did not confirm the result. Outcome uncertain; do not repost. Contact support."}
    parsed = parse_tally_response(response.text)
    ok = response.status_code == 200 and parsed.get("errors") == 0 and (
        parsed.get("created") or parsed.get("altered")
    )
    return {
        "invoice_id": invoice_id,
        "success": bool(ok),
        "outcome_uncertain": not ok and not (
            response.status_code == 200 and parsed.get("line_error")
            and not parsed.get("created") and not parsed.get("altered")
            and "<LINEERROR" in response.text.upper()
        ),
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
    return read_tally_companies(tally_url)



def cloud_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def connector_metadata(tally_detected: Optional[bool] = None) -> Dict[str, Any]:
    return {
        "connector_host": socket.gethostname(),
        "connector_version": APP_VERSION,
        "tally_detected": tally_detected,
    }


def connection_config_error(config: ConnectorConfig) -> str:
    try:
        url = urlsplit(config.cloud_url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            return "Use a base SiftEntry URL such as https://app.siftentry.com, without /app or other paths."
        if url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return "Use HTTPS for SiftEntry. Plain HTTP is allowed only for local development."
    except ValueError:
        return "SiftEntry URL is invalid. Use https://app.siftentry.com."
    if not config.workspace_id.strip():
        return "Workspace ID is missing. Copy it from the client profile."
    if not valid_connector_token(config.token):
        return TOKEN_FORMAT_MESSAGE
    return ""


def cloud_request(config: ConnectorConfig, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """One secret-safe error path for all connector calls; redirects never carry tokens."""
    problem = connection_config_error(config)
    if problem:
        return {"success": False, "message": problem}
    if not requests:
        return {"success": False, "message": "Connector HTTP support is missing. Reinstall the connector."}
    try:
        response = requests.post(cloud_url(config.cloud_url, path), json=payload,
                                 headers=auth_headers(config.token), timeout=30,
                                 allow_redirects=False)
    except Exception:
        # Exception messages can contain URLs or invalid Authorization values.
        return {"success": False, "message": "Could not reach SiftEntry. Check internet, URL, and TLS/firewall settings."}
    code = response.status_code
    messages = {
        401: "Workspace ID or connector token was not accepted. Check the saved profile and copy its token again.",
        403: "Connector access is not permitted. Ask the workspace administrator.",
        404: "Connector endpoint was not found. Check the SiftEntry base URL and server deployment.",
        409: "The request is stale or conflicts with current settings. For master discovery, run Sync Tally masters again. Do not repost invoices to resolve this.",
        413: "Connector result is too large. Contact support; do not re-enter vouchers.",
        422: "Connector settings or request format were rejected. Check the Workspace ID and update the connector.",
        429: "SiftEntry is busy. Wait before testing again.",
    }
    if code >= 300:
        message = messages.get(code, "SiftEntry returned a server error. Contact support with the HTTP status and time.")
        if 300 <= code < 400:
            message = "SiftEntry returned a redirect. Use the correct HTTPS base URL; credentials were not forwarded."
        return {"success": False, "message": f"{message} (HTTP {code})", "status_code": code}
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("object required")
    except (ValueError, TypeError):
        return {"success": False, "message": "SiftEntry returned an unexpected response. Check the base URL.", "status_code": code}
    data.setdefault("success", True)
    data["status_code"] = code
    return data


def test_connection(config: ConnectorConfig) -> Dict[str, Any]:
    """Read-only diagnostics. Never claim invoices or touch the local outbox."""
    checks = {key: {"state": "not_checked", "message": "Not checked"}
              for key in ("cloud", "tally", "company", "masters")}
    cloud = cloud_request(config, "/api/v1/connectors/tally/diagnostics",
                          {"workspace_id": config.workspace_id, **connector_metadata()})
    checks["cloud"] = {"state": "passed" if cloud.get("success") else "failed",
                       "message": cloud.get("message", "Cloud authentication passed.")}
    # Independent local check remains useful when cloud authentication is down.
    tally = read_tally_companies(config.tally_url)
    checks["tally"] = {"state": "passed" if tally.get("success") else "failed",
                       "message": tally["message"]}
    company = str(cloud.get("company_name") or "")
    if cloud.get("success") and tally.get("success"):
        found = bool(company) and company in tally.get("companies", [])
        checks["company"] = {"state": "passed" if found else "failed", "message":
            f"Configured company is available: {company}" if found else
            "Configured company was not found. Open the correct company in Tally and verify the profile company name."}
    checks["masters"] = {"state": cloud.get("master_readiness", "not_verified"), "message":
        cloud.get("master_message", "Master names and accounting mappings are not verified.")}
    connected = bool(cloud.get("success"))
    failures = [check["message"] for check in checks.values() if check["state"] == "failed"]
    return {"success": not failures, "connected_to_siftentry": connected,
            "tally_detected": bool(tally.get("success")), "checks": checks,
            "message": " | ".join(failures) if failures else
            "Connection checks passed. Review master readiness separately. No invoices were claimed or posted.",
            "claimed": 0, "submitted": 0, "failed_jobs": 0,
            "updated_at": datetime.now().isoformat(timespec="seconds")}


def sync_masters(config: ConnectorConfig) -> Dict[str, Any]:
    """Explicit discovery only. Never reads the outbox, claims, or posts invoices."""
    begin = cloud_request(config, "/api/v1/connectors/tally/masters/begin",
                          {"workspace_id": config.workspace_id, **connector_metadata()})
    if not begin.get("success"):
        return begin
    if not begin.get("ticket") or not begin.get("company_name"):
        return {"success": False, "message": "Cloud did not provide a company-bound sync session. Update the server and try again."}
    try:
        snapshot = read_snapshot(config.tally_url, str(begin["company_name"]))
    except MasterSyncError as exc:
        return {"success": False, "message": str(exc)}
    return cloud_request(config, "/api/v1/connectors/tally/masters/submit",
                         {"workspace_id": config.workspace_id, "ticket": begin["ticket"], **snapshot})


def read_tally_companies(tally_url: str) -> Dict[str, Any]:
    """Fixed local XML EXPORT; a web server returning 200 is not a Tally pass."""
    xml = ('<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST>'
           '<TYPE>Collection</TYPE><ID>SiftEntryCompanies</ID></HEADER><BODY><DESC>'
           '<STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>'
           '<TDL><TDLMESSAGE><COLLECTION NAME="SiftEntryCompanies" ISINITIALIZE="Yes">'
           '<TYPE>Company</TYPE><NATIVEMETHOD>Name</NATIVEMETHOD>'
           '</COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>')
    try:
        response = requests.post(tally_url, data=xml.encode("utf-8"),
                                 headers={"Content-Type": "application/xml"}, timeout=8,
                                 allow_redirects=False)
        if response.status_code != 200 or len(response.content) > 2_000_000:
            raise ValueError("unexpected response")
        root = ET.fromstring(response.content)
        if (root.tag != "ENVELOPE" or root.find(".//COLLECTION") is None
                or root.findtext(".//STATUS") == "0" or root.find(".//LINEERROR") is not None):
            raise ValueError("not a Tally collection")
        names = [node.get("NAME") or node.findtext(".//NAME") or ""
                 for node in root.findall(".//COMPANY")]
        return {"success": True, "companies": names, "message": "Tally XML export responded."}
    except Exception:
        return {"success": False, "companies": [], "message":
                "Tally XML check failed. Open TallyPrime, load the company, and enable XML access on port 9000."}


def send_cloud_heartbeat(config: ConnectorConfig, tally_detected: Optional[bool] = None) -> Dict[str, Any]:
    """Tell SiftEntry the connector is alive even when no jobs can be claimed."""
    return cloud_request(config, "/api/v1/connectors/tally/heartbeat", {
        "workspace_id": config.workspace_id, **connector_metadata(tally_detected),
    })


def claim_cloud_jobs(config: ConnectorConfig) -> Dict[str, Any]:
    result = cloud_request(config, "/api/v1/connectors/tally/jobs/claim", {
        "workspace_id": config.workspace_id, "limit": config.claim_limit,
        "dry_run": config.dry_run, **connector_metadata(tally_detected=True),
    })
    result.setdefault("jobs", [])
    return result


def submit_cloud_results(config: ConnectorConfig, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return cloud_request(config, "/api/v1/connectors/tally/jobs/results", {
        "workspace_id": config.workspace_id, "results": results,
    })


@contextmanager
def _poll_file_lock(path: Path):
    """Serialize processes as well as threads; a second instance never drains our outbox."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def poll_once(config: ConnectorConfig) -> Dict[str, Any]:
    try:
        with _poll_file_lock(default_outbox_path(config.config_path)):
            return _poll_once_locked(config)
    except (OSError, OutboxUnreadable) as exc:
        return {
            "success": False, "connected_to_siftentry": False, "tally_detected": False,
            "claimed": 0, "submitted": 0, "failed_jobs": 0, "awaiting_ack": -1,
            "message": ("Connector paused: another instance is polling, or local recovery storage "
                        f"cannot be used. Do not re-enter vouchers. Contact support: {exc}"),
        }


def _poll_once_locked(config: ConnectorConfig) -> Dict[str, Any]:
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

    # Acknowledge what already happened in Tally before anything else. This
    # must not depend on Tally being open now, or on the network having been
    # up at the moment the voucher was created.
    outbox_path = default_outbox_path(config.config_path)
    try:
        drained = drain_outbox(config, outbox_path)
    except OutboxUnreadable as exc:
        return {
            "success": False,
            "connected_to_siftentry": False,
            "tally_detected": False,
            "message": (
                "The local results file is unreadable — not claiming new work until it is "
                f"recovered. Contact SiftEntry support with this file: {exc}"
            ),
            "claimed": 0,
            "submitted": 0,
            "failed_jobs": 0,
            "awaiting_ack": -1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    if not drained.get("success"):
        heartbeat = send_cloud_heartbeat(config, tally_detected=None)
        return {
            "success": False,
            "connected_to_siftentry": bool(heartbeat.get("success")),
            "tally_detected": False,
            "message": (
                drained["message"] if drained.get("uncertain") else
                f"{drained.get('pending', 0)} posting result(s) await cloud acknowledgement. "
                "Retrying acknowledgement only. Do not re-enter vouchers."
            ),
            "claimed": 0,
            "submitted": 0,
            "failed_jobs": 0,
            "awaiting_ack": int(drained.get("pending", 0) or 0),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
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

    # Verify durable storage before asking the server to reserve new invoices.
    write_outbox(outbox_path, [])
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
        result["connector_workspace_id"] = config.workspace_id
        result["connector_cloud_url"] = config.cloud_url.rstrip("/")
        # Persist THIS result before touching the next job. An interruption
        # during job N must not lose the outcome of job N-1.
        append_outbox(outbox_path, [result])
        results.append(result)
        last_invoice = str(job.get("invoice_number") or job.get("invoice_id") or last_invoice)
        if result.get("outcome_uncertain"):
            # The server keeps this and any unattempted batch claims reserved.
            # A human must reconcile; an inconclusive outcome never authorizes retry.
            drained = drain_outbox(config, outbox_path)
            return {"success": False, "connected_to_siftentry": True, "tally_detected": True,
                    "claimed": len(jobs), "submitted": 0, "failed_jobs": 0,
                    "awaiting_ack": drained.get("pending", 1), "message":
                    "Outcome uncertain. Posting is paused. Contact support to reconcile the batch; do not re-enter vouchers."}

    submitted: Dict[str, Any] = {"success": True, "accepted": 0}
    awaiting_ack = 0
    if results:
        # Every result is already on disk. If the acknowledgement fails, the
        # next poll retries it before doing anything else.
        submitted = submit_cloud_results(config, results)
        if (submitted.get("success") and submitted.get("accepted") == len(results)
                and not submitted.get("rejected")):
            write_outbox(outbox_path, [])
        else:
            submitted["success"] = False
            awaiting_ack = len(results)

    failed_jobs = len([result for result in results if not result.get("success")])
    success = bool(claimed.get("success")) and bool(submitted.get("success"))
    message = "Idle. No approved Tally jobs."
    if not claimed.get("success"):
        message = str(claimed.get("message") or "Could not reach SiftEntry.")
    elif awaiting_ack:
        message = (
            f"Posted {awaiting_ack} voucher(s) to Tally; SiftEntry has not confirmed yet — "
            "retrying automatically. Do not re-enter these vouchers."
        )
    elif results:
        message = str(submitted.get("message") or f"Submitted {submitted.get('accepted', len(results))} result(s).")
    return {
        "success": success,
        "connected_to_siftentry": bool(claimed.get("success")),
        "tally_detected": True,
        "message": message,
        "claimed": len(jobs),
        "submitted": 0 if awaiting_ack else int(submitted.get("accepted", len(results)) or 0),
        "awaiting_ack": awaiting_ack,
        "failed_jobs": failed_jobs,
        "last_posted_invoice": last_invoice,
        "claim": claimed,
        "submit": submitted,
        "results": results,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
