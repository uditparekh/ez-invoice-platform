"""SiftEntry pilot end-to-end QA — drives the full 2-client lifecycle.

Run from the repository root before any pilot launch or after significant
changes (deliberately NOT named test_* so pytest does not collect it):

    python tests/pilot_e2e_qa.py

Covers: bootstrap, auth/session rotation, two organizations, org settings,
Tally + QuickBooks client profiles, PDF upload/parse/evidence, the reviewer
correct -> validate -> approve workflow, send-back, dry-run posting, batch
posting through the background worker, the cloud Tally connector
claim/results loop, document retrieval, inbound email intake, invitations,
password reset, cross-org isolation, learning export/import, storage
cleanup, and AI-off verification. Runs on a throwaway SQLite database in a
temp directory; nothing external is touched.
"""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
WORKSPACE = Path(tempfile.mkdtemp(prefix="siftentry-qa-"))

os.environ.update({
    "EZ_API_ENVIRONMENT": "pilot",
    "EZ_API_ALLOW_DEV_BOOTSTRAP": "true",
    "EZ_API_DATABASE_URL": f"sqlite:///{WORKSPACE / 'qa.db'}",
    "EZ_API_UPLOAD_DIRECTORY": str(WORKSPACE / "uploads"),
    "EZ_EMAIL_PROVIDER": "log",
    "SIFTENTRY_INBOUND_EMAIL_SECRET": "qa-inbound-secret-24chars!!",
    "SIFTENTRY_AI_PROVIDER": "profile_context",
})

from fastapi.testclient import TestClient

from siftentry_app.backend import worker as worker_mod
from siftentry_app.backend.main import create_app
from siftentry_app.backend.settings import ApiSettings

APP = create_app(ApiSettings.from_environment())
RESULTS = []


GST_PDF = None
US_PDF = None


def _make_pdf(path, lines):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for text, size in lines:
        page.insert_text((50, y), text, fontsize=size)
        y += size + 10
    doc.save(str(path))
    doc.close()


def make_sample_pdfs():
    global GST_PDF, US_PDF
    GST_PDF = WORKSPACE / "gst_invoice.pdf"
    US_PDF = WORKSPACE / "us_invoice.pdf"
    _make_pdf(GST_PDF, [
        ("TAX INVOICE", 16), ("Crescent Bearing Corporation", 12),
        ("GSTIN/UIN: 27AABCC1234D1Z5", 10),
        ("12 Industrial Estate, Mumbai, Maharashtra 400001", 9),
        ("Invoice No.: CBC-2026-0142", 11), ("Invoice Date: 05-Jul-2026", 10),
        ("Bill To: Neel Trading Co", 10), ("GSTIN/UIN: 27AADCN9876E1Z2", 9),
        ("Description        HSN/SAC   Qty   Rate      Amount", 9),
        ("Ball Bearing 6204  84821011  50    450.00    22500.00", 9),
        ("Roller Bearing     84821012  25    1261.00   31525.00", 9),
        ("Taxable Value: 54025.00", 10), ("CGST @ 9%: 4862.25", 9),
        ("SGST @ 9%: 4862.25", 9), ("Round Off: 0.50", 9),
        ("Invoice Amount: 63750.00", 11),
    ])
    _make_pdf(US_PDF, [
        ("INVOICE", 16), ("Gulf Coast Fuel Supply LLC", 12),
        ("800 Port Blvd, Miami FL 33132", 9),
        ("INVOICE NO.: GCF-88121", 11), ("INVOICE DATE: 07/01/2026", 10),
        ("DUE DATE: 07/31/2026", 10), ("BILL TO: Craft Charter LLC", 10),
        ("DESCRIPTION           QTY     UNIT PRICE    AMOUNT", 9),
        ("Jet A Fuel (gal)      1200    4.85          5820.00", 9),
        ("Into-plane fee        1       250.00        250.00", 9),
        ("INVOICE AMOUNT: 6070.00", 11), ("CURRENCY: USD", 9),
    ])



def warn(name, ok, detail=""):
    mark = "OK  " if ok else "WARN"
    print(f"[{mark}] (parser quality) {name}" + (f" — {detail}" if detail and not ok else ""))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))


def main():
    c = CLIENT

    # ---------- 1. Health ----------
    r = c.get("/health")
    check("health endpoint", r.status_code == 200)
    r = c.get("/health/deployment")
    check("deployment health endpoint", r.status_code == 200, str(r.status_code))

    # ---------- 2. Owner bootstrap (you) ----------
    r = c.post("/api/v1/auth/bootstrap", json={
        "email": "udit@siftentry.test", "password": "pilot-password-123",
        "full_name": "Udit Parekh", "organization_name": "Neel Trading Co",
        "legal_names": ["Neel Trading Co", "Neel Trading Company"],
        "default_currency": "INR",
    })
    check("bootstrap owner + first org", r.status_code == 201, r.text[:200])
    tokens = r.json()
    org_a = tokens["user"]["memberships"][0]["organization_id"]
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = c.post("/api/v1/auth/login", json={"email": "udit@siftentry.test", "password": "wrong-password!"})
    check("wrong password rejected", r.status_code == 401, str(r.status_code))

    r = c.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    check("refresh token rotation", r.status_code == 200, r.text[:200])
    rotated = r.json()
    r = c.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    check("old refresh token revoked after rotation", r.status_code == 401, str(r.status_code))
    hdr = {"Authorization": f"Bearer {rotated['access_token']}"}
    refresh_token = rotated["refresh_token"]

    r = c.get("/api/v1/auth/me", headers=hdr)
    check("auth/me", r.status_code == 200 and r.json()["email"] == "udit@siftentry.test")

    # ---------- 3. Second pilot client org ----------
    r = c.post("/api/v1/organizations", headers=hdr, json={
        "name": "Craft Charter LLC", "legal_names": ["Craft Charter LLC"],
        "default_currency": "USD",
    })
    check("create second pilot org", r.status_code in (200, 201), r.text[:200])
    org_b = r.json()["id"]

    # ---------- 4. Org settings ----------
    r = c.put(f"/api/v1/organizations/{org_a}/settings", headers=hdr, json={
        "default_currency": "INR", "default_country": "IN",
        "primary_accounting_system": "tally", "data_retention": "review_window",
        "notifications": {"approvals": True, "failures": True, "digest": False},
        "metadata": {},
    })
    check("save org settings (client A)", r.status_code == 200, r.text[:200])

    # ---------- 5. Client profiles (the per-client 'plugin values') ----------
    profile_a = {
        "name": "Neel — GST Purchase Invoices",
        "accounting_system": "tally",
        "description": "Standard India GST tax invoices posted as Purchase Vouchers.",
        "is_default": True,
        "settings": {
            "company_name": "Neel Trading Co",
            "country_code": "IN", "default_currency": "INR",
            "invoice_format": "gst_einvoice", "tax_mode": "cgst_sgst",
            "direction": "inbound", "posting_mode": "accounting_voucher",
            "purchase_ledger": "Purchase Accounts",
            "tax_ledger": "Input CGST,Input SGST",
            "round_off_ledger": "Rounding Off",
            "connection_settings": {
                "connector_enabled": True,
                "workspace_id": "neel-ws-1",
                "connector_token": "qa-connector-token-neel-0001",
            },
            "training_profile": {
                "onboarding_status": "collecting_samples",
                "business_process": "AP clerk uploads supplier tax invoices weekly.",
                "expected_fields": ["invoice_number", "invoice_date", "supplier_name",
                                     "supplier_tax_id", "subtotal", "tax_total", "total"],
                "extraction_instructions": "GSTIN appears under supplier name. Tax split CGST+SGST at 9% each.",
                "validation_rules": ["subtotal + tax_total must equal total within 1.00"],
                "posting_expectations": "Purchase voucher, credit supplier, debit Purchase Accounts + input GST.",
            },
        },
    }
    r = c.post(f"/api/v1/organizations/{org_a}/client-profiles", headers=hdr, json=profile_a)
    check("create Tally client profile (A)", r.status_code in (200, 201), r.text[:300])
    profile_a_id = r.json()["id"]

    profile_b = {
        "name": "Craft — US Fuel Invoices",
        "accounting_system": "quickbooks",
        "description": "US supplier fuel invoices posted as QuickBooks Bills.",
        "is_default": True,
        "settings": {
            "country_code": "US", "default_currency": "USD",
            "invoice_format": "generic", "tax_mode": "none",
            "direction": "inbound",
        },
    }
    r = c.post(f"/api/v1/organizations/{org_b}/client-profiles", headers=hdr, json=profile_b)
    check("create QuickBooks client profile (B)", r.status_code in (200, 201), r.text[:300])
    profile_b_id = r.json()["id"]

    # ---------- 6. Upload + parse (both formats) ----------
    with open(GST_PDF, "rb") as f:
        r = c.post("/api/v1/invoices/upload", headers=hdr,
                   params={"organization_id": org_a, "client_profile_id": profile_a_id},
                   files={"file": ("gst_invoice.pdf", f, "application/pdf")})
    check("upload GST invoice (A)", r.status_code in (200, 201), r.text[:300])
    inv_a = r.json()
    warn("GST parser selected", "GST" in (inv_a.get("parser") or "") or inv_a.get("parser") == "GST/E-Invoice adapter", inv_a.get("parser", ""))
    warn("GST invoice number extracted", inv_a.get("invoice_number") == "CBC-2026-0142", inv_a.get("invoice_number", ""))
    warn("GST total extracted", abs(float(inv_a.get("total") or 0) - 63750.0) < 1.0, str(inv_a.get("total")))
    warn("GSTIN extracted", "27AABCC1234D1Z5" in (inv_a.get("supplier", {}).get("tax_id") or ""), inv_a.get("supplier", {}).get("tax_id", ""))
    check("parse evidence bboxes present", len(inv_a.get("evidence") or []) > 0, str(len(inv_a.get("evidence") or [])))

    with open(US_PDF, "rb") as f:
        r = c.post("/api/v1/invoices/upload", headers=hdr,
                   params={"organization_id": org_b, "client_profile_id": profile_b_id},
                   files={"file": ("us_invoice.pdf", f, "application/pdf")})
    check("upload US invoice (B)", r.status_code in (200, 201), r.text[:300])
    inv_b = r.json()
    warn("US invoice number extracted", inv_b.get("invoice_number") == "GCF-88121", inv_b.get("invoice_number", ""))
    check("US total extracted", abs(float(inv_b.get("total") or 0) - 6070.0) < 1.0, str(inv_b.get("total")))

    # Non-PDF rejected
    r = c.post("/api/v1/invoices/upload", headers=hdr, params={"organization_id": org_a},
               files={"file": ("notes.txt", b"hello", "text/plain")})
    check("non-PDF upload rejected", r.status_code == 415, str(r.status_code))

    # ---------- 7. Review -> correct (reviewer workflow) -> validate -> approve ----------
    r = c.get(f"/api/v1/invoices/{inv_a['id']}/review", headers=hdr)
    check("review payload (A)", r.status_code == 200, r.text[:200])

    # Reviewer corrections: exactly what the review screen does when the
    # deterministic parser misreads an unfamiliar layout.
    fix_a = {
        "invoice_number": "CBC-2026-0142", "invoice_date": "2026-07-05",
        "due_date": "2026-08-04",
        "subtotal": 54025.0, "tax_total": 9724.5, "total": 63750.0,
        "supplier": {"name": "Crescent Bearing Corporation",
                      "tax_id": "27AABCC1234D1Z5",
                      "address": ["12 Industrial Estate, Mumbai"],
                      "email": "", "phone": ""},
        "lines": [
            {"line_number": 1, "description": "Ball Bearing 6204", "quantity": 50,
             "uom": "NOS", "unit_price": 450.0, "net_amount": 22500.0,
             "tax_amount": 4050.0, "total_amount": 26550.0, "hsn_sac": "84821011",
             "category": "", "gl_code": ""},
            {"line_number": 2, "description": "Roller Bearing", "quantity": 25,
             "uom": "NOS", "unit_price": 1261.0, "net_amount": 31525.0,
             "tax_amount": 5674.5, "total_amount": 37200.0, "hsn_sac": "84821012",
             "category": "", "gl_code": ""},
        ],
    }
    r = c.patch(f"/api/v1/invoices/{inv_a['id']}", headers=hdr, json=fix_a)
    check("reviewer corrections saved (A)", r.status_code == 200, r.text[:200])
    r = c.post(f"/api/v1/invoices/{inv_a['id']}/validate", headers=hdr)
    v = r.json() if r.status_code == 200 else {}
    check("validate after corrections (A)", r.status_code == 200 and v.get("valid") is True,
          json.dumps(v.get("issues", r.text[:200])))
    r = c.post(f"/api/v1/invoices/{inv_a['id']}/approve", headers=hdr)
    check("approve invoice (A)", r.status_code == 200, r.text[:300])

    fix_b = {"invoice_number": "GCF-88121", "invoice_date": "2026-07-01",
              "subtotal": 6070.0, "tax_total": 0.0, "total": 6070.0,
              "supplier": {"name": "Gulf Coast Fuel Supply LLC", "tax_id": "",
                            "address": [], "email": "", "phone": ""},
              "lines": [
                  {"line_number": 1, "description": "Jet A Fuel (gal)", "quantity": 1200,
                   "uom": "GAL", "unit_price": 4.85, "net_amount": 5820.0,
                   "tax_amount": 0.0, "total_amount": 5820.0, "hsn_sac": "",
                   "category": "", "gl_code": ""},
                  {"line_number": 2, "description": "Into-plane fee", "quantity": 1,
                   "uom": "EA", "unit_price": 250.0, "net_amount": 250.0,
                   "tax_amount": 0.0, "total_amount": 250.0, "hsn_sac": "",
                   "category": "", "gl_code": ""},
              ]}
    r = c.patch(f"/api/v1/invoices/{inv_b['id']}", headers=hdr, json=fix_b)
    ok_fix = r.status_code == 200
    r = c.post(f"/api/v1/invoices/{inv_b['id']}/validate", headers=hdr)
    v = r.json() if r.status_code == 200 else {}
    ok_b = ok_fix and r.status_code == 200 and v.get("valid") is True
    r = c.post(f"/api/v1/invoices/{inv_b['id']}/approve", headers=hdr)
    check("correct + validate + approve invoice (B)", ok_b and r.status_code == 200,
          json.dumps(v.get("issues", [])) + " | " + r.text[:200])

    # send-back path on a fresh copy
    with open(US_PDF, "rb") as f:
        r = c.post("/api/v1/invoices/upload", headers=hdr, params={"organization_id": org_b},
                   files={"file": ("us_invoice2.pdf", f, "application/pdf")})
    inv_b2 = r.json()
    c.patch(f"/api/v1/invoices/{inv_b2['id']}", headers=hdr, json=fix_b)
    c.post(f"/api/v1/invoices/{inv_b2['id']}/validate", headers=hdr)
    r = c.post(f"/api/v1/invoices/{inv_b2['id']}/send-back", headers=hdr,
               json={"reason": "Missing PO reference — please re-check with supplier."})
    check("send-back with reason (mobile reject flow)", r.status_code == 200, r.text[:200])

    # ---------- 8. Dry-run posting ----------
    r = c.post(f"/api/v1/invoices/{inv_a['id']}/post", headers=hdr,
               json={"target": "tally", "dry_run": True, "client_profile_id": profile_a_id})
    pr = r.json() if r.status_code == 200 else {}
    check("Tally dry-run post (A)", r.status_code == 200 and pr.get("success") is True,
          "MSG: " + str(pr.get("message")) + " ISSUES: " + json.dumps(pr.get("issues") or (pr.get("response_payload") or {}).get("issues") or [])[:400])
    r = c.post(f"/api/v1/invoices/{inv_b['id']}/post", headers=hdr,
               json={"target": "quickbooks", "dry_run": True, "client_profile_id": profile_b_id})
    check("QuickBooks dry-run preflight (B)", r.status_code == 200 and r.json().get("success") is True, r.text[:300])

    # ---------- 9. Batch post via jobs + worker ----------
    r = c.post(f"/api/v1/organizations/{org_a}/jobs/post-ready", headers=hdr,
               json={"target": "tally", "dry_run": True, "client_profile_id": profile_a_id, "status": "approved"})
    check("enqueue batch-post job", r.status_code in (200, 201, 202), r.text[:300])
    job_id = (r.json().get("job") or {}).get("id") or r.json().get("id", "")

    # Drive the worker exactly as the worker service does (claim -> execute -> finish)
    processed = worker_mod.run_once(APP)
    r = c.get(f"/api/v1/jobs/{job_id}", headers=hdr)
    job_done = (
        processed and r.status_code == 200
        and r.json().get("status") == "done"
        and r.json().get("result", {}).get("succeeded", 0) >= 1
    )
    check("worker claims and completes batch job", job_done, r.text[:300])

    # ---------- 10. Tally connector claim/results (client-side agent path) ----------
    # The desktop connector polls and CLAIMS approved invoices for its profile;
    # the claim itself creates the posting. No direct /post call is needed.
    conn_hdr = {"X-SiftEntry-Connector-Token": "qa-connector-token-neel-0001"}
    r = c.post("/api/v1/connectors/tally/jobs/claim", headers=conn_hdr,
               json={"workspace_id": "neel-ws-1", "limit": 5})
    claimed = r.status_code == 200 and len(r.json().get("jobs", [])) >= 1
    check("connector claims Tally job with token", claimed, r.text[:300])
    if claimed:
        job = r.json()["jobs"][0]
        check("connector job carries Tally XML", "<ENVELOPE>" in (job.get("xml") or ""), (job.get("xml") or "")[:60])
        r = c.post("/api/v1/connectors/tally/jobs/results", headers=conn_hdr, json={
            "workspace_id": "neel-ws-1",
            "results": [{"posting_id": job["posting_id"], "invoice_id": job["invoice_id"],
                          "success": True, "message": "Tally voucher created: CBC-2026-0142",
                          "external_id": "VCH-1042", "raw": {}}],
        })
        check("connector submits result, invoice POSTED", r.status_code == 200 and r.json().get("accepted") == 1, r.text[:300])
    r = c.post("/api/v1/connectors/tally/jobs/claim",
               headers={"X-SiftEntry-Connector-Token": "wrong-token"},
               json={"workspace_id": "neel-ws-1", "limit": 5})
    check("connector rejects wrong token", r.status_code == 401, str(r.status_code))

    # ---------- 11. Document retrieval ----------
    r = c.get(f"/api/v1/invoices/{inv_a['id']}/document", headers=hdr)
    check("document download works", r.status_code == 200 and r.content[:4] == b"%PDF", str(r.status_code))
    check("document has filename header", "filename" in (r.headers.get("content-disposition") or "").lower(),
          r.headers.get("content-disposition", "<missing>"))

    # ---------- 12. Inbound email intake ----------
    pdf_b64 = base64.b64encode(open(US_PDF, "rb").read()).decode()
    r = c.post("/api/v1/inbound/email",
               headers={"X-SiftEntry-Inbound-Secret": "qa-inbound-secret-24chars!!"},
               json={"organization_id": org_b, "from_email": "ap@gulfcoast.test",
                     "to_email": "invoices@in.siftentry.test", "subject": "Invoice GCF-88121",
                     "message_id": "<qa-1>", "parser_mode": "auto", "client_profile_id": None,
                     "attachments": [{"filename": "emailed.pdf", "content_type": "application/pdf",
                                       "content_base64": pdf_b64}]})
    check("inbound email intake accepted", r.status_code == 202, r.text[:300])
    r = c.post("/api/v1/inbound/email", headers={"X-SiftEntry-Inbound-Secret": "bad"},
               json={"organization_id": org_b, "attachments": []})
    check("inbound email rejects wrong secret", r.status_code == 403, str(r.status_code))

    # ---------- 13. Invitations + email delivery (log provider) ----------
    r = c.post(f"/api/v1/organizations/{org_a}/invitations", headers=hdr,
               json={"email": "clerk@neel.test", "role": "accountant"})
    check("create invitation", r.status_code in (200, 201), r.text[:300])
    r = c.post("/api/v1/auth/password-reset/request", json={"email": "udit@siftentry.test"})
    check("password reset request accepted", r.status_code == 200, r.text[:300])

    # ---------- 14. Cross-org isolation ----------
    r2 = c.post("/api/v1/auth/bootstrap", json={
        "email": "other@x.test", "password": "another-password-123",
        "full_name": "Other", "organization_name": "Other Co", "legal_names": [], "default_currency": "USD"})
    check("second bootstrap blocked (single-owner rule)", r2.status_code == 409, str(r2.status_code))
    r = c.get(f"/api/v1/invoices/{inv_a['id']}")
    check("unauthenticated access blocked", r.status_code in (401, 403), str(r.status_code))

    # ---------- 15. Learning export/import round-trip ----------
    r = c.get(f"/api/v1/organizations/{org_a}/learning/export", headers=hdr)
    ok_export = r.status_code == 200
    bundle = r.json() if ok_export else {}
    r = c.post(f"/api/v1/organizations/{org_a}/learning/import", headers=hdr, json=bundle)
    check("learning bundle export/import round-trip", ok_export and r.status_code == 200, r.text[:200])

    # ---------- 16. Storage cleanup ----------
    r = c.post(f"/api/v1/organizations/{org_a}/storage/cleanup", headers=hdr)
    check("storage retention cleanup endpoint", r.status_code == 200, r.text[:200])

    # ---------- 17. AI status (confirm OFF) ----------
    r = c.get("/api/v1/system/ai-extraction", headers=hdr)
    ai = r.json() if r.status_code == 200 else {}
    check("AI extraction reports non-live (off for pilot)", r.status_code == 200 and not ai.get("live_provider", True), json.dumps(ai)[:200])

    # ---------- 18. Logout ----------
    r = c.post("/api/v1/auth/logout", headers=hdr, json={"refresh_token": refresh_token})
    check("logout", r.status_code in (200, 204), r.text[:200])

    # ---------- Summary ----------
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n===== QA SUMMARY: {passed}/{len(RESULTS)} passed =====")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAILED: {name} — {detail}")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    make_sample_pdfs()
    with TestClient(APP) as CLIENT:
        main()
