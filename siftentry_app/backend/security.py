"""Password hashing, access tokens, and opaque refresh-token helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from pwdlib import PasswordHash

from .settings import ApiSettings


PASSWORD_HASH = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class RefreshToken:
    session_id: str
    token: str
    token_hash: str
    expires_at: datetime


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASH.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(
    user_id: str,
    session_id: str,
    settings: ApiSettings,
) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return (
        jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM),
        max(1, int((expires - now).total_seconds())),
    )


def decode_access_token(token: str, settings: ApiSettings) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "sid", "type", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired access token.") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token type.")
    return payload


def create_refresh_token(settings: ApiSettings) -> RefreshToken:
    session_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(48)
    token = session_id + "." + secret
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)
    return RefreshToken(
        session_id=session_id,
        token=token,
        token_hash=hash_refresh_token(token),
        expires_at=expires_at,
    )


def parse_refresh_session_id(token: str) -> str:
    session_id, separator, secret = token.partition(".")
    if not separator or not session_id or not secret:
        raise AuthenticationError("Invalid refresh token.")
    return session_id


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_matches(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(token), expected_hash)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
