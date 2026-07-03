"""Local SiftEntry Tally Connector.

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

from flask import Flask, jsonify, request

try:
    from .tally_connector_runtime import (
        APP_VERSION,
        ConnectorConfig,
        poll_once,
        post_xml_to_tally,
        test_tally_connection,
        write_status,
    )
except ImportError:
    from tally_connector_runtime import (
        APP_VERSION,
        ConnectorConfig,
        poll_once,
        post_xml_to_tally,
        test_tally_connection,
        write_status,
    )


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
    config = ConnectorConfig(
        cloud_url=args.cloud_url,
        workspace_id=args.workspace_id,
        token=args.token,
        tally_url=args.tally_url,
        poll_interval=args.poll_interval,
        claim_limit=args.claim_limit,
        dry_run=args.cloud_dry_run,
    )
    while True:
        status = poll_once(config)
        write_status(status)
        if not status.get("success"):
            print(datetime.now().isoformat(timespec="seconds"), "poll failed:", status.get("message", status))
        elif status.get("claimed"):
            print(
                datetime.now().isoformat(timespec="seconds"),
                "posted",
                status.get("submitted", 0),
                "of",
                status.get("claimed", 0),
                "job(s)",
            )
        else:
            print(datetime.now().isoformat(timespec="seconds"), status.get("message", "Idle"))
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
                "connector": "SiftEntry Tally Connector",
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
        return jsonify(test_tally_connection(tally_url))

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
    parser = argparse.ArgumentParser(description="Run the local SiftEntry Tally Connector.")
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
