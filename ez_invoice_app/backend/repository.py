"""SQLite persistence for the first EZ-Invoice SaaS backend slice."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    Invitation,
    Invoice,
    InvoiceCreate,
    InvoiceLine,
    InvoicePatch,
    InvoiceStatus,
    Membership,
    Organization,
    OrganizationCreate,
    OrganizationRole,
    PostingResult,
    PostingTarget,
    User,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@dataclass(frozen=True)
class AuthSessionRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime]
    replaced_by: Optional[str]


class InvoiceRepository:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.Lock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

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

                CREATE TABLE IF NOT EXISTS posting_attempts (
                    id TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    external_id TEXT,
                    issues_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                );

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

    def _organization_from_row(self, row: sqlite3.Row) -> Organization:
        return Organization(
            id=row["id"],
            name=row["name"],
            legal_names=_loads(row["legal_names_json"], []),
            default_currency=row["default_currency"],
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
    ) -> PostingResult:
        current = self.get_invoice(invoice_id)
        if not current:
            raise ValueError("Invoice does not exist.")
        posting = PostingResult(
            id=str(uuid.uuid4()),
            invoice_id=invoice_id,
            target=target,
            success=success,
            dry_run=dry_run,
            message=message,
            external_id=external_id,
            issues=issues or [],
            raw=raw or {},
            created_at=utc_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO posting_attempts (
                    id, invoice_id, target, success, dry_run, message,
                    external_id, issues_json, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.id,
                    posting.invoice_id,
                    posting.target,
                    int(posting.success),
                    int(posting.dry_run),
                    posting.message,
                    posting.external_id,
                    _json(posting.issues),
                    _json(posting.raw),
                    posting.created_at.isoformat(),
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

    def get_posting(self, posting_id: str) -> Optional[PostingResult]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM posting_attempts WHERE id = ?", (posting_id,)
            ).fetchone()
        if not row:
            return None
        return PostingResult(
            id=row["id"],
            invoice_id=row["invoice_id"],
            target=row["target"],
            success=bool(row["success"]),
            dry_run=bool(row["dry_run"]),
            message=row["message"],
            external_id=row["external_id"],
            issues=_loads(row["issues_json"], []),
            raw=_loads(row["raw_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
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
                utc_now().isoformat(),
            ),
        )
