"""Company-bound master snapshots and explicit accountant confirmations.

Discovery never changes a profile, invoice, posting plan, or retry state.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .approval_plans import ApprovalConflict, digest, profile_fingerprint

KINDS = ("ledgers", "stock_items", "units", "godowns", "voucher_types")
FRESH_FOR = timedelta(hours=24)


class MasterRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=512)
    guid: str = Field(default="", max_length=512)
    parent: str = Field(default="", max_length=512)
    base_units: str = Field(default="", max_length=512)

    @field_validator("name", "guid", "parent", "base_units")
    @classmethod
    def safe_text(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("Master text contains unsupported control characters")
        return value


class MasterCompany(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=512)
    guid: str = Field(min_length=1, max_length=512)

    @field_validator("name", "guid")
    @classmethod
    def nonempty_identity(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Company identity is empty or contains control characters")
        return value


class MasterUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=160)
    ticket: str = Field(min_length=32, max_length=128)
    company: MasterCompany
    masters: dict[str, list[MasterRow]]

    @model_validator(mode="after")
    def complete_snapshot(self):
        if set(self.masters) != set(KINDS):
            raise ValueError("All five master collections are required")
        if sum(len(rows) for rows in self.masters.values()) > 10000:
            raise ValueError("Snapshot exceeds 10000 masters")
        for rows in self.masters.values():
            if len({row.name for row in rows}) != len(rows) or any(
                not row.name.strip() for row in rows
            ):
                raise ValueError(
                    "Master names must be nonempty and unique within each collection"
                )
        if (
            len(json.dumps(self.model_dump(), ensure_ascii=True).encode())
            > 2 * 1024 * 1024 + 2048
        ):
            raise ValueError("Snapshot exceeds the size limit")
        return self


class MasterConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(min_length=32, max_length=128)
    profile_fingerprint: str = Field(min_length=64, max_length=64)


def source_fingerprint(profile):
    settings = profile.settings
    connection = settings.connection_settings
    return digest(
        {
            "organization": profile.organization_id,
            "profile": profile.id,
            "system": profile.accounting_system,
            "company": settings.company_name,
            "workspace": connection.get("workspace_id"),
            "enabled": connection.get("connector_enabled", False),
            "tally_url": connection.get("tally_url")
            or connection.get("url")
            or "http://localhost:9000",
        }
    )


def mapping_checks(profile, masters):
    """Check only configured/effective names, not amounts or accounting correctness."""
    settings = profile.settings
    fields = [
        ("Voucher type", "voucher_types", settings.voucher_type or "Purchase"),
        ("Purchase ledger", "ledgers", settings.purchase_ledger or "Purchase Accounts"),
    ]
    for field in ("tax_ledger", "tcs_ledger", "round_off_ledger"):
        fields.append(
            (field.replace("_", " ").capitalize(), "ledgers", getattr(settings, field))
        )
    for field in ("igst_ledger", "cgst_ledger", "sgst_ledger"):
        fields.append(
            (
                field.replace("_", " ").upper(),
                "ledgers",
                str(settings.tax_settings.get(field) or ""),
            )
        )
    inventory = settings.posting_mode in ("item_invoice", "voucher_with_inventory")
    if inventory:
        fields.extend(
            [
                ("Stock item", "stock_items", settings.stock_item_name),
                ("Unit", "units", settings.stock_item_uom),
                ("Godown", "godowns", settings.godown_name),
            ]
        )
    for i, mapping in enumerate(settings.item_mappings):
        for field, kind in (
            ("purchase_ledger", "ledgers"),
            ("tax_ledger", "ledgers"),
            ("target_item_name", "stock_items"),
            ("target_uom", "units"),
        ):
            if kind in ("stock_items", "units") and not inventory:
                continue
            fields.append(
                (
                    f"Rule {i + 1}: {field.replace('_', ' ')}",
                    kind,
                    getattr(mapping, field),
                )
            )
    names = {kind: {row["name"] for row in masters.get(kind, [])} for kind in KINDS}
    return [
        {"field": label, "kind": kind, "name": value, "found": value in names[kind]}
        for label, kind, value in fields
        if value
    ]


class MasterRepository:
    def begin_master_sync(self, authenticated_profile):
        now = datetime.now(timezone.utc)
        ticket = secrets.token_hex(32)
        with self._connect() as connection:
            profile = self._locked_profile(connection, authenticated_profile.id)
            if (
                not profile
                or profile.updated_at != authenticated_profile.updated_at
                or not profile.settings.company_name
            ):
                raise ApprovalConflict(
                    "Save the exact Tally company name and reconnect before syncing."
                )
            connection.execute(
                """INSERT INTO tally_master_sync (profile_id, ticket, profile_revision, started_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(profile_id) DO UPDATE SET
                ticket = excluded.ticket, profile_revision = excluded.profile_revision, started_at = excluded.started_at""",
                (profile.id, ticket, profile.updated_at.isoformat(), now.isoformat()),
            )
        return {
            "success": True,
            "ticket": ticket,
            "company_name": profile.settings.company_name,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
        }

    def save_master_snapshot(self, authenticated_profile, body):
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            profile = self._locked_profile(connection, authenticated_profile.id)
            row = connection.execute(
                "SELECT * FROM tally_master_sync WHERE profile_id = ?",
                (authenticated_profile.id,),
            ).fetchone()
            if (
                not profile
                or not row
                or row["ticket"] != body.ticket
                or profile.updated_at != authenticated_profile.updated_at
                or row["profile_revision"] != profile.updated_at.isoformat()
                or now - datetime.fromisoformat(row["started_at"])
                > timedelta(minutes=10)
                or body.company.name != profile.settings.company_name
            ):
                raise ApprovalConflict(
                    "Sync expired, was superseded, or the profile changed. Run Sync Tally masters again."
                )
            snapshot = {
                "id": body.ticket,
                "company": body.company.model_dump(),
                "masters": {
                    kind: [item.model_dump() for item in rows]
                    for kind, rows in body.masters.items()
                },
                "synced_at": now.isoformat(),
                "source_fingerprint": source_fingerprint(profile),
            }
            connection.execute(
                "UPDATE tally_master_sync SET ticket = '', snapshot_json = ?, confirmation_json = '' WHERE profile_id = ?",
                (json.dumps(snapshot, ensure_ascii=True), profile.id),
            )
            self._insert_audit(
                connection,
                profile.organization_id,
                None,
                "client_profile.masters_synced",
                {
                    "client_profile_id": profile.id,
                    "company_guid": body.company.guid,
                    "counts": {kind: len(rows) for kind, rows in body.masters.items()},
                },
            )
        return {
            "success": True,
            "message": "Master snapshot saved. Review and confirm mappings in Client profiles.",
            "synced_at": now.isoformat(),
        }

    def _master_view(self, connection, profile):
        row = connection.execute(
            "SELECT * FROM tally_master_sync WHERE profile_id = ?", (profile.id,)
        ).fetchone()
        snapshot = (
            json.loads(row["snapshot_json"]) if row and row["snapshot_json"] else None
        )
        confirmation = (
            json.loads(row["confirmation_json"])
            if row and row["confirmation_json"]
            else None
        )
        matches = bool(
            snapshot and snapshot["source_fingerprint"] == source_fingerprint(profile)
        )
        fresh = bool(
            matches
            and datetime.now(timezone.utc)
            - datetime.fromisoformat(snapshot["synced_at"])
            < FRESH_FOR
        )
        fingerprint = profile_fingerprint(profile)
        confirmed = bool(
            fresh
            and confirmation
            and confirmation["profile_fingerprint"] == fingerprint
            and confirmation["snapshot_id"] == snapshot["id"]
        )
        # Old-company names must never populate current-profile selections.
        return {
            "snapshot": (
                {
                    key: value
                    for key, value in snapshot.items()
                    if key != "source_fingerprint"
                }
                if matches
                else None
            ),
            "state": "fresh" if fresh else "stale" if matches else "not_synced",
            "profile_fingerprint": fingerprint,
            "mapping_confirmed": confirmed,
            "confirmation": confirmation if confirmed else None,
            "checks": mapping_checks(profile, snapshot["masters"]) if matches else [],
        }

    def get_master_snapshot(self, profile):
        with self._connect() as connection:
            return self._master_view(connection, profile)

    def confirm_master_mappings(self, profile_id, body, actor_id):
        with self._connect() as connection:
            profile = self._locked_profile(connection, profile_id)
            if not profile:
                raise ApprovalConflict("Profile is no longer available.")
            view = self._master_view(connection, profile)
            if (
                view["state"] != "fresh"
                or view["snapshot"]["id"] != body.snapshot_id
                or view["profile_fingerprint"] != body.profile_fingerprint
                or any(not check["found"] for check in view["checks"])
            ):
                raise ApprovalConflict(
                    "Save current mappings, refresh masters, and resolve missing names before confirming."
                )
            confirmation = {
                "snapshot_id": body.snapshot_id,
                "profile_fingerprint": body.profile_fingerprint,
                "confirmed_by": actor_id,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                "UPDATE tally_master_sync SET confirmation_json = ? WHERE profile_id = ?",
                (json.dumps(confirmation), profile_id),
            )
            self._insert_audit(
                connection,
                profile.organization_id,
                None,
                "client_profile.mappings_confirmed",
                {"actor_id": actor_id, "client_profile_id": profile_id, **confirmation},
            )
        return self.get_master_snapshot(profile)
