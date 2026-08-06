"""Authentication services and FastAPI dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import AuthenticatedUser, AuthTokens
from .repository import InvoiceRepository
from .security import (
    AuthenticationError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    parse_refresh_session_id,
    refresh_token_matches,
)
from .settings import ApiSettings


bearer_scheme = HTTPBearer(auto_error=False)


def authenticated_user(repository: InvoiceRepository, user_id: str) -> AuthenticatedUser:
    user = repository.get_user(user_id)
    if not user or not user.is_active:
        raise AuthenticationError("The user account is unavailable.")
    return AuthenticatedUser(
        **user.model_dump(),
        memberships=repository.list_memberships(user.id),
    )


def issue_tokens(
    repository: InvoiceRepository,
    user_id: str,
    settings: ApiSettings,
) -> AuthTokens:
    user = authenticated_user(repository, user_id)
    refresh = create_refresh_token(settings)
    repository.create_auth_session(
        session_id=refresh.session_id,
        user_id=user.id,
        token_hash=refresh.token_hash,
        expires_at=refresh.expires_at,
    )
    access_token, expires_in = create_access_token(
        user_id=user.id,
        session_id=refresh.session_id,
        settings=settings,
    )
    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh.token,
        expires_in=expires_in,
        user=user,
    )


def rotate_refresh_token(
    repository: InvoiceRepository,
    refresh_token: str,
    settings: ApiSettings,
) -> AuthTokens:
    session_id = parse_refresh_session_id(refresh_token)
    session = repository.get_auth_session(session_id)
    now = datetime.now(timezone.utc)
    if (
        not session
        or session.revoked_at is not None
        or session.expires_at <= now
        or not refresh_token_matches(refresh_token, session.token_hash)
    ):
        raise AuthenticationError("Invalid or expired refresh token.")

    user = authenticated_user(repository, session.user_id)
    replacement = create_refresh_token(settings)
    repository.create_auth_session(
        session_id=replacement.session_id,
        user_id=user.id,
        token_hash=replacement.token_hash,
        expires_at=replacement.expires_at,
    )
    repository.revoke_auth_session(session.id, replaced_by=replacement.session_id)
    access_token, expires_in = create_access_token(
        user_id=user.id,
        session_id=replacement.session_id,
        settings=settings,
    )
    return AuthTokens(
        access_token=access_token,
        refresh_token=replacement.token,
        expires_in=expires_in,
        user=authenticated_user(repository, user.id),
    )


_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DEMO_ALLOWED_MUTATION_PATHS = frozenset(
    {"/api/v1/auth/refresh", "/api/v1/auth/logout"}
)


def _enforce_demo_read_only(user: AuthenticatedUser, request: Request) -> None:
    """The public demo account can look at everything and change nothing.

    Role checks already stop most org-scoped writes, but the shared demo
    login must also never create organizations, accept invitations, or
    change its own account (e.g. the password everyone shares). This
    blanket guard at the auth chokepoint covers every authenticated
    endpoint, including ones added in the future. Only the exact refresh
    and logout routes stay allowed so sessions keep working.
    """
    from .demo_seed import PUBLIC_DEMO_EMAIL

    if user.email.strip().lower() != PUBLIC_DEMO_EMAIL:
        return
    if request.method.upper() in _READ_ONLY_METHODS:
        return
    if request.url.path in _DEMO_ALLOWED_MUTATION_PATHS:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "The public demo is read-only. Create your own SiftEntry "
            "workspace to upload and manage invoices."
        ),
    )


def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        settings: ApiSettings = request.app.state.settings
        payload = decode_access_token(credentials.credentials, settings)
        repository: InvoiceRepository = request.app.state.repository
        session = repository.get_auth_session(str(payload["sid"]))
        now = datetime.now(timezone.utc)
        if (
            not session
            or session.user_id != str(payload["sub"])
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            raise AuthenticationError("The authentication session is no longer active.")
        user = authenticated_user(repository, str(payload["sub"]))
        _enforce_demo_read_only(user, request)
        return user
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
