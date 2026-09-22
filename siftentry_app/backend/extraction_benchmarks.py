"""Versioned, tenant-scoped extraction evidence. Never writes accounting data."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .approval_plans import ApprovalConflict, digest
from .extraction_common import EXTRACTION_FIELDS, SYSTEM_PROMPT

CONTRACT_VERSION = "extraction-evidence-v1"
# Any parser/prompt change invalidates earlier qualification, even if a developer
# forgets to bump a hand-maintained version string.
PARSER_REVISION = hashlib.sha256(
    b"".join(
        (Path(__file__).parent / p).read_bytes()
        for p in (
            "parser_service.py",
            "domain.py",
            "extraction_common.py",
            "ai_parser.py",
            "extraction_benchmarks.py",
            "benchmark_service.py",
            "../universal_parser.py",
            "../gst_invoice_parser.py",
        )
    )
).hexdigest()
LINE_FIELDS = (
    "description",
    "quantity",
    "uom",
    "unit_price",
    "net_amount",
    "tax_amount",
    "total_amount",
    "hsn_sac",
)
NUMERIC = {
    "subtotal",
    "tax_total",
    "total",
    "quantity",
    "unit_price",
    "net_amount",
    "tax_amount",
    "total_amount",
}
LABELS = (
    "invoice no",
    "invoice number",
    "document no",
    "invoice date",
    "due date",
    "bill to",
    "ship to",
    "gstin",
    "tax invoice",
    "credit note",
    "debit note",
    "description",
    "quantity",
    "qty",
    "unit price",
    "subtotal",
    "sub total",
    "grand total",
    "total",
    "cgst",
    "sgst",
    "igst",
    "hsn",
    "sac",
    "purchase order",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def field_values(invoice):
    return {
        **{
            name: getattr(invoice, name)
            for name in EXTRACTION_FIELDS
            if not name.startswith("supplier_")
        },
        "supplier_name": invoice.supplier.name,
        "supplier_tax_id": invoice.supplier.tax_id,
        "lines": [
            {field: getattr(line, field) for field in LINE_FIELDS}
            for line in invoice.lines
        ],
    }


def extraction_scope(profile_id, values, text, pages, pdf_bytes=b""):
    # A conservative layout signature, not an assertion that two PDFs are identical.
    # It contains only known labels and their relative ordering, never invoice values.
    pattern = (
        r"\b(?:"
        + "|".join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True))
        + r")\b"
    )
    labels = re.findall(pattern, normalized(text))[:300]
    geometry = []
    if pdf_bytes:
        try:
            import fitz

            with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
                for page_index, page in enumerate(document):
                    for label in sorted(set(labels)):
                        for rect in page.search_for(label)[:3]:
                            geometry.append(
                                (
                                    page_index,
                                    label,
                                    round(rect.x0 / page.rect.width * 20),
                                    round(rect.y0 / page.rect.height * 20),
                                )
                            )
        except (ImportError, ValueError, RuntimeError):
            geometry = []
    document_type = (
        "credit_note"
        if "credit note" in normalized(text)
        else "debit_note" if "debit note" in normalized(text) else "invoice"
    )
    supplier = normalized(values.get("supplier_tax_id")) or normalized(
        values.get("supplier_name")
    )
    return {
        "profile_id": profile_id or "",
        "supplier_key": supplier,
        "layout": digest({"labels": labels, "pages": pages, "geometry": geometry}),
        "currency": str(values.get("currency") or "").upper(),
        "document_type": document_type,
        "recognizable": len(set(labels)) >= 4 and bool(supplier) and bool(geometry),
    }


def scope_key(scope):
    return digest(scope)


def extraction_revision(profile):
    t = profile.settings.training_profile
    return digest(
        {
            "contract": CONTRACT_VERSION,
            "parser": PARSER_REVISION,
            "prompt": SYSTEM_PROMPT,
            "instructions": t.extraction_instructions,
            "exceptions": t.exception_examples,
            "expected_fields": t.expected_fields,
            "validation_rules": t.validation_rules,
            "currency": profile.settings.default_currency,
            "country": profile.settings.country_code,
            "tax_mode": profile.settings.tax_mode,
            "policy": t.llm_policy,
        }
    )


def quality_reasons(values, text, scope):
    reasons = []
    if not scope.get("recognizable"):
        reasons.append("unrecognized_layout")
    if scope.get("document_type") != "invoice":
        reasons.append("non_invoice_document")
    if len(text.strip()) < 100 or "\ufffd" in text:
        reasons.append("weak_text_layer")
    if not all(
        values.get(k)
        for k in ("invoice_number", "invoice_date", "supplier_name", "currency")
    ):
        reasons.append("missing_required_field")
    try:
        subtotal, tax, total = (
            Decimal(str(values.get(k, 0))) for k in ("subtotal", "tax_total", "total")
        )
        if (
            not all(v.is_finite() for v in (subtotal, tax, total))
            or total <= 0
            or abs(subtotal + tax - total) > Decimal("0.02")
        ):
            reasons.append("arithmetic_mismatch")
        rows = values.get("lines") or []
        if not rows or abs(
            sum(Decimal(str(r.get("net_amount", 0))) for r in rows) - subtotal
        ) > Decimal("0.02"):
            reasons.append("line_arithmetic_mismatch")
    except (InvalidOperation, TypeError, ValueError):
        reasons.append("invalid_amount")
    return reasons


class ExpectedLine(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=500)
    quantity: float
    uom: str = Field(max_length=50)
    unit_price: float
    net_amount: float
    tax_amount: float
    total_amount: float
    hsn_sac: str = Field(default="", max_length=50)


class ExpectedExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    invoice_number: str = Field(min_length=1, max_length=200)
    invoice_date: str
    due_date: str = ""
    supplier_name: str = Field(min_length=1, max_length=500)
    supplier_tax_id: str = Field(default="", max_length=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    subtotal: float
    tax_total: float
    total: float
    lines: list[ExpectedLine] = Field(min_length=1, max_length=100)

    @field_validator("invoice_date", "due_date")
    @classmethod
    def date_value(cls, value):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("invoice_number", "supplier_name", "invoice_date")
    @classmethod
    def required_text(cls, value):
        if not value.strip():
            raise ValueError("A confirmed value is required")
        return value.strip()


class BenchmarkConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected: ExpectedExtraction
    split: Literal["learning", "held_out"] = "held_out"
    confirmed: Literal[True]
    retain_for_checks: Literal[True]
    review_seconds: int | None = Field(default=None, ge=1, le=86400)


class AnchorLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str = Field(min_length=1, max_length=100)
    field: Literal[
        "invoice_number",
        "invoice_date",
        "due_date",
        "supplier_name",
        "supplier_tax_id",
        "currency",
        "subtotal",
        "tax_total",
        "total",
    ]
    anchor: str = Field(min_length=2, max_length=80, pattern=r"^[^\d\r\n\x00-\x1f]+$")
    relation: Literal["after_label", "below_label", "same_row"] = "after_label"
    confirmed: Literal[True]


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_ai: bool = False


def compare(expected, actual):
    checks = []

    def add(path, want, got):
        field = path.rsplit(".", 1)[-1]
        if field in NUMERIC:
            try:
                a, b = Decimal(str(want)), Decimal(str(got))
                equal = a.is_finite() and b.is_finite() and a == b
            except (InvalidOperation, ValueError, TypeError):
                equal = False
        elif field in {"invoice_date", "due_date"}:

            def canonical_date(value):
                if not value:
                    return ""
                for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
                    try:
                        return datetime.strptime(str(value), fmt).date().isoformat()
                    except ValueError:
                        pass
                return str(value)

            equal = canonical_date(want) == canonical_date(got)
        else:
            equal = str(want).strip() == str(got).strip() if got is not None else False
        checks.append({"field": path, "expected": want, "actual": got, "match": equal})

    for field in EXTRACTION_FIELDS:
        add(field, expected[field], actual.get(field))
    expected_lines, actual_lines = expected["lines"], actual.get("lines") or []
    add("line_count", len(expected_lines), len(actual_lines))
    for i, line in enumerate(expected_lines):
        found = actual_lines[i] if i < len(actual_lines) else {}
        for field in LINE_FIELDS:
            add(f"lines.{i}.{field}", line[field], found.get(field))
    matched = sum(c["match"] for c in checks)
    return {
        "matches": matched,
        "checked": len(checks),
        "passed": matched == len(checks),
        "checks": checks,
    }


class ExtractionBenchmarkRepository:
    def initialize_extraction_benchmarks(self, connection):
        connection.executescript(
            """
        CREATE TABLE IF NOT EXISTS extraction_revisions (
            profile_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS extraction_runs (
            job_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS extraction_runs_profile ON extraction_runs(profile_id);
        CREATE TABLE IF NOT EXISTS extraction_samples (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, profile_id TEXT NOT NULL,
            file_hash TEXT NOT NULL, document_key TEXT NOT NULL, filename TEXT NOT NULL,
            storage_json TEXT NOT NULL, expected_json TEXT NOT NULL, scope_json TEXT NOT NULL,
            split TEXT NOT NULL, confirmed_by TEXT NOT NULL, review_seconds INTEGER,
            created_at TEXT NOT NULL, deleted_at TEXT NOT NULL DEFAULT '',
            UNIQUE(profile_id, document_key), UNIQUE(profile_id, file_hash));
        CREATE TABLE IF NOT EXISTS extraction_lessons (
            id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, sample_id TEXT NOT NULL,
            scope_key TEXT NOT NULL, field TEXT NOT NULL, anchor TEXT NOT NULL,
            relation TEXT NOT NULL, confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS extraction_lessons_scope ON extraction_lessons(profile_id, scope_key);
        """
        )

    def bump_extraction_revision(self, connection, profile_id):
        if profile_id:
            connection.execute(
                """INSERT INTO extraction_revisions(profile_id, revision) VALUES (?, 1)
                ON CONFLICT(profile_id) DO UPDATE SET revision = extraction_revisions.revision + 1""",
                (profile_id,),
            )

    def extraction_revision_number(self, profile_id):
        with self._connect() as c:
            row = c.execute(
                "SELECT revision FROM extraction_revisions WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        return row["revision"] if row else 0

    def benchmark_samples(self, profile_id):
        with self._connect() as c:
            rows = c.execute(
                "SELECT * FROM extraction_samples WHERE profile_id = ? AND deleted_at = '' ORDER BY created_at, id",
                (profile_id,),
            ).fetchall()
        return [
            {
                **dict(r),
                "expected": json.loads(r["expected_json"]),
                "scope": json.loads(r["scope_json"]),
            }
            for r in rows
        ]

    def add_benchmark(self, profile, stored, filename, content, body, scope, actor_id):
        document_key = digest(
            {
                "supplier": scope["supplier_key"],
                "number": body.expected.invoice_number,
                "type": scope["document_type"],
            }
        )
        with self._connect() as c:
            if not self._locked_profile(c, profile.id):
                raise ApprovalConflict(
                    "Profile was deleted. Reload before changing evidence."
                )
            if (
                c.execute(
                    "SELECT COUNT(*) AS n FROM extraction_samples WHERE profile_id = ? AND deleted_at = ''",
                    (profile.id,),
                ).fetchone()["n"]
                >= 20
            ):
                raise ApprovalConflict(
                    "This profile supports at most 20 benchmark PDFs. Delete obsolete samples first."
                )
            if c.execute(
                "SELECT id FROM extraction_samples WHERE profile_id = ? AND (file_hash = ? OR document_key = ?)",
                (profile.id, hashlib.sha256(content).hexdigest(), document_key),
            ).fetchone():
                raise ApprovalConflict(
                    "This document is already in the benchmark history. A learning document cannot become held-out evidence."
                )
            sample_id = str(uuid.uuid4())
            c.execute(
                """INSERT INTO extraction_samples (id, organization_id, profile_id, file_hash, document_key, filename, storage_json, expected_json, scope_json, split, confirmed_by, review_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sample_id,
                    profile.organization_id,
                    profile.id,
                    hashlib.sha256(content).hexdigest(),
                    document_key,
                    filename,
                    json.dumps(stored.__dict__),
                    body.expected.model_dump_json(),
                    json.dumps(scope),
                    body.split,
                    actor_id,
                    body.review_seconds,
                    now(),
                ),
            )
            self.bump_extraction_revision(c, profile.id)
            self._insert_audit(
                c,
                profile.organization_id,
                None,
                "extraction.sample_confirmed",
                {
                    "sample_id": sample_id,
                    "profile_id": profile.id,
                    "split": body.split,
                    "actor_id": actor_id,
                },
            )
        return sample_id

    def benchmark_lessons(self, profile_id, scope=None, exclude_sample_id=""):
        with self._connect() as c:
            rows = c.execute(
                """SELECT l.* FROM extraction_lessons l JOIN extraction_samples s ON s.id = l.sample_id
                WHERE l.profile_id = ? AND l.deleted_at = '' AND s.deleted_at = '' AND s.split = 'learning'
                ORDER BY l.created_at, l.id""",
                (profile_id,),
            ).fetchall()
        return [
            dict(r)
            for r in rows
            if r["sample_id"] != exclude_sample_id
            and (scope is None or r["scope_key"] == scope_key(scope))
        ]

    def add_anchor_lesson(self, profile, sample, body, actor_id):
        with self._connect() as c:
            if not self._locked_profile(c, profile.id):
                raise ApprovalConflict(
                    "Profile was deleted. Reload before changing evidence."
                )
            row = c.execute(
                "SELECT * FROM extraction_samples WHERE id = ? AND profile_id = ? AND deleted_at = '' AND split = 'learning'",
                (sample["id"], profile.id),
            ).fetchone()
            if not row:
                raise ApprovalConflict(
                    "Lessons require an active learning sample, never a held-out sample."
                )
            # One active instruction per field/scope; explicit replacement is auditable.
            c.execute(
                "UPDATE extraction_lessons SET deleted_at = ? WHERE profile_id = ? AND scope_key = ? AND field = ? AND deleted_at = ''",
                (now(), profile.id, scope_key(sample["scope"]), body.field),
            )
            lesson_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO extraction_lessons(id, profile_id, sample_id, scope_key, field, anchor, relation, confirmed_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lesson_id,
                    profile.id,
                    sample["id"],
                    scope_key(sample["scope"]),
                    body.field,
                    body.anchor.strip(),
                    body.relation,
                    actor_id,
                    now(),
                ),
            )
            self.bump_extraction_revision(c, profile.id)
            self._insert_audit(
                c,
                profile.organization_id,
                None,
                "extraction.lesson_confirmed",
                {
                    "profile_id": profile.id,
                    "lesson_id": lesson_id,
                    "field": body.field,
                    "actor_id": actor_id,
                },
            )
        return lesson_id

    def delete_benchmark_item(self, profile, item_id, kind, actor_id):
        table = "extraction_samples" if kind == "sample" else "extraction_lessons"
        with self._connect() as c:
            if not self._locked_profile(c, profile.id):
                raise ApprovalConflict(
                    "Profile was deleted. Reload before changing evidence."
                )
            row = c.execute(
                f"SELECT * FROM {table} WHERE id = ? AND profile_id = ? AND deleted_at = ''",
                (item_id, profile.id),
            ).fetchone()
            if not row:
                raise ApprovalConflict("Item is no longer available.")
            c.execute(
                f"UPDATE {table} SET deleted_at = ? WHERE id = ?", (now(), item_id)
            )
            if kind == "sample":
                c.execute(
                    "UPDATE extraction_lessons SET deleted_at = ? WHERE sample_id = ? AND deleted_at = ''",
                    (now(), item_id),
                )
                c.execute(
                    "UPDATE extraction_samples SET expected_json = '{}' WHERE id = ?",
                    (item_id,),
                )
            self.bump_extraction_revision(c, profile.id)
            self._insert_audit(
                c,
                profile.organization_id,
                None,
                "extraction." + kind + "_deleted",
                {"profile_id": profile.id, "id": item_id, "actor_id": actor_id},
            )
        return dict(row)

    def pending_benchmark_deletions(self, profile_id=None):
        with self._connect() as c:
            rows = c.execute(
                "SELECT id, storage_json FROM extraction_samples WHERE deleted_at != '' AND storage_json != '{}'"
                + (" AND profile_id = ?" if profile_id else "")
                + " ORDER BY deleted_at LIMIT 100",
                (profile_id,) if profile_id else (),
            ).fetchall()
        return [dict(row) for row in rows]

    def confirm_benchmark_pdf_deleted(self, sample_id):
        with self._connect() as c:
            c.execute(
                "UPDATE extraction_samples SET storage_json = '{}' WHERE id = ? AND deleted_at != ''",
                (sample_id,),
            )

    def latest_benchmark_job(self, profile):
        with self._connect() as c:
            row = c.execute(
                "SELECT j.* FROM jobs j JOIN extraction_runs r ON r.job_id = j.id WHERE r.profile_id = ? AND j.organization_id = ? ORDER BY j.created_at DESC LIMIT 1",
                (profile.id, profile.organization_id),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def queue_benchmark(self, profile, config, include_ai, actor_id):
        with self._connect() as c:
            profile = self._locked_profile(c, profile.id)
            if not profile:
                raise ApprovalConflict(
                    "Profile was deleted. Reload before running checks."
                )
            active = c.execute(
                "SELECT j.id FROM jobs j JOIN extraction_runs r ON r.job_id = j.id WHERE r.profile_id = ? AND j.status IN ('queued', 'running')",
                (profile.id,),
            ).fetchone()
            if active:
                raise ApprovalConflict(
                    "A check is already queued or running for this profile."
                )
            rows = c.execute(
                "SELECT * FROM extraction_samples WHERE profile_id = ? AND deleted_at = '' ORDER BY created_at, id",
                (profile.id,),
            ).fetchall()
            if not rows:
                raise ApprovalConflict("Add a confirmed benchmark PDF first.")
            samples = [
                {
                    "id": r["id"],
                    "filename": r["filename"],
                    "file_hash": r["file_hash"],
                    "expected": json.loads(r["expected_json"]),
                    "scope": json.loads(r["scope_json"]),
                    "split": r["split"],
                    "review_seconds": r["review_seconds"],
                }
                for r in rows
            ]
            lesson_rows = c.execute(
                "SELECT l.* FROM extraction_lessons l JOIN extraction_samples s ON s.id = l.sample_id WHERE l.profile_id = ? AND l.deleted_at = '' AND s.deleted_at = '' AND s.split = 'learning'",
                (profile.id,),
            ).fetchall()
            revision = c.execute(
                "SELECT revision FROM extraction_revisions WHERE profile_id = ?",
                (profile.id,),
            ).fetchone()
            org = c.execute(
                "SELECT * FROM organizations WHERE id = ?", (profile.organization_id,)
            ).fetchone()
            clean = profile.model_copy(deep=True)
            clean.settings.connection_settings = {}
            clean.settings.metadata = {}
            clean.settings.training_profile.sample_invoices = []
            payload = {
                "profile_id": profile.id,
                "profile": clean.model_dump(mode="json"),
                "legal_names": json.loads(org["legal_names_json"]) or [org["name"]],
                "include_ai": include_ai,
                "provider_config": config.status(),
                "revision": revision["revision"] if revision else 0,
                "extraction_revision": extraction_revision(profile),
                "samples": samples,
                "lessons": [dict(r) for r in lesson_rows],
            }
            job_id, at = str(uuid.uuid4()), now()
            c.execute(
                "INSERT INTO jobs(id, organization_id, kind, payload_json, status, actor_id, created_at, updated_at) VALUES (?, ?, 'extraction_benchmark', ?, 'queued', ?, ?, ?)",
                (
                    job_id,
                    profile.organization_id,
                    json.dumps(payload),
                    actor_id,
                    at,
                    at,
                ),
            )
            c.execute(
                "INSERT INTO extraction_runs(job_id, profile_id) VALUES (?, ?)",
                (job_id, profile.id),
            )
            self._insert_audit(
                c,
                profile.organization_id,
                None,
                "extraction.check_queued",
                {
                    "profile_id": profile.id,
                    "job_id": job_id,
                    "include_ai": include_ai,
                    "actor_id": actor_id,
                },
            )
        return self.get_job(job_id)

    def cancel_benchmark(self, profile, actor_id):
        with self._connect() as c:
            self._locked_profile(c, profile.id)
            rows = c.execute(
                "SELECT j.id FROM jobs j JOIN extraction_runs r ON r.job_id = j.id WHERE r.profile_id = ? AND j.status IN ('queued', 'running')",
                (profile.id,),
            ).fetchall()
            for row in rows:
                c.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND status IN ('queued', 'running')",
                    (
                        "Cancelled by reviewer. An in-flight provider request may finish, but cannot publish results.",
                        now(),
                        row["id"],
                    ),
                )
                self._insert_audit(
                    c,
                    profile.organization_id,
                    None,
                    "extraction.check_cancelled",
                    {
                        "job_id": row["id"],
                        "profile_id": profile.id,
                        "actor_id": actor_id,
                    },
                )

    def extraction_guidance(self, profile, scope, reasons, provider_config=None):
        lessons = self.benchmark_lessons(profile.id, scope)
        eligible = False
        job = self.latest_benchmark_job(profile)
        if (
            job
            and job.status == "done"
            and job.result.get("revision")
            == self.extraction_revision_number(profile.id)
            and job.result.get("extraction_revision") == extraction_revision(profile)
            and (
                not job.payload.get("include_ai")
                or provider_config is None
                or job.payload.get("provider_config") == provider_config
            )
        ):
            age = datetime.now(timezone.utc) - job.updated_at
            rows = [
                r
                for r in job.result.get("samples", [])
                if r.get("scope_key") == scope_key(scope)
                and r.get("split") == "held_out"
            ]
            eligible = (
                age.total_seconds() < 7 * 86400
                and len(rows) >= 5
                and all(r.get("baseline", {}).get("passed") for r in rows)
            )
        if not eligible:
            reasons = [*reasons, "held_out_evidence_required"]
        return {
            "lessons": [
                {k: l[k] for k in ("id", "field", "anchor", "relation")}
                for l in lessons
            ],
            "reasons": reasons,
            "allow_skip": eligible and not reasons,
        }
