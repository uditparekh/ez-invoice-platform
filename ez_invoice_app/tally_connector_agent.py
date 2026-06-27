"""Local EZ-Invoice Tally Connector.

Run this on the client machine that can reach TallyPrime. The connector exposes
a small token-protected local API for approved voucher jobs.
"""

from __future__ import annotations

import argparse
import hmac
import os
import socket
import time
from datetime import datetime
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

from flask import Flask, jsonify, request

from tally_integration import _parse_tally_response, _test_connection

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


APP_VERSION = "0.1.0"


def auth_headers(token: str, content_type: str = "application/json") -> Dict[str, str]:
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-SiftEntry-Connector-Token"] = token
    return headers


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
    parsed = _parse_tally_response(response.text)
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


def cloud_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def claim_cloud_jobs(
    base_url: str,
    workspace_id: str,
    token: str,
    limit: int,
    dry_run: bool,
) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed", "jobs": []}
    try:
        response = requests.post(
            cloud_url(base_url, "/api/v1/connectors/tally/jobs/claim"),
            json={"workspace_id": workspace_id, "limit": limit, "dry_run": dry_run},
            headers=auth_headers(token),
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


def submit_cloud_results(
    base_url: str,
    workspace_id: str,
    token: str,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed"}
    try:
        response = requests.post(
            cloud_url(base_url, "/api/v1/connectors/tally/jobs/results"),
            json={"workspace_id": workspace_id, "results": results},
            headers=auth_headers(token),
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


def run_cloud_polling(args: argparse.Namespace) -> None:
    if not args.token:
        raise SystemExit("Set --token or EZ_TALLY_CONNECTOR_TOKEN before starting cloud polling.")
    print(
        "SiftEntry Tally Connector polling",
        args.cloud_url,
        "workspace",
        args.workspace_id,
    )
    print("Posting to TallyPrime at", args.tally_url)
    while True:
        claimed = claim_cloud_jobs(
            args.cloud_url,
            args.workspace_id,
            args.token,
            limit=args.claim_limit,
            dry_run=args.cloud_dry_run,
        )
        jobs = claimed.get("jobs") or []
        if not claimed.get("success"):
            print(datetime.now().isoformat(timespec="seconds"), "claim failed:", claimed.get("message", claimed))
        elif jobs:
            print(datetime.now().isoformat(timespec="seconds"), "claimed", len(jobs), "job(s)")
        results: List[Dict[str, Any]] = []
        for job in jobs:
            tally_url = str(job.get("tally_url") or args.tally_url)
            result = post_xml_to_tally(
                tally_url,
                invoice_id=str(job.get("invoice_id") or ""),
                xml=str(job.get("xml") or ""),
                dry_run=bool(job.get("dry_run")),
            )
            result["posting_id"] = str(job.get("posting_id") or "")
            results.append(result)
            print(" ", job.get("invoice_number") or job.get("invoice_id"), "-", result.get("message"))
        if results:
            submitted = submit_cloud_results(
                args.cloud_url,
                args.workspace_id,
                args.token,
                results,
            )
            if not submitted.get("success"):
                print(datetime.now().isoformat(timespec="seconds"), "result submit failed:", submitted.get("message", submitted))
            else:
                print(datetime.now().isoformat(timespec="seconds"), "submitted", submitted.get("accepted", len(results)), "result(s)")
        if args.run_once:
            break
        time.sleep(args.poll_interval)


def create_app(config: Dict[str, Any]) -> Flask:
    app = Flask(__name__)
    token = str(config.get("token") or "")
    tally_url = str(config.get("tally_url") or "http://localhost:9000")
    workspace_id = str(config.get("workspace_id") or "local")

    def authorized() -> bool:
        if not token:
            return True
        auth = request.headers.get("Authorization", "")
        header_token = request.headers.get("X-EZ-Connector-Token", "")
        supplied = header_token
        if auth.lower().startswith("bearer "):
            supplied = auth.split(" ", 1)[1].strip()
        return hmac.compare_digest(supplied, token)

    def require_auth():
        if authorized():
            return None
        return jsonify({"success": False, "message": "Unauthorized connector request"}), 401

    @app.get("/health")
    def health():
        return jsonify(
            {
                "success": True,
                "connector": "EZ-Invoice Tally Connector",
                "version": APP_VERSION,
                "workspace_id": workspace_id,
                "host": socket.gethostname(),
                "tally_url": tally_url,
                "auth_required": bool(token),
                "time": datetime.now().isoformat(timespec="seconds"),
            }
        )

    @app.post("/connector/test-tally")
    def test_tally():
        auth_error = require_auth()
        if auth_error:
            return auth_error
        return jsonify(_test_connection(tally_url))

    @app.post("/connector/vouchers")
    def vouchers():
        auth_error = require_auth()
        if auth_error:
            return auth_error
        body = request.get_json(silent=True) or {}
        vouchers = body.get("vouchers") or []
        dry_run = bool(body.get("dry_run", False))
        if not isinstance(vouchers, list) or not vouchers:
            return jsonify({"success": False, "message": "No vouchers supplied", "results": []}), 400

        results: List[Dict[str, Any]] = []
        for item in vouchers:
            invoice_id = str(item.get("invoice_id") or item.get("name") or "invoice")
            xml = str(item.get("xml") or "")
            results.append(post_xml_to_tally(tally_url, invoice_id, xml, dry_run=dry_run))

        success = all(result.get("success") for result in results)
        return jsonify(
            {
                "success": success,
                "message": "All vouchers accepted" if success else "One or more vouchers failed",
                "dry_run": dry_run,
                "workspace_id": workspace_id,
                "results": results,
            }
        ), 200 if success else 207

    return app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local EZ-Invoice Tally Connector.")
    parser.add_argument("--host", default=os.environ.get("EZ_TALLY_CONNECTOR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("EZ_TALLY_CONNECTOR_PORT", "8765")))
    parser.add_argument("--tally-url", default=os.environ.get("TALLY_URL", "http://localhost:9000"))
    parser.add_argument("--workspace-id", default=os.environ.get("EZ_WORKSPACE_ID", "local-workspace"))
    parser.add_argument("--token", default=os.environ.get("EZ_TALLY_CONNECTOR_TOKEN", ""))
    parser.add_argument("--cloud-url", default=os.environ.get("SIFTENTRY_CLOUD_URL", ""))
    parser.add_argument("--poll-cloud", action="store_true", help="Poll SiftEntry cloud for approved Tally jobs instead of serving a local API.")
    parser.add_argument("--poll-interval", type=int, default=int(os.environ.get("EZ_TALLY_POLL_INTERVAL", "15")))
    parser.add_argument("--claim-limit", type=int, default=int(os.environ.get("EZ_TALLY_CLAIM_LIMIT", "5")))
    parser.add_argument("--cloud-dry-run", action="store_true", help="Claim jobs as dry runs so no vouchers are posted.")
    parser.add_argument("--run-once", action="store_true", help="Poll once and exit. Useful for smoke tests.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.poll_cloud or args.cloud_url:
        if not args.cloud_url:
            raise SystemExit("Set --cloud-url or SIFTENTRY_CLOUD_URL for cloud polling mode.")
        run_cloud_polling(args)
        return
    if not args.token:
        print("WARNING: Connector is running without a token. Set EZ_TALLY_CONNECTOR_TOKEN for real use.")
    app = create_app(
        {
            "token": args.token,
            "tally_url": args.tally_url,
            "workspace_id": args.workspace_id,
        }
    )
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
