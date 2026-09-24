"""Atomic, replica-shared authentication budgets backed by the application DB.

Identifiers are hashed; credentials and email addresses are never persisted here.
No forwarded IP header is trusted. The peer budget is intentionally generous for
the shared web gateway; identity budgets apply across peers and API replicas.
"""
import hashlib
import time

from fastapi import HTTPException, Request


def clear_successful_login_budget(request: Request, email: str) -> None:
    start = int(time.time()) // 60 * 60
    key = hashlib.sha256(f"login:{email.strip().lower()}:{start}".encode()).hexdigest()
    with request.app.state.repository._connect() as connection:
        connection.execute("DELETE FROM auth_rate_buckets WHERE bucket_key = ?", (key,))


def enforce_auth_budget(request: Request, action: str, subject: str = "", *, limit: int = 10, seconds: int = 60) -> None:
    now = int(time.time())
    peer = request.client.host if request.client else "unknown"
    budgets = [(f"peer:{peer}", 600, 60)]
    if subject:
        budgets.append((f"{action}:{subject.strip().lower()}", limit, seconds))
    denied_until = 0
    with request.app.state.repository._connect() as connection:
        connection.execute("DELETE FROM auth_rate_buckets WHERE expires_at < ?", (now,))
        for identity, maximum, period in budgets:
            start = now // period * period
            key = hashlib.sha256(f"{identity}:{start}".encode()).hexdigest()
            row = connection.execute(
                """INSERT INTO auth_rate_buckets (bucket_key, attempts, expires_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT (bucket_key) DO UPDATE SET attempts = auth_rate_buckets.attempts + 1
                   RETURNING attempts""",
                (key, start + period),
            ).fetchone()
            if row["attempts"] > maximum:
                denied_until = max(denied_until, start + period)
    # Raise after committing: denied requests must not roll back accounting.
    if denied_until:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.",
                            headers={"Retry-After": str(max(1, denied_until - now))})
