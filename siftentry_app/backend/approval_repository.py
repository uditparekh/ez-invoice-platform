"""Transactional approval storage, shared by SQLite and PostgreSQL."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .approval_plans import (
    ApprovalConflict,
    build_plan,
    invoice_fingerprint,
    profile_fingerprint,
)


class ApprovalRepository:
    def _locked_profile(self, connection, profile_id):
        # First lock in approval and claim; profile updates take this same lock.
        # No network I/O inside the transaction.
        connection.execute(
            "UPDATE client_profiles SET id = id WHERE id = ?", (profile_id,)
        )
        row = connection.execute(
            "SELECT * FROM client_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return self._client_profile_from_row(row) if row else None

    def get_approval_plan(self, invoice_id):
        with self._connect() as connection:
            return self._latest_approval(connection, invoice_id)

    def _latest_approval(self, connection, invoice_id):
        row = connection.execute(
            "SELECT * FROM approval_plans WHERE invoice_id = ? ORDER BY version DESC LIMIT 1",
            (invoice_id,),
        ).fetchone()
        if not row:
            return None
        return {
            **json.loads(row["plan_json"]),
            "id": row["id"],
            "version": row["version"],
            "approved_at": row["approved_at"],
            "approved_by": row["approved_by"],
        }

    def approve_plan(self, invoice_id, profile_id, preview_hash, actor_id):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            profile = self._locked_profile(connection, profile_id)
            row = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            if (
                not profile
                or not row
                or profile.organization_id != row["organization_id"]
            ):
                raise ApprovalConflict("The selected profile is no longer available.")
            invoice = self._invoice_from_row(connection, row)
            if invoice.status != "validated":
                raise ApprovalConflict(
                    "Validate the current invoice before approving its posting plan."
                )
            snapshot = self._master_view(connection, profile)["snapshot"]
            plan = build_plan(invoice, profile, snapshot["company"]["guid"] if snapshot else "")
            if plan["preview_hash"] != preview_hash:
                raise ApprovalConflict(
                    "Invoice or posting rules changed. Reload and review the new entry before approving."
                )
            if plan["blocking_issues"]:
                raise ApprovalConflict(" ".join(plan["blocking_issues"]))
            cursor = connection.execute(
                "UPDATE invoices SET status = 'approved', updated_at = ? WHERE id = ? AND status = 'validated' AND updated_at = ?",
                (now, invoice_id, invoice.updated_at.isoformat()),
            )
            if cursor.rowcount != 1:
                raise ApprovalConflict(
                    "Invoice changed during approval. Reload and review it again."
                )
            previous = self._latest_approval(connection, invoice_id)
            version = previous["version"] + 1 if previous else 1
            plan_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO approval_plans (id, invoice_id, organization_id, client_profile_id, version, plan_json, approved_by, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    invoice_id,
                    invoice.organization_id,
                    profile_id,
                    version,
                    json.dumps(plan, ensure_ascii=True),
                    actor_id,
                    now,
                ),
            )
            self._insert_audit(
                connection,
                invoice.organization_id,
                invoice_id,
                "invoice.approved",
                {
                    "actor_id": actor_id,
                    "status": "approved",
                    "plan_id": plan_id,
                    "plan_version": version,
                    "preview_hash": preview_hash,
                    "client_profile_id": profile_id,
                },
            )
        return self.get_invoice(invoice_id)

    def _approved_plan_for_claim(self, connection, invoice_id, profile_id):
        profile = self._locked_profile(connection, profile_id)
        row = connection.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        plan = self._latest_approval(connection, invoice_id)
        if not row or not profile or not plan or row["status"] != "approved":
            return None
        invoice = self._invoice_from_row(connection, row)
        snapshot = self._master_view(connection, profile)["snapshot"]
        if (
            plan["schema_version"] != 2
            or not snapshot
            or plan.get("company_guid") != snapshot["company"]["guid"]
            or plan["client_profile_id"] != profile_id
            or plan["organization_id"] != invoice.organization_id
            or profile.organization_id != invoice.organization_id
            or plan["profile_fingerprint"] != profile_fingerprint(profile)
            or plan["invoice_fingerprint"] != invoice_fingerprint(invoice)
        ):
            return None
        return plan, invoice.updated_at.isoformat()

    def _invalidate_profile_approvals(self, connection, profile_id, actor_id):
        rows = connection.execute(
            """SELECT id, organization_id FROM invoices WHERE status = 'approved' AND id IN (
                SELECT p.invoice_id FROM approval_plans p WHERE p.client_profile_id = ?
                AND p.version = (SELECT MAX(latest.version) FROM approval_plans latest WHERE latest.invoice_id = p.invoice_id)
            )""",
            (profile_id,),
        ).fetchall()
        for row in rows:
            changed = connection.execute(
                "UPDATE invoices SET status = 'validated', updated_at = ? WHERE id = ? AND status = 'approved'",
                (datetime.now(timezone.utc).isoformat(), row["id"]),
            )
            if changed.rowcount:
                self._insert_audit(
                    connection,
                    row["organization_id"],
                    row["id"],
                    "invoice.approval_invalidated",
                    {
                        "actor_id": actor_id,
                        "client_profile_id": profile_id,
                        "reason": "Accounting configuration changed; review and reapprove the posting plan.",
                    },
                )
