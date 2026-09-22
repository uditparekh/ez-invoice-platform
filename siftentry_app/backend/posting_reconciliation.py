"""Single-use execution permits and read-only recovery for connector claims."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

from .approval_plans import ApprovalConflict, digest, profile_fingerprint
from ..tally_reconciliation import verify_voucher, ReconciliationError


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=160)
    posting_ids: list[str] = Field(default_factory=list, max_length=100)


class ExecutionRequest(RecoveryRequest):
    posting_id: str = Field(min_length=1, max_length=100)


class RecoveryEvidence(ExecutionRequest):
    company: dict[str, str] = Field(default_factory=dict)
    voucher_xml: str = Field(default="", max_length=256 * 1024)
    message: str = Field(default="", max_length=1000)


class ReconciliationRepository:
    def connector_recovery_jobs(self, profile, posting_ids=None):
        with self._connect() as connection:
            ids = list(dict.fromkeys(posting_ids or []))[:100]
            terminal_clause = (
                " OR id IN (" + ",".join("?" for _ in ids) + ")" if ids else ""
            )
            rows = connection.execute(
                """SELECT * FROM posting_attempts WHERE client_profile_id = ? AND organization_id = ?
                AND target = 'tally' AND (status = 'started'"""
                + terminal_clause
                + ") AND dry_run = 0 ORDER BY created_at LIMIT 100",
                (profile.id, profile.organization_id, *ids),
            ).fetchall()
        return [self._posting_from_row(row) for row in rows]

    def begin_connector_execution(self, authenticated_profile, posting_id):
        with self._connect() as connection:
            profile = self._locked_profile(connection, authenticated_profile.id)
            connection.execute(
                "UPDATE posting_attempts SET id = id WHERE id = ?", (posting_id,)
            )
            row = connection.execute(
                "SELECT * FROM posting_attempts WHERE id = ?", (posting_id,)
            ).fetchone()
            if (
                not profile
                or not row
                or row["client_profile_id"] != profile.id
                or row["organization_id"] != profile.organization_id
            ):
                raise ApprovalConflict("Posting does not belong to this connector.")
            posting = self._posting_from_row(row)
            plan = posting.request_payload.get("posting_plan", {})
            if (
                posting.status != "started"
                or posting.dry_run
                or posting.target != "tally"
                or plan.get("schema_version") != 2
                or posting.raw.get("execution")
                or plan.get("profile_fingerprint") != profile_fingerprint(profile)
            ):
                raise ApprovalConflict(
                    "Posting is already reserved for execution, legacy, or changed. Reconcile; do not retry."
                )
            view = self._master_view(connection, profile)
            if (
                not view["snapshot"]
                or view["snapshot"]["company"]["name"] != plan["company"]
                or view["snapshot"]["company"]["guid"] != plan.get("company_guid")
            ):
                raise ApprovalConflict(
                    "Sync Tally masters for the current company before posting. This claim remains on hold."
                )
            execution = {
                "company": view["snapshot"]["company"],
                "snapshot_id": view["snapshot"]["id"],
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "posting_reference": plan["posting_reference"],
            }
            raw = {**posting.raw, "execution": execution}
            connection.execute(
                "UPDATE posting_attempts SET raw_json = ? WHERE id = ? AND status = 'started'",
                (json.dumps(raw), posting_id),
            )
            self._insert_audit(
                connection,
                profile.organization_id,
                posting.invoice_id,
                "posting.execution_reserved",
                {
                    "posting_id": posting_id,
                    "company": execution["company"],
                    "posting_reference": plan["posting_reference"],
                },
            )
        return {"success": True, "execution": execution}

    def record_reconciliation_hold(self, posting, message):
        message = message[:1000]
        with self._connect() as connection:
            connection.execute(
                "UPDATE posting_attempts SET id = id WHERE id = ?", (posting.id,)
            )
            row = connection.execute(
                "SELECT * FROM posting_attempts WHERE id = ?", (posting.id,)
            ).fetchone()
            if not row or row["status"] != "started":
                return
            raw = json.loads(row["raw_json"] or "{}")
            evidence = {"state": "held", "message": message}
            if raw.get("reconciliation", {}).get("fingerprint") == digest(evidence):
                return
            raw["reconciliation"] = {
                **evidence,
                "fingerprint": digest(evidence),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                "UPDATE posting_attempts SET raw_json = ?, message = ? WHERE id = ?",
                (json.dumps(raw), "Recovery hold: " + message, posting.id),
            )
            self._insert_audit(
                connection,
                posting.organization_id,
                posting.invoice_id,
                "posting.reconciliation_held",
                {"posting_id": posting.id, **evidence},
            )

    def reconcile_connector_posting(self, profile, body):
        posting = self.get_posting(body.posting_id)
        if (
            not posting
            or posting.client_profile_id != profile.id
            or posting.organization_id != profile.organization_id
            or posting.target != "tally"
            or posting.dry_run
        ):
            raise ApprovalConflict("Posting does not belong to this connector.")
        execution = posting.raw.get("execution", {})
        if not body.voucher_xml:
            self.record_reconciliation_hold(
                posting, body.message or "Lookup inconclusive. Do not repost."
            )
            return {
                "success": False,
                "state": "held",
                "message": "Posting remains on hold. No voucher was imported.",
            }
        try:
            if not execution.get("company") or body.company != execution["company"]:
                raise ReconciliationError(
                    "Lookup company does not match the pinned execution company."
                )
            evidence = verify_voucher(
                posting.request_payload.get("posting_plan", {}), body.voucher_xml
            )
        except ReconciliationError as exc:
            self.record_reconciliation_hold(posting, str(exc))
            raise ApprovalConflict(str(exc)) from exc
        raw = {
            **posting.raw,
            "reconciliation": {
                "state": "matched",
                "company": body.company,
                **evidence,
                "voucher_xml": body.voucher_xml,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        completed, won = self.complete_posting_atomic(
            posting.id,
            success=True,
            message="Reconciled: existing Tally voucher matches the approved entry. No repost performed.",
            external_id=evidence["external_id"],
            raw=raw,
            response_payload=raw,
        )
        if not completed or not completed.success:
            raise ApprovalConflict(
                "A conflicting terminal result exists. Manual review required; no state was overwritten."
            )
        return {
            "success": True,
            "state": "matched",
            "posting_id": posting.id,
            "won": won,
            "message": "Existing Tally voucher verified and acknowledged. No repost performed.",
        }
