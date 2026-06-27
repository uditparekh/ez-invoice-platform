"""Local EZ-Invoice Tally Connector.

Run this on the client machine that can reach TallyPrime. The connector exposes
a small token-protected local API for approved voucher jobs.
"""

from __future__ import annotations

import argparse
import hmac
import os
import socket
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
            if not xml.strip():
                results.append({"invoice_id": invoice_id, "success": False, "message": "Missing XML"})
                continue
            try:
                ET.fromstring(xml)
            except ET.ParseError as exc:
                results.append({"invoice_id": invoice_id, "success": False, "message": "Invalid XML: " + str(exc)})
                continue
            if dry_run:
                results.append({"invoice_id": invoice_id, "success": True, "message": "Dry run accepted"})
                continue
            if not requests:
                results.append({"invoice_id": invoice_id, "success": False, "message": "requests is not installed"})
                continue
            try:
                response = requests.post(
                    tally_url,
                    data=xml.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                    timeout=20,
                )
            except Exception as exc:
                results.append({"invoice_id": invoice_id, "success": False, "message": "Tally post failed: " + str(exc)})
                continue
            parsed = _parse_tally_response(response.text)
            ok = response.status_code == 200 and parsed.get("errors") == 0 and (
                parsed.get("created") or parsed.get("altered")
            )
            results.append(
                {
                    "invoice_id": invoice_id,
                    "success": bool(ok),
                    "message": "Posted to Tally" if ok else (parsed.get("line_error") or response.text[:300]),
                    "status_code": response.status_code,
                    "response": parsed,
                }
            )

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
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
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
