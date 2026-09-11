"""Persistence repository for SiftEntry's SQLite and PostgreSQL backends."""

from __future__ import annotations

import json
import sqlite3

from . import db
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    Job,
    ClientProfile,
    ClientProfileCreate,
    ClientProfilePatch,
    CorrectionLearningSignal,
    Invitation,
    Invoice,
    InvoiceDocumentRetention,
    InvoiceCreate,
    InvoiceLine,
    InvoicePatch,
    InvoiceStatus,
    Membership,
    Organization,
    OrganizationCreate,
    OrganizationMember,
    OrganizationRole,
    PostingResult,
    PostingStatus,
    PostingTarget,
    User,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in value
        ]
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


@dataclass(frozen=True)
class AuthSessionRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime]
    replaced_by: Optional[str]


@dataclass(frozen=True)
class PasswordResetRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: Optional[datetime]
    created_at: datetime


@dataclass(frozen=True)
class InvoiceFileRecord:
    id: str
    organization_id: str
    invoice_id: str
    original_filename: str
    content_type: str
    storage_backend: str
    storage_key: str
    local_path: str
    sha256_hash: str
    size_bytes: int
    retention_policy: str
    retention_until: Optional[datetime]
    deleted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    def retention_model(self) -> InvoiceDocumentRetention:
        return InvoiceDocumentRetention(
            file_id=self.id,
            retained=self.deleted_at is None,
            retention_policy=self.retention_policy,
            retention_until=self.retention_until,
            deleted_at=self.deleted_at,
            sha256_hash=self.sha256_hash,
            size_bytes=self.size_bytes,
            storage_backend=self.storage_backend,
        )


class InvoiceRepository:
    def __init__(self, database_path: Path, database_url: str = ""):
        self.database_path = Path(database_path)
        self.database_url = (database_url or "").strip()
        if not db.is_postgres_url(self.database_url):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            db.create_database_if_missing(self.database_url)
        self._schema_lock = threading.Lock()
        self.initialize()

    def _connect(self):
        return db.connect(self.database_url, self.database_path)

    def initialize(self) -> None:
        with self._schema_lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    legal_names_json TEXT NOT NULL,
                    default_currency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    actor_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS jobs_status_created_idx
                ON jobs(status, created_at);

                CREATE TABLE IF NOT EXISTS organization_settings (
                    organization_id TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS organization_memberships (
                    user_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, organization_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memberships_organization
                ON organization_memberships(organization_id, role);

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    replaced_by TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
                ON auth_sessions(user_id, expires_at DESC);

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
                ON password_reset_tokens(user_id, expires_at DESC);

                CREATE TABLE IF NOT EXISTS organization_invitations (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE,
                    role TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    invited_by TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    accepted_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (invited_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    parser TEXT NOT NULL,
                    extraction_engine TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    invoice_number TEXT NOT NULL,
                    invoice_date TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    purchase_order TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    tax_total REAL NOT NULL,
                    total REAL NOT NULL,
                    supplier_json TEXT NOT NULL,
                    customer_json TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL,
                    evidence_json TEXT NOT NULL,
                    validation_issues_json TEXT NOT NULL,
                    raw_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_org_supplier_number
                ON invoices(organization_id, invoice_number, source_file);

                CREATE INDEX IF NOT EXISTS idx_invoice_org_status
                ON invoices(organization_id, status, created_at DESC);

                CREATE TABLE IF NOT EXISTS invoice_files (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    invoice_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    storage_key TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    retention_policy TEXT NOT NULL,
                    retention_until TEXT,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_invoice_files_invoice_active
                ON invoice_files(invoice_id, deleted_at, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_invoice_files_org_retention
                ON invoice_files(organization_id, retention_until, deleted_at);

                CREATE TABLE IF NOT EXISTS invoice_lines (
                    id TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    uom TEXT NOT NULL,
                    unit_price REAL NOT NULL,
                    net_amount REAL NOT NULL,
                    tax_amount REAL NOT NULL,
                    total_amount REAL NOT NULL,
                    hsn_sac TEXT NOT NULL,
                    category TEXT NOT NULL,
                    gl_code TEXT NOT NULL,
                    confidence REAL,
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    invoice_id TEXT NOT NULL,
                    field_path TEXT NOT NULL,
                    old_value_json TEXT NOT NULL,
                    new_value_json TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS supplier_formats (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    supplier_key TEXT NOT NULL,
                    supplier_name TEXT NOT NULL,
                    supplier_tax_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'training',
                    samples_count INTEGER NOT NULL DEFAULT 0,
                    clean_streak INTEGER NOT NULL DEFAULT 0,
                    hints_json TEXT NOT NULL DEFAULT '{}',
                    last_invoice_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (organization_id, supplier_key),
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                );

                CREATE TABLE IF NOT EXISTS accounting_mappings (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                );

                CREATE TABLE IF NOT EXISTS client_profiles (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    accounting_system TEXT NOT NULL,
                    description TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    settings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_client_profiles_org_name
                ON client_profiles(organization_id, name COLLATE NOCASE);

                CREATE INDEX IF NOT EXISTS idx_client_profiles_org_system
                ON client_profiles(organization_id, accounting_system, is_default);

                CREATE TABLE IF NOT EXISTS posting_attempts (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL DEFAULT '',
                    invoice_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'failed',
                    success INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    client_profile_id TEXT,
                    actor_id TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL,
                    external_id TEXT,
                    issues_json TEXT NOT NULL,
                    request_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_posting_attempts_invoice_created
                ON posting_attempts(invoice_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    invoice_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS connector_heartbeats (
                    client_profile_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    connector_host TEXT NOT NULL DEFAULT '',
                    connector_version TEXT NOT NULL DEFAULT '',
                    tally_detected INTEGER,
                    last_seen_at TEXT NOT NULL
                );
                """
            )
            if db.is_postgres_url(self.database_url):
                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS users_email_nocase_idx
                    ON users (LOWER(email))
                    """
                )
            self._migrate_posting_attempts(connection)
            # Columns must exist before creating this index on older databases.
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_attempts_active_claim
                ON posting_attempts(invoice_id, COALESCE(client_profile_id, ''), target)
                WHERE status = 'started' AND dry_run = 0
            """)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_posting_attempts_org_created
                ON posting_attempts(organization_id, created_at DESC)
                """
            )

    def _migrate_posting_attempts(self, connection: sqlite3.Connection) -> None:
        columns = db.table_columns(connection, "posting_attempts")
        required_columns = {
            "organization_id": "organization_id TEXT NOT NULL DEFAULT ''",
            "status": "status TEXT NOT NULL DEFAULT 'failed'",
            "client_profile_id": "client_profile_id TEXT",
            "actor_id": "actor_id TEXT NOT NULL DEFAULT ''",
            "request_json": "request_json TEXT NOT NULL DEFAULT '{}'",
            "response_json": "response_json TEXT NOT NULL DEFAULT '{}'",
            "updated_at": "updated_at TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in required_columns.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE posting_attempts ADD COLUMN {definition}"
                )
        connection.execute(
            """
            UPDATE posting_attempts
            SET organization_id = COALESCE(
                    NULLIF(organization_id, ''),
                    (SELECT organization_id FROM invoices WHERE invoices.id = posting_attempts.invoice_id),
                    ''
                ),
                status = CASE WHEN success = 1 THEN 'succeeded' ELSE 'failed' END,
                response_json = CASE
                    WHEN response_json = '' OR response_json = '{}' THEN raw_json
                    ELSE response_json
                END,
                updated_at = CASE
                    WHEN updated_at = '' THEN created_at
                    ELSE updated_at
                END
            WHERE organization_id = ''
               OR updated_at = ''
               OR response_json = ''
               OR status NOT IN ('started', 'succeeded', 'failed')
            """
        )

    def count_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"] if row else 0)

    def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: str = "",
    ) -> User:
        now = utc_now()
        user_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, email, password_hash, full_name, is_active,
                    created_at, updated_at, last_login_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
                """,
                (
                    user_id,
                    email.strip().lower(),
                    password_hash,
                    full_name.strip(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        user = self.get_user(user_id)
        if not user:
            raise RuntimeError("User creation failed.")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._user_from_row(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email.strip().lower(),),
            ).fetchone()
        return self._user_from_row(row) if row else None

    def get_password_hash(self, user_id: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return str(row["password_hash"]) if row else None

    def update_password_hash(self, user_id: str, password_hash: str) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, now, user_id),
            )

    def mark_user_login(self, user_id: str) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now, now, user_id),
            )

    def create_membership(
        self,
        user_id: str,
        organization_id: str,
        role: OrganizationRole,
    ) -> Membership:
        now = utc_now()
        role_value = role.value if isinstance(role, OrganizationRole) else str(role)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO organization_memberships (
                    user_id, organization_id, role, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, organization_id)
                DO UPDATE SET role = excluded.role, updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    organization_id,
                    role_value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        membership = self.get_membership(user_id, organization_id)
        if not membership:
            raise RuntimeError("Membership creation failed.")
        return membership

    def get_membership(
        self,
        user_id: str,
        organization_id: str,
    ) -> Optional[Membership]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT m.*, o.name AS organization_name
                FROM organization_memberships m
                JOIN organizations o ON o.id = m.organization_id
                WHERE m.user_id = ? AND m.organization_id = ?
                """,
                (user_id, organization_id),
            ).fetchone()
        return self._membership_from_row(row) if row else None

    def list_memberships(self, user_id: str) -> List[Membership]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, o.name AS organization_name
                FROM organization_memberships m
                JOIN organizations o ON o.id = m.organization_id
                WHERE m.user_id = ?
                ORDER BY o.name COLLATE NOCASE
                """,
                (user_id,),
            ).fetchall()
        return [self._membership_from_row(row) for row in rows]

    def delete_membership(self, user_id: str, organization_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM organization_memberships
                WHERE user_id = ? AND organization_id = ?
                """,
                (user_id, organization_id),
            )

    def list_organization_members(
        self,
        organization_id: str,
    ) -> List[OrganizationMember]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.email,
                    u.full_name,
                    u.is_active,
                    u.last_login_at,
                    m.role,
                    m.created_at AS member_since
                FROM organization_memberships m
                JOIN users u ON u.id = m.user_id
                WHERE m.organization_id = ?
                ORDER BY
                    CASE m.role
                        WHEN 'owner' THEN 1
                        WHEN 'admin' THEN 2
                        WHEN 'accountant' THEN 3
                        WHEN 'approver' THEN 4
                        ELSE 5
                    END,
                    u.email COLLATE NOCASE
                """,
                (organization_id,),
            ).fetchall()
        return [self._organization_member_from_row(row) for row in rows]

    def list_organizations_for_user(self, user_id: str) -> List[Organization]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT o.*
                FROM organizations o
                JOIN organization_memberships m ON m.organization_id = o.id
                WHERE m.user_id = ?
                ORDER BY o.name COLLATE NOCASE
                """,
                (user_id,),
            ).fetchall()
        return [self._organization_from_row(row) for row in rows]

    def create_auth_session(
        self,
        session_id: str,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> AuthSessionRecord:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (
                    id, user_id, token_hash, expires_at, created_at,
                    revoked_at, replaced_by
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    session_id,
                    user_id,
                    token_hash,
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
        session = self.get_auth_session(session_id)
        if not session:
            raise RuntimeError("Authentication session creation failed.")
        return session

    def get_auth_session(self, session_id: str) -> Optional[AuthSessionRecord]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._auth_session_from_row(row) if row else None

    def revoke_auth_session(
        self,
        session_id: str,
        replaced_by: Optional[str] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = COALESCE(revoked_at, ?), replaced_by = COALESCE(?, replaced_by)
                WHERE id = ?
                """,
                (utc_now().isoformat(), replaced_by, session_id),
            )

    def revoke_auth_sessions_for_user(self, user_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (utc_now().isoformat(), user_id),
            )
            return int(cursor.rowcount)

    def create_password_reset(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetRecord:
        reset_id = str(uuid.uuid4())
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO password_reset_tokens (
                    id, user_id, token_hash, expires_at, used_at, created_at
                ) VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (
                    reset_id,
                    user_id,
                    token_hash,
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
        reset = self.get_password_reset_by_hash(token_hash)
        if not reset:
            raise RuntimeError("Password reset token creation failed.")
        return reset

    def get_password_reset_by_hash(
        self,
        token_hash: str,
    ) -> Optional[PasswordResetRecord]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM password_reset_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return self._password_reset_from_row(row) if row else None

    def mark_password_reset_used(self, reset_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = COALESCE(used_at, ?)
                WHERE id = ?
                """,
                (utc_now().isoformat(), reset_id),
            )

    def create_invitation(
        self,
        organization_id: str,
        email: str,
        role: OrganizationRole,
        token_hash: str,
        invited_by: str,
        expires_at: datetime,
    ) -> Invitation:
        invitation_id = str(uuid.uuid4())
        created_at = utc_now()
        role_value = role.value if isinstance(role, OrganizationRole) else str(role)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO organization_invitations (
                    id, organization_id, email, role, token_hash, invited_by,
                    expires_at, accepted_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    invitation_id,
                    organization_id,
                    email.strip().lower(),
                    role_value,
                    token_hash,
                    invited_by,
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
        invitation = self.get_invitation_by_hash(token_hash)
        if not invitation:
            raise RuntimeError("Invitation creation failed.")
        return invitation

    def get_invitation_by_hash(self, token_hash: str) -> Optional[Invitation]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM organization_invitations WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return self._invitation_from_row(row) if row else None

    def list_organization_invitations(
        self,
        organization_id: str,
        include_accepted: bool = False,
    ) -> List[Invitation]:
        accepted_filter = "" if include_accepted else "AND accepted_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM organization_invitations
                WHERE organization_id = ?
                {accepted_filter}
                ORDER BY created_at DESC
                """,
                (organization_id,),
            ).fetchall()
        return [self._invitation_from_row(row) for row in rows]

    def accept_invitation(self, invitation_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE organization_invitations
                SET accepted_at = COALESCE(accepted_at, ?)
                WHERE id = ?
                """,
                (utc_now().isoformat(), invitation_id),
            )

    def create_organization(self, data: OrganizationCreate) -> Organization:
        now = utc_now()
        organization = Organization(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO organizations
                (id, name, legal_names_json, default_currency, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    organization.id,
                    organization.name,
                    _json(organization.legal_names),
                    organization.default_currency,
                    organization.created_at.isoformat(),
                    organization.updated_at.isoformat(),
                ),
            )
        return organization

    def list_organizations(self) -> List[Organization]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM organizations ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._organization_from_row(row) for row in rows]

    def list_correction_learning_signals(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> List[CorrectionLearningSignal]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.*,
                    i.invoice_number,
                    i.supplier_json,
                    u.email AS actor_email
                FROM corrections c
                JOIN invoices i ON i.id = c.invoice_id
                LEFT JOIN users u ON u.id = c.actor_id
                WHERE c.organization_id = ?
                ORDER BY c.created_at DESC
                LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        return [self._correction_learning_from_row(row) for row in rows]

    def get_organization(self, organization_id: str) -> Optional[Organization]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM organizations WHERE id = ?", (organization_id,)
            ).fetchone()
        return self._organization_from_row(row) if row else None

    def get_organization_by_name(self, name: str) -> Optional[Organization]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM organizations WHERE name = ? COLLATE NOCASE",
                (name.strip(),),
            ).fetchone()
        return self._organization_from_row(row) if row else None

    def set_organization_default_currency(
        self,
        organization_id: str,
        currency: str,
    ) -> Optional[Organization]:
        organization = self.get_organization(organization_id)
        if organization is None:
            return None
        normalized = (currency or "USD").strip().upper()
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE organizations
                SET default_currency = ?, updated_at = ?
                WHERE id = ?
                """,
                (normalized, now.isoformat(), organization_id),
            )
            self._insert_audit(
                connection,
                organization_id,
                None,
                "organization.default_currency_updated",
                {"default_currency": normalized},
            )
        return self.get_organization(organization_id)

    def _organization_from_row(self, row: sqlite3.Row) -> Organization:
        return Organization(
            id=row["id"],
            name=row["name"],
            legal_names=_loads(row["legal_names_json"], []),
            default_currency=row["default_currency"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_client_profile(
        self,
        organization_id: str,
        data: ClientProfileCreate,
        actor_id: str = "api-user",
    ) -> ClientProfile:
        now = utc_now()
        profile = ClientProfile(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )
        accounting_system = _enum_value(profile.accounting_system)
        with self._connect() as connection:
            if profile.is_default:
                connection.execute(
                    """
                    UPDATE client_profiles
                    SET is_default = 0, updated_at = ?
                    WHERE organization_id = ? AND accounting_system = ?
                    """,
                    (now.isoformat(), organization_id, accounting_system),
                )
            connection.execute(
                """
                INSERT INTO client_profiles (
                    id, organization_id, name, accounting_system, description,
                    is_default, settings_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.organization_id,
                    profile.name,
                    accounting_system,
                    profile.description,
                    int(profile.is_default),
                    _json(profile.settings),
                    profile.created_at.isoformat(),
                    profile.updated_at.isoformat(),
                ),
            )
            self._insert_audit(
                connection,
                organization_id,
                None,
                "client_profile.created",
                {
                    "actor_id": actor_id,
                    "profile_id": profile.id,
                    "name": profile.name,
                    "accounting_system": accounting_system,
                    "is_default": profile.is_default,
                },
            )
        created = self.get_client_profile(profile.id)
        if not created:
            raise RuntimeError("Client profile creation failed.")
        return created

    def list_client_profiles(
        self,
        organization_id: str,
        accounting_system: Optional[str] = None,
    ) -> List[ClientProfile]:
        clauses = ["organization_id = ?"]
        values: List[Any] = [organization_id]
        if accounting_system:
            clauses.append("accounting_system = ?")
            values.append(accounting_system)
        where = " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM client_profiles
                WHERE {where}
                ORDER BY is_default DESC, accounting_system, name COLLATE NOCASE
                """,
                values,
            ).fetchall()
        return [self._client_profile_from_row(row) for row in rows]

    def list_client_profiles_by_system(
        self,
        accounting_system: str,
    ) -> List[ClientProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM client_profiles
                WHERE accounting_system = ?
                ORDER BY organization_id, is_default DESC, name COLLATE NOCASE
                """,
                (accounting_system,),
            ).fetchall()
        return [self._client_profile_from_row(row) for row in rows]

    def get_client_profile(self, profile_id: str) -> Optional[ClientProfile]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM client_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return self._client_profile_from_row(row) if row else None

    def update_client_profile(
        self,
        profile_id: str,
        patch: ClientProfilePatch,
        actor_id: str = "api-user",
    ) -> Optional[ClientProfile]:
        current = self.get_client_profile(profile_id)
        if not current:
            return None

        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            return current

        merged = current.model_dump()
        merged.update(updates)
        merged["updated_at"] = utc_now()
        updated = ClientProfile.model_validate(merged)
        accounting_system = _enum_value(updated.accounting_system)

        with self._connect() as connection:
            if updated.is_default:
                connection.execute(
                    """
                    UPDATE client_profiles
                    SET is_default = 0, updated_at = ?
                    WHERE organization_id = ? AND accounting_system = ? AND id != ?
                    """,
                    (
                        updated.updated_at.isoformat(),
                        updated.organization_id,
                        accounting_system,
                        profile_id,
                    ),
                )
            connection.execute(
                """
                UPDATE client_profiles
                SET name = ?, accounting_system = ?, description = ?,
                    is_default = ?, settings_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.name,
                    accounting_system,
                    updated.description,
                    int(updated.is_default),
                    _json(updated.settings),
                    updated.updated_at.isoformat(),
                    profile_id,
                ),
            )
            self._insert_audit(
                connection,
                updated.organization_id,
                None,
                "client_profile.updated",
                {
                    "actor_id": actor_id,
                    "profile_id": profile_id,
                    "fields": list(updates),
                },
            )
        return self.get_client_profile(profile_id)

    def set_default_client_profile(
        self,
        profile_id: str,
        actor_id: str = "api-user",
    ) -> Optional[ClientProfile]:
        profile = self.get_client_profile(profile_id)
        if not profile:
            return None

        now = utc_now()
        accounting_system = _enum_value(profile.accounting_system)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE client_profiles
                SET is_default = 0, updated_at = ?
                WHERE organization_id = ? AND accounting_system = ?
                """,
                (now.isoformat(), profile.organization_id, accounting_system),
            )
            connection.execute(
                """
                UPDATE client_profiles
                SET is_default = 1, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), profile_id),
            )
            self._insert_audit(
                connection,
                profile.organization_id,
                None,
                "client_profile.default_set",
                {
                    "actor_id": actor_id,
                    "profile_id": profile_id,
                    "accounting_system": accounting_system,
                },
            )
        return self.get_client_profile(profile_id)

    def delete_client_profile(
        self,
        profile_id: str,
        actor_id: str = "api-user",
    ) -> bool:
        profile = self.get_client_profile(profile_id)
        if not profile:
            return False

        with self._connect() as connection:
            connection.execute("DELETE FROM client_profiles WHERE id = ?", (profile_id,))
            self._insert_audit(
                connection,
                profile.organization_id,
                None,
                "client_profile.deleted",
                {
                    "actor_id": actor_id,
                    "profile_id": profile_id,
                    "name": profile.name,
                    "accounting_system": _enum_value(profile.accounting_system),
                },
            )
        return True

    def _client_profile_from_row(self, row: sqlite3.Row) -> ClientProfile:
        return ClientProfile(
            id=row["id"],
            organization_id=row["organization_id"],
            name=row["name"],
            accounting_system=row["accounting_system"],
            description=row["description"],
            is_default=bool(row["is_default"]),
            settings=_loads(row["settings_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _user_from_row(self, row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_login_at=(
                datetime.fromisoformat(row["last_login_at"])
                if row["last_login_at"]
                else None
            ),
        )

    def _membership_from_row(self, row: sqlite3.Row) -> Membership:
        return Membership(
            organization_id=row["organization_id"],
            organization_name=row["organization_name"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _organization_member_from_row(
        self,
        row: sqlite3.Row,
    ) -> OrganizationMember:
        return OrganizationMember(
            user_id=row["user_id"],
            email=row["email"],
            full_name=row["full_name"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            member_since=datetime.fromisoformat(row["member_since"]),
            last_login_at=(
                datetime.fromisoformat(row["last_login_at"])
                if row["last_login_at"]
                else None
            ),
        )

    def _auth_session_from_row(self, row: sqlite3.Row) -> AuthSessionRecord:
        return AuthSessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            revoked_at=(
                datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None
            ),
            replaced_by=row["replaced_by"],
        )

    def _password_reset_from_row(self, row: sqlite3.Row) -> PasswordResetRecord:
        return PasswordResetRecord(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _invitation_from_row(self, row: sqlite3.Row) -> Invitation:
        return Invitation(
            id=row["id"],
            organization_id=row["organization_id"],
            email=row["email"],
            role=row["role"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            accepted_at=(
                datetime.fromisoformat(row["accepted_at"]) if row["accepted_at"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _correction_learning_from_row(
        self,
        row: sqlite3.Row,
    ) -> CorrectionLearningSignal:
        supplier = _loads(row["supplier_json"], {})
        supplier_name = supplier.get("name") if isinstance(supplier, dict) else ""
        return CorrectionLearningSignal(
            id=row["id"],
            invoice_id=row["invoice_id"],
            invoice_number=row["invoice_number"] or "Untitled invoice",
            supplier_name=supplier_name or "Unknown supplier",
            field_path=row["field_path"],
            old_value=_loads(row["old_value_json"], None),
            new_value=_loads(row["new_value_json"], None),
            actor_id=row["actor_id"],
            actor_email=row["actor_email"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_invoice(self, data: InvoiceCreate) -> Invoice:
        now = utc_now()
        invoice_id = str(uuid.uuid4())
        invoice = Invoice(
            id=invoice_id,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invoices (
                    id, organization_id, source_file, source_path, parser,
                    extraction_engine, page_count, status, invoice_number,
                    invoice_date, due_date, purchase_order, currency, subtotal,
                    tax_total, total, supplier_json, customer_json, direction,
                    confidence, evidence_json, validation_issues_json,
                    raw_payload_json, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                self._invoice_values(invoice),
            )
            self._replace_lines(connection, invoice_id, invoice.lines)
            self._insert_audit(
                connection,
                invoice.organization_id,
                invoice_id,
                "invoice.created",
                {"source_file": invoice.source_file, "parser": invoice.parser},
            )
        return self.get_invoice(invoice_id) or invoice

    def list_invoices(
        self,
        organization_id: Optional[str] = None,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Invoice]:
        clauses: List[str] = []
        values: List[Any] = []
        if organization_id:
            clauses.append("organization_id = ?")
            values.append(organization_id)
        if status:
            clauses.append("status = ?")
            values.append(status.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM invoices{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                values,
            ).fetchall()
            return [self._invoice_from_row(connection, row) for row in rows]

    def list_connector_ready_invoices(
        self,
        organization_id: str,
        client_profile_id: str,
        target: PostingTarget,
        limit: int = 5,
    ) -> List[Invoice]:
        # Validation says an invoice is ready; approval authorizes sending it.
        # Only approved invoices are ever offered to a connector.
        ready_statuses = (
            InvoiceStatus.APPROVED.value,
            InvoiceStatus.APPROVED.value,
        )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT invoice_rows.*
                FROM invoices AS invoice_rows
                WHERE invoice_rows.organization_id = ?
                  AND invoice_rows.status IN (?, ?)
                  AND NOT EXISTS (
                      SELECT 1
                      FROM posting_attempts AS posting_rows
                      WHERE posting_rows.invoice_id = invoice_rows.id
                        AND posting_rows.client_profile_id = ?
                        AND posting_rows.target = ?
                        AND posting_rows.status IN ('started', 'succeeded')
                        AND posting_rows.dry_run = 0
                  )
                ORDER BY invoice_rows.updated_at ASC, invoice_rows.created_at ASC
                LIMIT ?
                """,
                (
                    organization_id,
                    ready_statuses[0],
                    ready_statuses[1],
                    client_profile_id,
                    _enum_value(target),
                    limit,
                ),
            ).fetchall()
            return [self._invoice_from_row(connection, row) for row in rows]

    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            return self._invoice_from_row(connection, row) if row else None

    def delete_organization_invoices(self, organization_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM invoices WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
            deleted = int(row["count"] if row else 0)
            connection.execute(
                "DELETE FROM invoices WHERE organization_id = ?",
                (organization_id,),
            )
            self._insert_audit(
                connection,
                organization_id,
                None,
                "invoice.queue_cleared",
                {"deleted": deleted},
            )
        return deleted

    def delete_seeded_demo_invoices(self, organization_id: str) -> int:
        """Remove only invoices carrying SiftEntry's explicit demo marker."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_path, raw_payload_json
                FROM invoices
                WHERE organization_id = ?
                  AND source_path LIKE ?
                """,
                (organization_id, "synthetic-demo/%"),
            ).fetchall()
            invoice_ids = []
            for row in rows:
                payload = _loads(row["raw_payload_json"], {})
                if (
                    payload.get("demo") is True
                    and payload.get("demo_seed_version") == 1
                ):
                    invoice_ids.append(str(row["id"]))

            for invoice_id in invoice_ids:
                connection.execute(
                    "DELETE FROM invoices WHERE id = ? AND organization_id = ?",
                    (invoice_id, organization_id),
                )
            if invoice_ids:
                self._insert_audit(
                    connection,
                    organization_id,
                    None,
                    "demo.seed_removed",
                    {"deleted": len(invoice_ids)},
                )
        return len(invoice_ids)

    def create_invoice_file(
        self,
        *,
        organization_id: str,
        invoice_id: str,
        original_filename: str,
        content_type: str,
        storage_backend: str,
        storage_key: str,
        local_path: str,
        sha256_hash: str,
        size_bytes: int,
        retention_policy: str,
        retention_until: Optional[datetime],
    ) -> InvoiceFileRecord:
        now = utc_now()
        file_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invoice_files (
                    id, organization_id, invoice_id, original_filename,
                    content_type, storage_backend, storage_key, local_path,
                    sha256_hash, size_bytes, retention_policy, retention_until,
                    deleted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    file_id,
                    organization_id,
                    invoice_id,
                    original_filename,
                    content_type,
                    storage_backend,
                    storage_key,
                    local_path,
                    sha256_hash,
                    size_bytes,
                    retention_policy,
                    retention_until.isoformat() if retention_until else None,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._insert_audit(
                connection,
                organization_id,
                invoice_id,
                "invoice.file_retained",
                {
                    "file_id": file_id,
                    "sha256_hash": sha256_hash,
                    "size_bytes": size_bytes,
                    "retention_policy": retention_policy,
                    "retention_until": (
                        retention_until.isoformat() if retention_until else None
                    ),
                },
            )
            row = connection.execute(
                "SELECT * FROM invoice_files WHERE id = ?",
                (file_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Invoice file metadata creation failed.")
        return self._invoice_file_from_row(row)

    def get_active_invoice_file(self, invoice_id: str) -> Optional[InvoiceFileRecord]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM invoice_files
                WHERE invoice_id = ?
                  AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (invoice_id,),
            ).fetchone()
        return self._invoice_file_from_row(row) if row else None

    def get_latest_invoice_file(self, invoice_id: str) -> Optional[InvoiceFileRecord]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM invoice_files
                WHERE invoice_id = ?
                ORDER BY deleted_at IS NULL DESC, created_at DESC
                LIMIT 1
                """,
                (invoice_id,),
            ).fetchone()
        return self._invoice_file_from_row(row) if row else None

    def list_organization_invoice_files(
        self,
        organization_id: str,
        include_deleted: bool = False,
    ) -> List[InvoiceFileRecord]:
        where_deleted = "" if include_deleted else " AND deleted_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM invoice_files
                WHERE organization_id = ?
                {where_deleted}
                ORDER BY created_at DESC
                """,
                (organization_id,),
            ).fetchall()
        return [self._invoice_file_from_row(row) for row in rows]

    def list_expired_invoice_files(
        self,
        *,
        now: datetime,
        organization_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[InvoiceFileRecord]:
        clauses = [
            "deleted_at IS NULL",
            "retention_until IS NOT NULL",
            "retention_until <= ?",
        ]
        values: List[Any] = [now.isoformat()]
        if organization_id:
            clauses.append("organization_id = ?")
            values.append(organization_id)
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM invoice_files
                WHERE {" AND ".join(clauses)}
                ORDER BY retention_until ASC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [self._invoice_file_from_row(row) for row in rows]

    def mark_invoice_file_deleted(
        self,
        file_id: str,
        deleted_at: Optional[datetime] = None,
    ) -> Optional[InvoiceFileRecord]:
        now = deleted_at or utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM invoice_files WHERE id = ?",
                (file_id,),
            ).fetchone()
            if row is None:
                return None
            record = self._invoice_file_from_row(row)
            connection.execute(
                """
                UPDATE invoice_files
                SET deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), now.isoformat(), file_id),
            )
            connection.execute(
                """
                UPDATE invoices
                SET source_path = '', updated_at = ?
                WHERE id = ?
                  AND source_path = ?
                """,
                (now.isoformat(), record.invoice_id, record.local_path),
            )
            self._insert_audit(
                connection,
                record.organization_id,
                record.invoice_id,
                "invoice.file_deleted",
                {
                    "file_id": file_id,
                    "retention_policy": record.retention_policy,
                    "retention_until": (
                        record.retention_until.isoformat()
                        if record.retention_until
                        else None
                    ),
                },
            )
            updated = connection.execute(
                "SELECT * FROM invoice_files WHERE id = ?",
                (file_id,),
            ).fetchone()
        return self._invoice_file_from_row(updated) if updated else None

    def patch_invoice(
        self,
        invoice_id: str,
        patch: InvoicePatch,
        actor_id: str = "api-user",
    ) -> Optional[Invoice]:
        current = self.get_invoice(invoice_id)
        if not current:
            return None

        updates = patch.model_dump(exclude_unset=True)
        learn_vendor_memory = updates.pop("learn_vendor_memory", None)
        learn = True if learn_vendor_memory is None else bool(learn_vendor_memory)
        if not updates:
            return current

        old_values = {
            key: getattr(current, key).model_dump(mode="json")
            if hasattr(getattr(current, key), "model_dump")
            else getattr(current, key)
            for key in updates
        }
        merged = current.model_dump()
        merged.update(updates)
        merged["updated_at"] = utc_now()
        merged["status"] = InvoiceStatus.EXTRACTED
        merged["validation_issues"] = []
        updated = Invoice.model_validate(merged)

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE invoices SET
                    status = ?, invoice_number = ?, invoice_date = ?,
                    due_date = ?, purchase_order = ?, currency = ?,
                    subtotal = ?, tax_total = ?, total = ?, supplier_json = ?,
                    customer_json = ?, direction = ?, validation_issues_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    InvoiceStatus.EXTRACTED.value,
                    updated.invoice_number,
                    updated.invoice_date,
                    updated.due_date,
                    updated.purchase_order,
                    updated.currency,
                    updated.subtotal,
                    updated.tax_total,
                    updated.total,
                    _json(updated.supplier),
                    _json(updated.customer),
                    updated.direction,
                    _json([]),
                    updated.updated_at.isoformat(),
                    invoice_id,
                ),
            )
            if "lines" in updates:
                self._replace_lines(connection, invoice_id, updated.lines)
            if learn:
                # Vendor-memory learning is opt-out via learn_vendor_memory=False
                # on the PATCH body (Review Workspace toggle).
                for field_path, new_value in updates.items():
                    self._insert_correction(
                        connection,
                        updated.organization_id,
                        invoice_id,
                        field_path,
                        old_values[field_path],
                        new_value,
                        actor_id,
                    )
            self._insert_audit(
                connection,
                updated.organization_id,
                invoice_id,
                "invoice.corrected",
                {"fields": list(updates)},
            )
        return self.get_invoice(invoice_id)

    def enqueue_job(
        self,
        organization_id: str,
        kind: str,
        payload: Dict[str, Any],
        actor_id: str = "api-user",
    ) -> "Job":
        job = Job(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            kind=kind,
            payload=payload,
            status="queued",
            attempts=0,
            result={},
            error="",
            actor_id=actor_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, organization_id, kind, payload_json, status, attempts,
                    result_json, error, actor_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.organization_id,
                    job.kind,
                    _json(job.payload),
                    job.status,
                    job.attempts,
                    _json(job.result),
                    job.error,
                    job.actor_id,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        return job

    def claim_next_job(self) -> Optional["Job"]:
        """Atomically claim the oldest queued job (safe for multiple workers)."""
        skip_locked = (
            " FOR UPDATE SKIP LOCKED" if db.is_postgres_url(self.database_url) else ""
        )
        with self._connect() as connection:
            row = connection.execute(
                f"""
                UPDATE jobs SET status = 'running',
                    attempts = attempts + 1, updated_at = ?
                WHERE id = (
                    SELECT id FROM jobs WHERE status = 'queued'
                    ORDER BY created_at LIMIT 1{skip_locked}
                ) AND status = 'queued'
                RETURNING *
                """,
                (utc_now().isoformat(),),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def finish_job(
        self,
        job_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
    ) -> Optional["Job"]:
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE jobs SET status = ?, result_json = ?, error = ?, updated_at = ?
                WHERE id = ?
                RETURNING *
                """,
                (
                    "failed" if error else "done",
                    _json(result or {}),
                    error,
                    utc_now().isoformat(),
                    job_id,
                ),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def get_job(self, job_id: str) -> Optional["Job"]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self, organization_id: str, limit: int = 50) -> List["Job"]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs WHERE organization_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def _job_from_row(self, row) -> "Job":
        return Job(
            id=row["id"],
            organization_id=row["organization_id"],
            kind=row["kind"],
            payload=_loads(row["payload_json"], {}),
            status=row["status"],
            attempts=int(row["attempts"]),
            result=_loads(row["result_json"], {}),
            error=row["error"],
            actor_id=row["actor_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_organization_settings(self, organization_id: str) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT settings_json FROM organization_settings
                WHERE organization_id = ?
                """,
                (organization_id,),
            ).fetchone()
        if not row:
            return {}
        loaded = _loads(row["settings_json"], {})
        return loaded if isinstance(loaded, dict) else {}

    def upsert_organization_settings(
        self,
        organization_id: str,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO organization_settings (organization_id, settings_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(organization_id) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = excluded.updated_at
                """,
                (organization_id, _json(settings), utc_now().isoformat()),
            )
        return settings

    def update_validation(
        self,
        invoice_id: str,
        status: InvoiceStatus,
        issues: List[str],
    ) -> Optional[Invoice]:
        current = self.get_invoice(invoice_id)
        if not current:
            return None
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE invoices
                SET status = ?, validation_issues_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, _json(issues), now.isoformat(), invoice_id),
            )
            self._insert_audit(
                connection,
                current.organization_id,
                invoice_id,
                "invoice.validated",
                {"status": status.value, "issues": issues},
            )
        return self.get_invoice(invoice_id)

    def set_status(self, invoice_id: str, status: InvoiceStatus) -> Optional[Invoice]:
        current = self.get_invoice(invoice_id)
        if not current:
            return None
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE invoices SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), invoice_id),
            )
            self._insert_audit(
                connection,
                current.organization_id,
                invoice_id,
                f"invoice.{status.value}",
                {"status": status.value},
            )
        return self.get_invoice(invoice_id)

    def create_posting(
        self,
        invoice_id: str,
        target: PostingTarget,
        success: bool,
        dry_run: bool,
        message: str,
        external_id: Optional[str] = None,
        issues: Optional[List[Dict[str, Any]]] = None,
        raw: Optional[Dict[str, Any]] = None,
        actor_id: str = "api-user",
        client_profile_id: Optional[str] = None,
        request_payload: Optional[Dict[str, Any]] = None,
        response_payload: Optional[Dict[str, Any]] = None,
    ) -> PostingResult:
        current = self.get_invoice(invoice_id)
        if not current:
            raise ValueError("Invoice does not exist.")
        status = PostingStatus.SUCCEEDED if success else PostingStatus.FAILED
        now = utc_now()
        posting = PostingResult(
            id=str(uuid.uuid4()),
            organization_id=current.organization_id,
            invoice_id=invoice_id,
            target=target,
            status=status,
            success=success,
            dry_run=dry_run,
            client_profile_id=client_profile_id,
            actor_id=actor_id,
            message=message,
            external_id=external_id,
            issues=issues or [],
            request_payload=request_payload or {
                "target": _enum_value(target),
                "dry_run": dry_run,
                "client_profile_id": client_profile_id,
            },
            response_payload=response_payload or raw or {},
            raw=raw or {},
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO posting_attempts (
                    id, organization_id, invoice_id, target, status, success,
                    dry_run, client_profile_id, actor_id, message, external_id,
                    issues_json, request_json, response_json, raw_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.id,
                    posting.organization_id,
                    posting.invoice_id,
                    _enum_value(posting.target),
                    _enum_value(posting.status),
                    int(posting.success),
                    int(posting.dry_run),
                    posting.client_profile_id,
                    posting.actor_id,
                    posting.message,
                    posting.external_id,
                    _json(posting.issues),
                    _json(posting.request_payload),
                    _json(posting.response_payload),
                    _json(posting.raw),
                    posting.created_at.isoformat(),
                    posting.updated_at.isoformat(),
                ),
            )
            self._insert_audit(
                connection,
                current.organization_id,
                invoice_id,
                "posting.completed" if success else "posting.failed",
                {
                    "posting_id": posting.id,
                    "target": str(posting.target),
                    "dry_run": dry_run,
                    "message": message,
                },
            )
        return posting

    def start_posting(
        self,
        invoice_id: str,
        target: PostingTarget,
        dry_run: bool,
        actor_id: str,
        client_profile_id: Optional[str] = None,
        request_payload: Optional[Dict[str, Any]] = None,
        require_approval: bool = False,
    ) -> Optional[PostingResult]:
        current = self.get_invoice(invoice_id)
        if not current:
            raise ValueError("Invoice does not exist.")
        now = utc_now()
        posting = PostingResult(
            id=str(uuid.uuid4()),
            organization_id=current.organization_id,
            invoice_id=invoice_id,
            target=target,
            status=PostingStatus.STARTED,
            success=False,
            dry_run=dry_run,
            client_profile_id=client_profile_id,
            actor_id=actor_id,
            message="Posting started.",
            external_id=None,
            issues=[],
            request_payload=request_payload or {
                "target": _enum_value(target),
                "dry_run": dry_run,
                "client_profile_id": client_profile_id,
            },
            response_payload={},
            raw={},
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            if require_approval and not dry_run:
                cursor = connection.execute(
                    """UPDATE invoices SET status = ?, updated_at = ?
                    WHERE id = ? AND status = ? AND NOT EXISTS (
                        SELECT 1 FROM posting_attempts
                        WHERE invoice_id = ? AND dry_run = 0
                          AND (status = 'started' OR (status = 'succeeded' AND target = ?))
                    )""",
                    (InvoiceStatus.POSTING.value, now.isoformat(), invoice_id,
                     InvoiceStatus.APPROVED.value, invoice_id, _enum_value(target)),
                )
                if cursor.rowcount != 1:
                    return None
            connection.execute(
                """
                INSERT INTO posting_attempts (
                    id, organization_id, invoice_id, target, status, success,
                    dry_run, client_profile_id, actor_id, message, external_id,
                    issues_json, request_json, response_json, raw_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.id,
                    posting.organization_id,
                    posting.invoice_id,
                    _enum_value(posting.target),
                    _enum_value(posting.status),
                    int(posting.success),
                    int(posting.dry_run),
                    posting.client_profile_id,
                    posting.actor_id,
                    posting.message,
                    posting.external_id,
                    _json(posting.issues),
                    _json(posting.request_payload),
                    _json(posting.response_payload),
                    _json(posting.raw),
                    posting.created_at.isoformat(),
                    posting.updated_at.isoformat(),
                ),
            )
            self._insert_audit(
                connection,
                current.organization_id,
                invoice_id,
                "posting.started",
                {
                    "posting_id": posting.id,
                    "target": _enum_value(target),
                    "dry_run": dry_run,
                    "client_profile_id": client_profile_id,
                    "actor_id": actor_id,
                },
            )
        return posting

    def complete_posting(self, posting_id: str, **kwargs) -> Optional[PostingResult]:
        """Compatibility wrapper: same idempotent semantics, returns the posting only."""
        posting, _won = self.complete_posting_atomic(posting_id, **kwargs)
        return posting

    def record_posting_conflict(self, posting_id: str, conflict: Dict[str, Any]) -> None:
        with self._connect() as connection:
            # Acquire a write lock before the read/merge on both supported engines.
            connection.execute("UPDATE posting_attempts SET id = id WHERE id = ?", (posting_id,))
            row = connection.execute(
                "SELECT raw_json FROM posting_attempts WHERE id = ?", (posting_id,)
            ).fetchone()
            raw: Dict[str, Any] = {}
            if row and row["raw_json"]:
                try:
                    raw = json.loads(row["raw_json"]) or {}
                except (TypeError, ValueError):
                    raw = {}
            conflicts = list(raw.get("late_result_conflicts") or [])
            conflicts.append(conflict)
            raw["late_result_conflicts"] = conflicts
            connection.execute(
                "UPDATE posting_attempts SET raw_json = ? WHERE id = ?",
                (json.dumps(raw), posting_id),
            )

    def _complete_posting_unchecked(
        self,
        posting_id: str,
        success: bool,
        message: str,
        external_id: Optional[str] = None,
        issues: Optional[List[Dict[str, Any]]] = None,
        raw: Optional[Dict[str, Any]] = None,
        response_payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[PostingResult], bool]:
        current = self.get_posting(posting_id)
        if not current:
            raise ValueError("Posting attempt does not exist.")
        status = PostingStatus.SUCCEEDED if success else PostingStatus.FAILED
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE posting_attempts
                SET status = ?, success = ?, message = ?, external_id = ?,
                    issues_json = ?, response_json = ?, raw_json = ?,
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    _enum_value(status),
                    int(success),
                    message,
                    external_id,
                    _json(issues or []),
                    _json(response_payload or raw or {}),
                    _json(raw or {}),
                    now.isoformat(),
                    posting_id,
                    PostingStatus.STARTED.value,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                return self.get_posting(posting_id), False
            if not current.dry_run:
                final_status = InvoiceStatus.POSTED if success else InvoiceStatus.FAILED
                connection.execute(
                    "UPDATE invoices SET status = ?, updated_at = ? WHERE id = ?",
                    (final_status.value, now.isoformat(), current.invoice_id),
                )
                self._insert_audit(connection, current.organization_id, current.invoice_id,
                                   f"invoice.{final_status.value}", {"status": final_status.value})
            self._insert_audit(
                connection,
                current.organization_id,
                current.invoice_id,
                "posting.completed" if success else "posting.failed",
                {
                    "posting_id": posting_id,
                    "target": _enum_value(current.target),
                    "dry_run": current.dry_run,
                    "client_profile_id": current.client_profile_id,
                    "message": message,
                },
            )
        updated = self.get_posting(posting_id)
        if not updated:
            raise RuntimeError("Posting completion failed.")
        return updated, True

    def complete_posting_atomic(self, posting_id: str, **kwargs):
        """Terminal transition decided by the database, not by a prior read.

        Returns (posting, won). `won` is True only for the single request whose
        conditional UPDATE (WHERE status='started') moved the row to terminal.
        Concurrent or late callers get the stored row and won=False; a
        conflicting outcome is recorded as evidence and never applied.
        """
        current = self.get_posting(posting_id)
        if not current:
            return None, False
        if current.status == PostingStatus.STARTED:
            posting, won = self._complete_posting_unchecked(posting_id, **kwargs)
            if won:
                return posting, True
            current = posting or self.get_posting(posting_id)
        if bool(current.success) != bool(kwargs.get("success")):
            self.record_posting_conflict(
                posting_id,
                {
                    "recorded_status": _enum_value(current.status),
                    "late_success": bool(kwargs.get("success")),
                    "late_message": kwargs.get("message"),
                    "late_external_id": kwargs.get("external_id"),
                    "received_at": utc_now().isoformat(),
                },
            )
            current = self.get_posting(posting_id) or current
        return current, False

    def get_posting(self, posting_id: str) -> Optional[PostingResult]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM posting_attempts WHERE id = ?", (posting_id,)
            ).fetchone()
        if not row:
            return None
        return self._posting_from_row(row)

    @staticmethod
    def supplier_format_key(name: str, tax_id: str = "") -> str:
        """Stable identity for a supplier's invoice format within an org."""
        base = (tax_id or "").strip().lower() or (name or "").strip().lower()
        return " ".join(base.split())

    TRUSTED_AFTER_CLEAN = 5

    def record_supplier_format_outcome(
        self,
        organization_id: str,
        supplier_name: str,
        supplier_tax_id: str,
        invoice_id: str,
        had_corrections: bool,
    ) -> Dict[str, Any]:
        """Update a supplier's training record after an invoice is approved.

        A clean approval (no field corrections) extends the streak; any
        correction resets it. Five consecutive clean approvals graduate the
        format from `training` to `trusted`; a correction on a trusted
        format demotes it back to training.
        """
        key = self.supplier_format_key(supplier_name, supplier_tax_id)
        if not key:
            return {}
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM supplier_formats WHERE organization_id = ? AND supplier_key = ?",
                (organization_id, key),
            ).fetchone()
            if row is None:
                record = {
                    "id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "supplier_key": key,
                    "supplier_name": supplier_name or key,
                    "supplier_tax_id": supplier_tax_id or "",
                    "status": "training",
                    "samples_count": 0,
                    "clean_streak": 0,
                    "created_at": now,
                }
            else:
                record = dict(row)
            record["samples_count"] = int(record["samples_count"]) + 1
            if had_corrections:
                record["clean_streak"] = 0
                record["status"] = "training"
            else:
                record["clean_streak"] = int(record["clean_streak"]) + 1
                if record["clean_streak"] >= self.TRUSTED_AFTER_CLEAN:
                    record["status"] = "trusted"
            record["last_invoice_id"] = invoice_id
            record["updated_at"] = now
            connection.execute(
                """
                INSERT INTO supplier_formats (
                    id, organization_id, supplier_key, supplier_name,
                    supplier_tax_id, status, samples_count, clean_streak,
                    hints_json, last_invoice_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((
                    SELECT hints_json FROM supplier_formats
                    WHERE organization_id = ? AND supplier_key = ?
                ), '{}'), ?, ?, ?)
                ON CONFLICT (organization_id, supplier_key) DO UPDATE SET
                    status = excluded.status,
                    samples_count = excluded.samples_count,
                    clean_streak = excluded.clean_streak,
                    last_invoice_id = excluded.last_invoice_id,
                    updated_at = excluded.updated_at
                """,
                (
                    record["id"],
                    organization_id,
                    key,
                    record["supplier_name"],
                    record["supplier_tax_id"],
                    record["status"],
                    record["samples_count"],
                    record["clean_streak"],
                    organization_id,
                    key,
                    record["last_invoice_id"],
                    record.get("created_at", now),
                    record["updated_at"],
                ),
            )
        return {
            "supplier_key": key,
            "status": record["status"],
            "samples_count": record["samples_count"],
            "clean_streak": record["clean_streak"],
        }

    def get_supplier_format(
        self,
        organization_id: str,
        supplier_name: str,
        supplier_tax_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """One supplier's format record, or None if the format is unseen."""
        key = self.supplier_format_key(supplier_name, supplier_tax_id)
        if not key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT supplier_key, supplier_name, supplier_tax_id, status,
                       samples_count, clean_streak, last_invoice_id, updated_at
                FROM supplier_formats
                WHERE organization_id = ? AND supplier_key = ?
                """,
                (organization_id, key),
            ).fetchone()
        return dict(row) if row else None

    def list_supplier_formats(self, organization_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT supplier_key, supplier_name, supplier_tax_id, status,
                       samples_count, clean_streak, last_invoice_id, updated_at
                FROM supplier_formats
                WHERE organization_id = ?
                ORDER BY updated_at DESC
                """,
                (organization_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_corrections_for_invoice(
        self,
        invoice_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Field corrections recorded against one invoice, oldest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, field_path, actor_id, created_at
                FROM corrections
                WHERE invoice_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (invoice_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "field_path": row["field_path"],
                "actor_id": row["actor_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_postings_for_invoice(
        self,
        invoice_id: str,
        limit: int = 20,
    ) -> List[PostingResult]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM posting_attempts
                WHERE invoice_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (invoice_id, limit),
            ).fetchall()
        return [self._posting_from_row(row) for row in rows]

    def list_postings_for_organization(
        self,
        organization_id: str,
        limit: int = 200,
    ) -> List[PostingResult]:
        """All posting attempts in one query — replaces per-invoice fan-out."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM posting_attempts
                WHERE organization_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        return [self._posting_from_row(row) for row in rows]

    def record_connector_heartbeat(
        self,
        client_profile_id: str,
        organization_id: str,
        workspace_id: str,
        connector_host: str = "",
        connector_version: str = "",
        tally_detected: Optional[bool] = None,
    ) -> datetime:
        seen_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO connector_heartbeats (
                    client_profile_id, organization_id, workspace_id,
                    connector_host, connector_version, tally_detected, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (client_profile_id) DO UPDATE SET
                    organization_id = excluded.organization_id,
                    workspace_id = excluded.workspace_id,
                    connector_host = excluded.connector_host,
                    connector_version = excluded.connector_version,
                    tally_detected = excluded.tally_detected,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    client_profile_id,
                    organization_id,
                    workspace_id,
                    connector_host,
                    connector_version,
                    None if tally_detected is None else int(bool(tally_detected)),
                    seen_at.isoformat(),
                ),
            )
        return seen_at

    def get_connector_heartbeat(
        self,
        client_profile_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM connector_heartbeats WHERE client_profile_id = ?",
                (client_profile_id,),
            ).fetchone()
        if not row:
            return None
        detected = row["tally_detected"]
        return {
            "client_profile_id": row["client_profile_id"],
            "organization_id": row["organization_id"],
            "workspace_id": row["workspace_id"],
            "connector_host": row["connector_host"],
            "connector_version": row["connector_version"],
            "tally_detected": None if detected is None else bool(detected),
            "last_seen_at": datetime.fromisoformat(row["last_seen_at"]),
        }

    def get_latest_posting_for_profile(
        self,
        client_profile_id: str,
        target: Optional[str] = None,
    ) -> Optional[PostingResult]:
        query = """
            SELECT *
            FROM posting_attempts
            WHERE client_profile_id = ?
        """
        params: List[Any] = [client_profile_id]
        if target:
            query += " AND target = ?"
            params.append(target)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return self._posting_from_row(row) if row else None

    def list_recent_postings(
        self,
        organization_id: str,
        since: datetime,
    ) -> List[PostingResult]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM posting_attempts
                WHERE organization_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (organization_id, since.isoformat()),
            ).fetchall()
        return [self._posting_from_row(row) for row in rows]

    def record_audit_event(
        self,
        organization_id: str,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
        invoice_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        """Public audit insert for events that happen outside another write."""
        with self._connect() as connection:
            self._insert_audit(
                connection,
                organization_id,
                invoice_id,
                event_type,
                details or {},
                created_at=created_at,
            )

    def get_latest_audit_event(
        self,
        organization_id: str,
        event_type: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, event_type, details_json, created_at
                FROM audit_events
                WHERE organization_id = ? AND event_type = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (organization_id, event_type),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "event_type": row["event_type"],
            "details": _loads(row["details_json"], {}),
            "created_at": datetime.fromisoformat(row["created_at"]),
        }

    def _posting_from_row(self, row: sqlite3.Row) -> PostingResult:
        created_at = datetime.fromisoformat(row["created_at"])
        updated_raw = row["updated_at"] or row["created_at"]
        return PostingResult(
            id=row["id"],
            organization_id=row["organization_id"],
            invoice_id=row["invoice_id"],
            target=row["target"],
            status=row["status"],
            success=bool(row["success"]),
            dry_run=bool(row["dry_run"]),
            client_profile_id=row["client_profile_id"],
            actor_id=row["actor_id"],
            message=row["message"],
            external_id=row["external_id"],
            issues=_loads(row["issues_json"], []),
            request_payload=_loads(row["request_json"], {}),
            response_payload=_loads(row["response_json"], {}),
            raw=_loads(row["raw_json"], {}),
            created_at=created_at,
            updated_at=datetime.fromisoformat(updated_raw),
        )

    def _invoice_values(self, invoice: Invoice) -> tuple:
        status = (
            invoice.status.value
            if isinstance(invoice.status, InvoiceStatus)
            else str(invoice.status)
        )
        return (
            invoice.id,
            invoice.organization_id,
            invoice.source_file,
            invoice.source_path,
            invoice.parser,
            invoice.extraction_engine,
            invoice.page_count,
            status,
            invoice.invoice_number,
            invoice.invoice_date,
            invoice.due_date,
            invoice.purchase_order,
            invoice.currency,
            invoice.subtotal,
            invoice.tax_total,
            invoice.total,
            _json(invoice.supplier),
            _json(invoice.customer),
            invoice.direction,
            invoice.confidence,
            _json(invoice.evidence),
            _json(invoice.validation_issues),
            _json(invoice.raw_payload),
            invoice.created_at.isoformat(),
            invoice.updated_at.isoformat(),
        )

    def _invoice_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> Invoice:
        line_rows = connection.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
            (row["id"],),
        ).fetchall()
        file_row = connection.execute(
            """
            SELECT *
            FROM invoice_files
            WHERE invoice_id = ?
            ORDER BY deleted_at IS NULL DESC, created_at DESC
            LIMIT 1
            """,
            (row["id"],),
        ).fetchone()
        document_retention = (
            self._invoice_file_from_row(file_row).retention_model()
            if file_row
            else None
        )
        lines = [
            InvoiceLine(
                id=line["id"],
                line_number=line["line_number"],
                description=line["description"],
                quantity=line["quantity"],
                uom=line["uom"],
                unit_price=line["unit_price"],
                net_amount=line["net_amount"],
                tax_amount=line["tax_amount"],
                total_amount=line["total_amount"],
                hsn_sac=line["hsn_sac"],
                category=line["category"],
                gl_code=line["gl_code"],
                confidence=line["confidence"],
            )
            for line in line_rows
        ]
        return Invoice(
            id=row["id"],
            organization_id=row["organization_id"],
            source_file=row["source_file"],
            source_path=row["source_path"],
            parser=row["parser"],
            extraction_engine=row["extraction_engine"],
            page_count=row["page_count"],
            status=row["status"],
            invoice_number=row["invoice_number"],
            invoice_date=row["invoice_date"],
            due_date=row["due_date"],
            purchase_order=row["purchase_order"],
            currency=row["currency"],
            subtotal=row["subtotal"],
            tax_total=row["tax_total"],
            total=row["total"],
            supplier=_loads(row["supplier_json"], {}),
            customer=_loads(row["customer_json"], {}),
            direction=row["direction"],
            lines=lines,
            confidence=row["confidence"],
            evidence=_loads(row["evidence_json"], []),
            validation_issues=_loads(row["validation_issues_json"], []),
            raw_payload=_loads(row["raw_payload_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            document_retention=document_retention,
        )

    def _invoice_file_from_row(self, row: sqlite3.Row) -> InvoiceFileRecord:
        return InvoiceFileRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            invoice_id=row["invoice_id"],
            original_filename=row["original_filename"],
            content_type=row["content_type"],
            storage_backend=row["storage_backend"],
            storage_key=row["storage_key"],
            local_path=row["local_path"],
            sha256_hash=row["sha256_hash"],
            size_bytes=int(row["size_bytes"]),
            retention_policy=row["retention_policy"],
            retention_until=(
                datetime.fromisoformat(row["retention_until"])
                if row["retention_until"]
                else None
            ),
            deleted_at=(
                datetime.fromisoformat(row["deleted_at"])
                if row["deleted_at"]
                else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _replace_lines(
        self,
        connection: sqlite3.Connection,
        invoice_id: str,
        lines: List[InvoiceLine],
    ) -> None:
        connection.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
        for index, line in enumerate(lines, start=1):
            connection.execute(
                """
                INSERT INTO invoice_lines (
                    id, invoice_id, line_number, description, quantity, uom,
                    unit_price, net_amount, tax_amount, total_amount, hsn_sac,
                    category, gl_code, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    line.id or str(uuid.uuid4()),
                    invoice_id,
                    line.line_number or index,
                    line.description,
                    line.quantity,
                    line.uom,
                    line.unit_price,
                    line.net_amount,
                    line.tax_amount,
                    line.total_amount,
                    line.hsn_sac,
                    line.category,
                    line.gl_code,
                    line.confidence,
                ),
            )

    def _insert_correction(
        self,
        connection: sqlite3.Connection,
        organization_id: str,
        invoice_id: str,
        field_path: str,
        old_value: Any,
        new_value: Any,
        actor_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO corrections (
                id, organization_id, invoice_id, field_path, old_value_json,
                new_value_json, actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                organization_id,
                invoice_id,
                field_path,
                _json(old_value),
                _json(new_value),
                actor_id,
                utc_now().isoformat(),
            ),
        )

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        organization_id: str,
        invoice_id: Optional[str],
        event_type: str,
        details: Dict[str, Any],
        created_at: Optional[datetime] = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                id, organization_id, invoice_id, event_type, details_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                organization_id,
                invoice_id,
                event_type,
                _json(details),
                (created_at or utc_now()).isoformat(),
            ),
        )
