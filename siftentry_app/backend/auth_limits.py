"""Atomic, replica-shared authentication budgets backed by the application DB.

Every bucket is keyed by action, so abuse of one route can never consume
another route's capacity: demo traffic has its own buckets and its own global
ceiling, and cannot block login or refresh. Identifiers are hashed; credentials,
email addresses and client addresses are never persisted.

The client address comes from ``client_ip.resolve_client_address``. A verified
address (gateway attestation or a trusted proxy's forwarded header) receives
its own per-address budget. An unverified address shares one budget with
everything that arrives through the same hop, so a spoofed header can never buy
extra capacity; it only ever lands in the shared bucket.
"""
import hashlib
import time

from fastapi import HTTPException, Request

from .client_ip import resolve_client_address

WINDOW_SECONDS = 60

# Per action, per minute: (per verified client address, per unverified ingress hop).
ADDRESS_LIMITS = {
    "login": (30, 600),
    "refresh": (120, 1200),
    "reset-request": (10, 300),
    "reset-confirm": (20, 300),
    "invite-accept": (20, 300),
    "change-password": (20, 300),
    "connector-token": (20, 300),
    "demo": (30, 120),
}
DEFAULT_ADDRESS_LIMITS = (20, 300)

# Actions with a ceiling across every address. Demo is reachable without
# credentials and prepares a workspace; exhausting it affects demo only.
GLOBAL_LIMITS = {"demo": 300}


def _bucket_key(identity: str, start: int) -> str:
    return hashlib.sha256(f"{identity}:{start}".encode()).hexdigest()


def clear_successful_login_budget(request: Request, email: str) -> None:
    start = int(time.time()) // WINDOW_SECONDS * WINDOW_SECONDS
    key = _bucket_key(f"login:{email.strip().lower()}", start)
    with request.app.state.repository._connect() as connection:
        connection.execute("DELETE FROM auth_rate_buckets WHERE bucket_key = ?", (key,))


def enforce_auth_budget(
    request: Request, action: str, subject: str = "", *, limit: int = 10, seconds: int = 60
) -> None:
    now = int(time.time())
    state = getattr(getattr(request, "app", None), "state", None)
    address = resolve_client_address(request, getattr(state, "settings", None), now)
    per_address, per_ingress = ADDRESS_LIMITS.get(action, DEFAULT_ADDRESS_LIMITS)
    if address.verified:
        budgets = [(f"address:{action}:{address.ip}", per_address, WINDOW_SECONDS)]
    else:
        budgets = [(f"ingress:{action}:{address.ip}", per_ingress, WINDOW_SECONDS)]
    if action in GLOBAL_LIMITS:
        budgets.append((f"global:{action}", GLOBAL_LIMITS[action], WINDOW_SECONDS))
    if subject:
        budgets.append((f"{action}:{subject.strip().lower()}", limit, seconds))
    denied_until = 0
    with request.app.state.repository._connect() as connection:
        connection.execute("DELETE FROM auth_rate_buckets WHERE expires_at < ?", (now,))
        for identity, maximum, period in budgets:
            start = now // period * period
            row = connection.execute(
                """INSERT INTO auth_rate_buckets (bucket_key, attempts, expires_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT (bucket_key) DO UPDATE SET attempts = auth_rate_buckets.attempts + 1
                   RETURNING attempts""",
                (_bucket_key(identity, start), start + period),
            ).fetchone()
            if row["attempts"] > maximum:
                denied_until = max(denied_until, start + period)
    # Raise after committing: denied requests must not roll back accounting.
    if denied_until:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(max(1, denied_until - now))},
        )
