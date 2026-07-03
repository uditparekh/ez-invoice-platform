"""Database connectivity for SQLite (pilot default) and PostgreSQL (production).

One repository, two dialects. SQLite keeps today's behavior exactly.
PostgreSQL activates when EZ_API_DATABASE_URL starts with postgres:// or
postgresql:// — connections are wrapped so the repository's existing SQL
("?" placeholders, name-addressable rows, executescript for DDL) runs
unchanged. Python bools/datetimes are coerced to the schema's INTEGER/TEXT
storage forms so both engines store identical shapes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse


def is_postgres_url(database_url: str) -> bool:
    if not database_url:
        return False
    return urlparse(database_url).scheme.startswith("postgres")


def connect(database_url: str, database_path: Path):
    """Open a connection appropriate to the configured engine."""
    if is_postgres_url(database_url):
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(database_url, row_factory=dict_row)
        return PostgresConnection(raw)

    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def table_columns(connection, table: str) -> set:
    """Column names for a table — dialect-aware (PRAGMA vs information_schema)."""
    if isinstance(connection, PostgresConnection):
        rows = connection.execute(
            """
            SELECT column_name AS name FROM information_schema.columns
            WHERE table_name = ?
            """,
            (table,),
        ).fetchall()
        return {str(row["name"]) for row in rows}
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


class PostgresConnection:
    """Adapts a psycopg connection to the repository's sqlite3 idioms."""

    def __init__(self, raw) -> None:
        self._raw = raw

    # -- context manager: commit on success, rollback on error, always close --
    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()
        return False

    def execute(self, sql: str, params: Iterable[Any] = ()):
        return self._raw.execute(_translate(sql), _coerce_params(params))

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self._raw.execute(_translate(statement))

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


import re as _re

_NOCASE_EQ = _re.compile(r"([A-Za-z_][\w.]*)\s*=\s*\?\s*COLLATE NOCASE", _re.IGNORECASE)
_NOCASE_DDL = _re.compile(r"((?:NOT NULL|UNIQUE|PRIMARY KEY))\s+COLLATE NOCASE", _re.IGNORECASE)
_NOCASE_EXPR = _re.compile(r"([A-Za-z_][\w.]*)\s+COLLATE NOCASE", _re.IGNORECASE)


def _translate(sql: str) -> str:
    """Rewrite the repository's SQLite SQL into PostgreSQL.

    - "?" placeholders -> "%s"
    - "col = ? COLLATE NOCASE" -> case-insensitive comparison on both sides
    - DDL "... NOT NULL/UNIQUE COLLATE NOCASE" -> collation dropped (a LOWER()
      unique index is created separately for users.email)
    - "expr COLLATE NOCASE" (ORDER BY, expression indexes) -> LOWER(expr)
    """
    sql = _NOCASE_EQ.sub(lambda m: f"LOWER({m.group(1)}) = LOWER(?)", sql)
    sql = _NOCASE_DDL.sub(lambda m: m.group(1), sql)
    sql = _NOCASE_EXPR.sub(lambda m: f"LOWER({m.group(1)})", sql)
    return sql.replace("?", "%s")


def _coerce_params(params: Iterable[Any]) -> tuple:
    return tuple(_coerce(value) for value in params)


def _coerce(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)  # schema stores booleans as INTEGER 0/1
    if isinstance(value, datetime):
        return value.isoformat()  # schema stores timestamps as TEXT
    if isinstance(value, Path):
        return str(value)
    return value


def create_database_if_missing(database_url: str) -> None:
    """Best-effort CREATE DATABASE for postgres URLs (used by tests/dev)."""
    if not is_postgres_url(database_url):
        return
    import psycopg

    parsed = urlparse(database_url)
    dbname = parsed.path.lstrip("/")
    admin_url = database_url.replace(f"/{dbname}", "/postgres")
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            exists = admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if not exists:
                admin.execute(f'CREATE DATABASE "{dbname}"')
    except Exception:
        # If we can't create it (permissions, already exists race), the real
        # connect() below will surface the actual problem.
        pass
