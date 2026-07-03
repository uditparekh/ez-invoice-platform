"""Batch parse invoice PDFs and prepare Tally XML exports.

Default behavior is intentionally non-destructive: it writes XML/summary files
for review. Pass --post-to-tally only when you are ready to create vouchers in
the configured Tally company.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from accounting_routing import apply_accounting_route
from gst_invoice_parser import looks_like_gst_invoice, parse_gst_invoice
from tally_integration import (
    TALLY_SETUP_PROFILES,
    _load_settings,
    _parse_tally_response,
    _profile_defaults,
    _test_connection,
    build_tally_xml,
)
from tally_connector_client import send_xml_batch_to_connector
from universal_parser import parse_generic_invoice

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


APP_DIR = Path(__file__).resolve().parent
DEFAULT_EXPORT_ROOT = APP_DIR / "tally_exports"


def _extract_text(pdf_bytes: bytes) -> Tuple[str, str, int]:
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return "\n".join(page.get_text("text") or "" for page in doc), "pymupdf", doc.page_count
    except Exception:
        pass

    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages), "pypdf", len(reader.pages)
    except Exception:
        return "", "none", 0


def _safe_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("_")
    return clean or "invoice"


def _capture_issues(payload: Dict[str, Any]) -> List[str]:
    inv = payload.get("INVOICE", {})
    header = inv.get("INVOICE HEADER", {})
    rows = inv.get("LINE ITEMS", {}).get("ROWS", []) or []
    issues: List[str] = []
    for field in ("INVOICE NO.", "INVOICE DATE", "DUE DATE"):
        if not str(header.get(field, "")).strip():
            issues.append("Missing " + field)
    if not rows:
        issues.append("No line items captured")
    for idx, row in enumerate(rows, start=1):
        missing = [
            field
            for field in ("DESCRIPTION", "QUANTITY", "UOM", "UNIT PRICE", "AMOUNT")
            if row.get(field) in (None, "")
        ]
        if missing:
            issues.append("Line " + str(idx) + " missing " + ", ".join(missing))
    return issues


def _parse_pdf(path: Path, homes: Optional[List[str]] = None) -> Dict[str, Any]:
    pdf_bytes = path.read_bytes()
    text, engine, pages = _extract_text(pdf_bytes)
    extracted_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if looks_like_gst_invoice(text):
        payload = parse_gst_invoice(path.name, pdf_bytes, text=text, engine=engine, pages=pages, extracted_at=extracted_at)
        if payload:
            apply_accounting_route(payload, homes=homes)
            return payload
    payload = parse_generic_invoice(path.name, text, engine, pages, extracted_at)
    apply_accounting_route(payload, homes=homes)
    return payload


def _summary_row(path: Path, payload: Dict[str, Any], xml_path: Path, issues: List[str]) -> Dict[str, Any]:
    inv = payload["INVOICE"]
    header = inv["INVOICE HEADER"]
    rows = inv.get("LINE ITEMS", {}).get("ROWS", []) or []
    payment = inv.get("PAYMENT", {}).get("ELECTRONIC", {})
    diag = inv.get("PARSER_DIAGNOSTICS", {})
    return {
        "file": path.name,
        "parser": inv.get("DOCUMENT", {}).get("PARSER", ""),
        "direction": inv.get("ROUTING", {}).get("DIRECTION", "unknown"),
        "transaction_type": inv.get("ROUTING", {}).get("TRANSACTION TYPE", "review"),
        "invoice_no": header.get("INVOICE NO.", ""),
        "invoice_date": header.get("INVOICE DATE", ""),
        "seller": inv.get("SELLER", {}).get("NAME", ""),
        "bill_to": inv.get("BILL TO", {}).get("NAME", ""),
        "currency": payment.get("CURRENCY", ""),
        "amount": payment.get("AMOUNT", 0),
        "taxable_total": diag.get("taxable_total", ""),
        "tax_total": diag.get("tax_total", ""),
        "line_count": len(rows),
        "issues": "; ".join(issues),
        "xml_path": str(xml_path),
    }


def _post_xml(url: str, xml: str) -> Dict[str, Any]:
    if not requests:
        return {"success": False, "message": "requests is not installed", "response": None}
    try:
        response = requests.post(url, data=xml.encode("utf-8"), headers={"Content-Type": "application/xml"}, timeout=20)
    except Exception as exc:
        return {"success": False, "message": str(exc), "response": None}
    parsed = _parse_tally_response(response.text)
    ok = response.status_code == 200 and parsed.get("errors") == 0 and (
        parsed.get("created") or parsed.get("altered")
    )
    return {
        "success": bool(ok),
        "message": parsed.get("line_error") or ("created/altered" if ok else response.text[:240]),
        "response": parsed,
        "status_code": response.status_code,
    }


def run(args: argparse.Namespace) -> int:
    settings = _load_settings()
    if args.setup_profile:
        settings.update(_profile_defaults(args.setup_profile))
        settings["setup_profile"] = args.setup_profile
    for key in (
        "setup_profile",
        "url",
        "company",
        "posting_mode",
        "voucher_type",
        "purchase_ledger",
        "tax_ledger",
        "stock_item_name",
        "stock_item_hsn",
        "stock_item_uom",
        "godown_name",
        "tcs_ledger",
        "round_off_ledger",
    ):
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = value

    out_dir = Path(args.output_dir) if args.output_dir else DEFAULT_EXPORT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: List[Dict[str, Any]] = []
    payloads: Dict[str, Any] = {}
    post_results: Dict[str, Any] = {}
    xml_files: List[Path] = []

    connector_settings = {
        "enabled": bool(args.post_via_connector),
        "url": args.connector_url,
        "token": args.connector_token or "",
        "workspace_id": args.workspace_id,
    }

    if (args.test_connection or args.post_to_tally) and not args.post_via_connector:
        probe = _test_connection(settings.get("url", ""))
        print("Tally connection:", probe.get("message", probe))
        if args.post_to_tally and not probe.get("success"):
            print("Stopped before posting because Tally did not respond.")
            return 2

    for raw_path in args.pdfs:
        path = Path(raw_path).expanduser()
        if not path.exists():
            print("Missing file:", path)
            continue

        payload = _parse_pdf(path, homes=args.home_company)
        issues = _capture_issues(payload)
        route = payload.get("INVOICE", {}).get("ROUTING", {})
        detected_direction = route.get("DIRECTION", "unknown")
        if args.direction != "auto" and detected_direction in ("unknown", "", None):
            route["DIRECTION"] = args.direction
            route["TRANSACTION TYPE"] = "purchase" if args.direction == "inbound" else "sales"
            route["PARTY ROLE"] = "vendor" if args.direction == "inbound" else "customer"
            route["TALLY VOUCHER TYPE"] = "Purchase" if args.direction == "inbound" else "Sales"
            route["CONFIDENCE"] = "manual"
            payload.setdefault("INVOICE", {}).setdefault("DOCUMENT", {})["DIRECTION"] = args.direction
        elif args.direction != "auto" and detected_direction != args.direction:
            issues.append(
                "Direction mismatch: expected "
                + args.direction
                + ", detected "
                + str(detected_direction)
            )
        xml = build_tally_xml(payload, settings=settings, classifier=None)
        xml_path = out_dir / (_safe_name(path.name) + "_tally.xml")
        xml_path.write_text(xml, encoding="utf-8")
        xml_files.append(xml_path)
        payloads[path.name] = payload
        summary.append(_summary_row(path, payload, xml_path, issues))

        if args.post_to_tally and args.post_via_connector and not issues:
            invoice_id = payload.get("INVOICE", {}).get("INVOICE HEADER", {}).get("INVOICE NO.", path.stem)
            post_results[path.name] = send_xml_batch_to_connector(
                [{"invoice_id": str(invoice_id or path.stem), "xml": xml}],
                settings=connector_settings,
                dry_run=bool(args.connector_dry_run),
            )
        elif args.post_to_tally and not issues:
            post_results[path.name] = _post_xml(settings["url"], xml)
        elif args.post_to_tally:
            post_results[path.name] = {"success": False, "message": "Skipped due to capture issues", "response": None}

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()) if summary else ["file"])
        writer.writeheader()
        writer.writerows(summary)

    summary_json = out_dir / "summary.json"
    summary_json.write_text(json.dumps({"settings": settings, "invoices": summary, "post_results": post_results}, indent=2), encoding="utf-8")

    zip_path = out_dir / "tally_xml_batch.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for xml_file in xml_files:
            zf.write(xml_file, arcname=xml_file.name)
        zf.write(summary_csv, arcname=summary_csv.name)
        zf.write(summary_json, arcname=summary_json.name)

    print("\nProcessed", len(summary), "invoice(s)")
    print("Output:", out_dir)
    print("ZIP:", zip_path)
    for row in summary:
        status = "OK" if not row["issues"] else "REVIEW"
        print(
            f"{status:6s} {row['direction']:8s} {row['invoice_no']:16s} {row['amount']:>12} "
            f"{row['currency']:3s} lines={row['line_count']:<3} seller={row['seller']}"
        )
        if row["issues"]:
            print("       issues:", row["issues"])
        if args.post_to_tally:
            print("       tally:", post_results.get(row["file"], {}).get("message", "not posted"))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Tally XML from invoice PDFs.")
    parser.add_argument("pdfs", nargs="+", help="Invoice PDF paths")
    parser.add_argument("--output-dir", help="Folder where XML, summary, and ZIP files are written")
    parser.add_argument("--test-connection", action="store_true", help="Probe the Tally HTTP endpoint before exporting")
    parser.add_argument("--post-to-tally", action="store_true", help="Create vouchers in Tally after parsing")
    parser.add_argument("--post-via-connector", action="store_true", help="Send vouchers through the local SiftEntry Tally Connector")
    parser.add_argument("--connector-dry-run", action="store_true", help="Validate vouchers with the connector without posting into Tally")
    parser.add_argument("--connector-url", default="http://127.0.0.1:8765", help="Local connector URL")
    parser.add_argument("--connector-token", default="", help="Local connector bearer token")
    parser.add_argument("--workspace-id", default="local-workspace", help="SiftEntry client workspace id")
    parser.add_argument("--direction", choices=["auto", "inbound", "outbound"], default="auto", help="Require a detected invoice direction before posting")
    parser.add_argument("--home-company", action="append", help="Client legal name used to infer inbound/outbound direction. Repeat for aliases.")
    parser.add_argument("--url", help="Tally URL, for example http://localhost:9000")
    parser.add_argument(
        "--setup-profile",
        choices=sorted(TALLY_SETUP_PROFILES.keys()),
        help="Saved client Tally profile to apply before command-line overrides",
    )
    parser.add_argument("--company", help="Tally company name")
    parser.add_argument("--posting-mode", choices=["Item Invoice", "Accounting Voucher"], help="Tally posting mode")
    parser.add_argument("--voucher-type", help="Tally voucher type, default comes from saved settings or Purchase")
    parser.add_argument("--purchase-ledger", help="Purchase/expense ledger, default comes from saved settings")
    parser.add_argument("--tax-ledger", help="Optional tax ledger; omitted tax rolls into purchase ledger")
    parser.add_argument("--stock-item-name", help="Optional Tally stock item override for item invoice mode")
    parser.add_argument("--stock-item-hsn", help="HSN that should map to the stock item override")
    parser.add_argument("--stock-item-uom", help="Exact Tally unit symbol for the stock item, for example KGS")
    parser.add_argument("--godown-name", help="Optional exact Tally godown/location master name")
    parser.add_argument("--tcs-ledger", help="Exact Tally TCS ledger name")
    parser.add_argument("--round-off-ledger", help="Exact Tally round-off ledger name")
    return parser


if __name__ == "__main__":
    sys.exit(run(build_arg_parser().parse_args()))
