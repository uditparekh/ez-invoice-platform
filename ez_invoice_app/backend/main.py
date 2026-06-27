"""FastAPI entry point for the EZ-Invoice SaaS foundation."""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .adapters import default_adapters
from .auth import get_current_user, issue_tokens, rotate_refresh_token
from .email import EmailDeliveryError, EmailService
from .models import (
    AccountingSystem,
    AuthBootstrapRequest,
    AuthenticatedUser,
    AuthTokens,
    ClientProfile,
    ClientProfileCreate,
    ClientProfilePatch,
    CorrectionLearningSignal,
    DeleteInvoicesResult,
    HealthResponse,
    Invitation,
    InvitationAcceptRequest,
    InvitationCreate,
    Invoice,
    InvoiceCreate,
    InvoicePatch,
    InvoiceStatus,
    LoginRequest,
    Membership,
    Organization,
    OrganizationCreate,
    OrganizationMember,
    OrganizationRole,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    PostingRequest,
    PostingRetryRequest,
    PostingResult,
    PostingResultCreate,
    PostingTarget,
    ProfileRecommendationResult,
    RefreshRequest,
    ValidationResult,
)
from .parser_service import parse_pdf_invoice
from .profile_recommendation import recommend_client_profiles
from .repository import InvoiceRepository
from .security import (
    AuthenticationError,
    hash_invitation_token,
    hash_password,
    hash_password_reset_token,
    parse_refresh_session_id,
    verify_password,
)
from .settings import ApiSettings
from .storage import LocalDocumentStorage
from .validation import validate_invoice


API_VERSION = "0.3.0"
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

READ_ROLES = set(OrganizationRole)
EDIT_ROLES = {
    OrganizationRole.OWNER,
    OrganizationRole.ADMIN,
    OrganizationRole.ACCOUNTANT,
}
VALIDATE_ROLES = EDIT_ROLES | {OrganizationRole.APPROVER}
APPROVE_ROLES = {
    OrganizationRole.OWNER,
    OrganizationRole.ADMIN,
    OrganizationRole.APPROVER,
}
MANAGE_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN}


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    resolved = settings or ApiSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved
        app.state.repository = InvoiceRepository(resolved.database_path)
        app.state.storage = LocalDocumentStorage(resolved.upload_directory)
        app.state.adapters = default_adapters()
        app.state.email = EmailService(resolved)
        yield

    app = FastAPI(
        title="EZ-Invoice API",
        version=API_VERSION,
        description="Universal invoice intake, review, validation, and accounting posting API.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="ez-invoice-api", version=API_VERSION)

    @app.get("/health/deployment", tags=["system"])
    def deployment_health(request: Request) -> Dict[str, Any]:
        settings = request.app.state.settings
        problems = settings.production_readiness_problems()
        return {
            "status": "ready" if not problems else "needs_configuration",
            "environment": settings.environment,
            "checks": {
                "jwt_secret": settings.jwt_secret != "ez-invoice-local-development-secret-change-me"
                and len(settings.jwt_secret) >= 32,
                "dev_bootstrap_disabled": not settings.allow_dev_bootstrap,
                "database_url_configured": bool(settings.database_url),
                "sqlite_pilot_database": settings.is_sqlite,
                "https_app_url": settings.app_base_url.startswith("https://"),
                "cors_configured": bool(settings.cors_origins)
                and not any(
                    "localhost" in origin or "127.0.0.1" in origin
                    for origin in settings.cors_origins
                ),
                "email_provider": settings.email_provider,
                "smtp_configured": settings.email_provider == "smtp"
                and bool(settings.smtp_host)
                and bool(settings.smtp_username)
                and bool(settings.smtp_password),
            },
            "problems": problems,
        }

    @app.post(
        "/api/v1/auth/bootstrap",
        response_model=AuthTokens,
        status_code=status.HTTP_201_CREATED,
        tags=["authentication"],
    )
    def bootstrap_owner(request: Request, body: AuthBootstrapRequest) -> AuthTokens:
        settings = request.app.state.settings
        repository = _repo(request)
        if not settings.allow_dev_bootstrap:
            raise HTTPException(status_code=404, detail="Development bootstrap is disabled.")
        if repository.count_users():
            raise HTTPException(status_code=409, detail="The initial owner account already exists.")
        try:
            user = repository.create_user(
                email=body.email,
                password_hash=hash_password(body.password),
                full_name=body.full_name,
            )
            organization = repository.get_organization_by_name(body.organization_name)
            if not organization:
                organization = repository.create_organization(
                    OrganizationCreate(
                        name=body.organization_name,
                        legal_names=body.legal_names,
                        default_currency=body.default_currency,
                    )
                )
            repository.create_membership(
                user.id,
                organization.id,
                OrganizationRole.OWNER,
            )
            repository.mark_user_login(user.id)
            return issue_tokens(repository, user.id, settings)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/auth/login",
        response_model=AuthTokens,
        tags=["authentication"],
    )
    def login(request: Request, body: LoginRequest) -> AuthTokens:
        repository = _repo(request)
        user = repository.get_user_by_email(body.email)
        password_hash = repository.get_password_hash(user.id) if user else None
        if (
            not user
            or not user.is_active
            or not password_hash
            or not verify_password(body.password, password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        repository.mark_user_login(user.id)
        return issue_tokens(repository, user.id, request.app.state.settings)

    @app.post(
        "/api/v1/auth/refresh",
        response_model=AuthTokens,
        tags=["authentication"],
    )
    def refresh(request: Request, body: RefreshRequest) -> AuthTokens:
        try:
            return rotate_refresh_token(
                _repo(request),
                body.refresh_token,
                request.app.state.settings,
            )
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/v1/auth/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["authentication"],
    )
    def logout(
        request: Request,
        body: RefreshRequest,
        current_user: CurrentUser,
    ) -> Response:
        try:
            session_id = parse_refresh_session_id(body.refresh_token)
            session = _repo(request).get_auth_session(session_id)
            if session and session.user_id == current_user.id:
                _repo(request).revoke_auth_session(session_id)
        except AuthenticationError:
            pass
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get(
        "/api/v1/auth/me",
        response_model=AuthenticatedUser,
        tags=["authentication"],
    )
    def me(current_user: CurrentUser) -> AuthenticatedUser:
        return current_user

    @app.post(
        "/api/v1/auth/change-password",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["authentication"],
    )
    def change_password(
        request: Request,
        body: PasswordChangeRequest,
        current_user: CurrentUser,
    ) -> Response:
        repository = _repo(request)
        password_hash = repository.get_password_hash(current_user.id)
        if not password_hash or not verify_password(body.current_password, password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect.",
            )
        repository.update_password_hash(current_user.id, hash_password(body.new_password))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/auth/password-reset/request",
        response_model=PasswordResetResponse,
        tags=["authentication"],
    )
    def request_password_reset(
        request: Request,
        body: PasswordResetRequest,
    ) -> PasswordResetResponse:
        repository = _repo(request)
        settings = request.app.state.settings
        user = repository.get_user_by_email(body.email)
        message = "If an account exists, password reset instructions have been prepared."
        if not user or not user.is_active:
            return PasswordResetResponse(message=message)

        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        repository.create_password_reset(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=expires_at,
        )
        reset_url = f"{settings.app_base_url}/reset-password?token={token}"
        try:
            request.app.state.email.send_password_reset(
                to_email=user.email,
                full_name=user.full_name,
                reset_url=reset_url,
                expires_at=expires_at,
            )
        except EmailDeliveryError as exc:
            raise HTTPException(
                status_code=502,
                detail="Password reset email could not be sent. Check email configuration.",
            ) from exc
        return PasswordResetResponse(
            message=message,
            reset_token=token if settings.environment != "production" else None,
            expires_at=expires_at if settings.environment != "production" else None,
        )

    @app.post(
        "/api/v1/auth/password-reset/confirm",
        response_model=AuthTokens,
        tags=["authentication"],
    )
    def confirm_password_reset(
        request: Request,
        body: PasswordResetConfirmRequest,
    ) -> AuthTokens:
        repository = _repo(request)
        reset = repository.get_password_reset_by_hash(
            hash_password_reset_token(body.token)
        )
        now = datetime.now(timezone.utc)
        if not reset or reset.used_at is not None or reset.expires_at <= now:
            raise HTTPException(
                status_code=400,
                detail="Password reset link is invalid or expired.",
            )

        user = repository.get_user(reset.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=400,
                detail="Password reset link is invalid or expired.",
            )

        repository.update_password_hash(user.id, hash_password(body.new_password))
        repository.mark_password_reset_used(reset.id)
        repository.revoke_auth_sessions_for_user(user.id)
        repository.mark_user_login(user.id)
        return issue_tokens(repository, user.id, request.app.state.settings)

    @app.get(
        "/api/v1/organizations/{organization_id}/members",
        response_model=List[OrganizationMember],
        tags=["authentication"],
    )
    def list_organization_members(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
    ) -> List[OrganizationMember]:
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        return _repo(request).list_organization_members(organization_id)

    @app.get(
        "/api/v1/organizations/{organization_id}/invitations",
        response_model=List[Invitation],
        tags=["authentication"],
    )
    def list_organization_invitations(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
        include_accepted: bool = Query(default=False),
    ) -> List[Invitation]:
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        return _repo(request).list_organization_invitations(
            organization_id,
            include_accepted=include_accepted,
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/invitations",
        response_model=Invitation,
        status_code=status.HTTP_201_CREATED,
        tags=["authentication"],
    )
    def create_invitation(
        request: Request,
        organization_id: str,
        body: InvitationCreate,
        current_user: CurrentUser,
    ) -> Invitation:
        membership = _require_membership(
            request,
            current_user,
            organization_id,
            MANAGE_ROLES,
        )
        if body.role == OrganizationRole.OWNER and membership.role != OrganizationRole.OWNER:
            raise HTTPException(status_code=403, detail="Only an owner can invite another owner.")
        token = secrets.token_urlsafe(48)
        invitation = _repo(request).create_invitation(
            organization_id=organization_id,
            email=body.email,
            role=body.role,
            token_hash=hash_invitation_token(token),
            invited_by=current_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        organization = _repo(request).get_organization(organization_id)
        invitation_url = f"{request.app.state.settings.app_base_url}/invite?token={token}"
        try:
            request.app.state.email.send_invitation(
                to_email=invitation.email,
                organization_name=organization.name if organization else "your workspace",
                invited_by_name=current_user.full_name or current_user.email,
                role=str(invitation.role),
                invitation_url=invitation_url,
                expires_at=invitation.expires_at,
            )
        except EmailDeliveryError as exc:
            raise HTTPException(
                status_code=502,
                detail="Invitation email could not be sent. Check email configuration.",
            ) from exc
        return invitation.model_copy(
            update={
                "invitation_token": (
                    token if request.app.state.settings.environment != "production" else None
                )
            }
        )

    @app.post(
        "/api/v1/auth/invitations/accept",
        response_model=AuthTokens,
        tags=["authentication"],
    )
    def accept_invitation(
        request: Request,
        body: InvitationAcceptRequest,
    ) -> AuthTokens:
        repository = _repo(request)
        invitation = repository.get_invitation_by_hash(hash_invitation_token(body.token))
        now = datetime.now(timezone.utc)
        if (
            not invitation
            or invitation.accepted_at is not None
            or invitation.expires_at <= now
        ):
            raise HTTPException(status_code=400, detail="Invitation is invalid or expired.")
        user = repository.get_user_by_email(invitation.email)
        if user:
            password_hash = repository.get_password_hash(user.id)
            if not password_hash or not verify_password(body.password, password_hash):
                raise HTTPException(status_code=401, detail="Invalid account password.")
        else:
            user = repository.create_user(
                invitation.email,
                hash_password(body.password),
                body.full_name,
            )
        repository.create_membership(
            user.id,
            invitation.organization_id,
            invitation.role,
        )
        repository.accept_invitation(invitation.id)
        repository.mark_user_login(user.id)
        return issue_tokens(repository, user.id, request.app.state.settings)

    @app.post(
        "/api/v1/organizations",
        response_model=Organization,
        status_code=status.HTTP_201_CREATED,
        tags=["organizations"],
    )
    def create_organization(
        request: Request,
        body: OrganizationCreate,
        current_user: CurrentUser,
    ) -> Organization:
        organization = _repo(request).create_organization(body)
        _repo(request).create_membership(
            current_user.id,
            organization.id,
            OrganizationRole.OWNER,
        )
        return organization

    @app.get(
        "/api/v1/organizations",
        response_model=List[Organization],
        tags=["organizations"],
    )
    def list_organizations(
        request: Request,
        current_user: CurrentUser,
    ) -> List[Organization]:
        return _repo(request).list_organizations_for_user(current_user.id)

    @app.get(
        "/api/v1/organizations/{organization_id}/corrections/learning",
        response_model=List[CorrectionLearningSignal],
        tags=["organizations"],
    )
    def list_correction_learning(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> List[CorrectionLearningSignal]:
        _require_membership(request, current_user, organization_id, READ_ROLES)
        return _repo(request).list_correction_learning_signals(
            organization_id,
            limit=limit,
        )

    @app.get(
        "/api/v1/organizations/{organization_id}/client-profiles",
        response_model=List[ClientProfile],
        tags=["client-profiles"],
    )
    def list_client_profiles(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
        accounting_system: Optional[AccountingSystem] = Query(default=None),
    ) -> List[ClientProfile]:
        _require_membership(request, current_user, organization_id, READ_ROLES)
        return _repo(request).list_client_profiles(
            organization_id,
            accounting_system.value if accounting_system else None,
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/client-profiles",
        response_model=ClientProfile,
        status_code=status.HTTP_201_CREATED,
        tags=["client-profiles"],
    )
    def create_client_profile(
        request: Request,
        organization_id: str,
        body: ClientProfileCreate,
        current_user: CurrentUser,
    ) -> ClientProfile:
        _require_membership(request, current_user, organization_id, EDIT_ROLES)
        _get_organization(request, organization_id)
        try:
            return _repo(request).create_client_profile(
                organization_id,
                body,
                actor_id=current_user.id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="A client profile with this name already exists.",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def get_client_profile(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> ClientProfile:
        return _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            READ_ROLES,
        )

    @app.patch(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def update_client_profile(
        request: Request,
        organization_id: str,
        profile_id: str,
        body: ClientProfilePatch,
        current_user: CurrentUser,
    ) -> ClientProfile:
        _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            EDIT_ROLES,
        )
        try:
            profile = _repo(request).update_client_profile(
                profile_id,
                body,
                actor_id=current_user.id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="A client profile with this name already exists.",
            ) from exc
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return profile

    @app.post(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/set-default",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def set_default_client_profile(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> ClientProfile:
        _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            EDIT_ROLES,
        )
        profile = _repo(request).set_default_client_profile(
            profile_id,
            actor_id=current_user.id,
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return profile

    @app.delete(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["client-profiles"],
    )
    def delete_client_profile(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> Response:
        _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            MANAGE_ROLES,
        )
        _repo(request).delete_client_profile(profile_id, actor_id=current_user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/invoices/import",
        response_model=Invoice,
        status_code=status.HTTP_201_CREATED,
        tags=["invoices"],
    )
    def import_invoice(
        request: Request,
        body: InvoiceCreate,
        current_user: CurrentUser,
    ) -> Invoice:
        _require_membership(request, current_user, body.organization_id, EDIT_ROLES)
        try:
            return _repo(request).create_invoice(body)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/invoices/upload",
        response_model=Invoice,
        status_code=status.HTTP_201_CREATED,
        tags=["invoices"],
    )
    async def upload_invoice(
        request: Request,
        organization_id: str,
        file: Annotated[UploadFile, File(description="Supplier invoice PDF")],
        current_user: CurrentUser,
        parser_mode: str = Query(default="auto"),
    ) -> Invoice:
        _require_membership(request, current_user, organization_id, EDIT_ROLES)
        organization = _get_organization(request, organization_id)
        filename = Path(file.filename or "invoice.pdf").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="Only PDF invoices are accepted.")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
        if len(content) > request.app.state.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="The uploaded PDF exceeds the size limit.")

        stored_path = _storage(request).save(organization_id, filename, content)
        try:
            parsed = parse_pdf_invoice(
                filename=filename,
                pdf_bytes=content,
                organization_id=organization_id,
                legal_names=organization.legal_names or [organization.name],
                source_path=str(stored_path),
                parser_mode=parser_mode,
            )
            return _repo(request).create_invoice(parsed)
        except ValueError as exc:
            _storage(request).delete(stored_path)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            _storage(request).delete(stored_path)
            raise HTTPException(status_code=500, detail=f"Invoice processing failed: {exc}") from exc

    @app.get("/api/v1/invoices", response_model=List[Invoice], tags=["invoices"])
    def list_invoices(
        request: Request,
        current_user: CurrentUser,
        organization_id: str,
        invoice_status: Optional[InvoiceStatus] = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> List[Invoice]:
        _require_membership(request, current_user, organization_id, READ_ROLES)
        return _repo(request).list_invoices(
            organization_id=organization_id,
            status=invoice_status,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/v1/invoices/{invoice_id}", response_model=Invoice, tags=["invoices"])
    def get_invoice(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
    ) -> Invoice:
        return _require_invoice(request, invoice_id, current_user, READ_ROLES)

    @app.get("/api/v1/invoices/{invoice_id}/document", tags=["invoices"])
    def get_invoice_document(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
    ) -> FileResponse:
        invoice = _require_invoice(request, invoice_id, current_user, READ_ROLES)
        source_path = Path(invoice.source_path)
        if not source_path.exists() or not source_path.is_file():
            raise HTTPException(status_code=404, detail="Invoice document not found.")
        return FileResponse(
            source_path,
            media_type="application/pdf",
            filename=invoice.source_file,
        )

    @app.get(
        "/api/v1/invoices/{invoice_id}/profile-recommendations",
        response_model=ProfileRecommendationResult,
        tags=["workflow"],
    )
    def recommend_invoice_profile(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
        accounting_system: Optional[AccountingSystem] = Query(default=None),
    ) -> ProfileRecommendationResult:
        invoice = _require_invoice(request, invoice_id, current_user, READ_ROLES)
        profiles = _repo(request).list_client_profiles(
            invoice.organization_id,
            accounting_system=(
                accounting_system.value if accounting_system is not None else None
            ),
        )
        return recommend_client_profiles(invoice, profiles)

    @app.delete(
        "/api/v1/organizations/{organization_id}/invoices",
        response_model=DeleteInvoicesResult,
        tags=["invoices"],
    )
    def clear_organization_invoices(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
    ) -> DeleteInvoicesResult:
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        stored_paths = [
            invoice.source_path
            for invoice in _repo(request).list_invoices(
                organization_id=organization_id,
                limit=100_000,
                offset=0,
            )
            if invoice.source_path
        ]
        deleted = _repo(request).delete_organization_invoices(organization_id)
        for stored_path in stored_paths:
            _storage(request).delete(Path(stored_path))
        return DeleteInvoicesResult(organization_id=organization_id, deleted=deleted)

    @app.patch("/api/v1/invoices/{invoice_id}", response_model=Invoice, tags=["invoices"])
    def patch_invoice(
        request: Request,
        invoice_id: str,
        body: InvoicePatch,
        current_user: CurrentUser,
    ) -> Invoice:
        _require_invoice(request, invoice_id, current_user, EDIT_ROLES)
        invoice = _repo(request).patch_invoice(
            invoice_id,
            body,
            actor_id=current_user.id,
        )
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        return invoice

    @app.post(
        "/api/v1/invoices/{invoice_id}/validate",
        response_model=ValidationResult,
        tags=["workflow"],
    )
    def validate_invoice_endpoint(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
    ) -> ValidationResult:
        invoice = _require_invoice(request, invoice_id, current_user, VALIDATE_ROLES)
        result = validate_invoice(invoice)
        _repo(request).update_validation(invoice_id, result.status, result.issues)
        return result

    @app.post(
        "/api/v1/invoices/{invoice_id}/approve",
        response_model=Invoice,
        tags=["workflow"],
    )
    def approve_invoice(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
    ) -> Invoice:
        invoice = _require_invoice(request, invoice_id, current_user, APPROVE_ROLES)
        current_status = InvoiceStatus(invoice.status)
        if current_status != InvoiceStatus.VALIDATED:
            raise HTTPException(
                status_code=409,
                detail="Only a validated invoice can be approved.",
            )
        return _repo(request).set_status(invoice_id, InvoiceStatus.APPROVED) or invoice

    @app.post(
        "/api/v1/invoices/{invoice_id}/post",
        response_model=PostingResult,
        tags=["workflow"],
    )
    def post_invoice(
        request: Request,
        invoice_id: str,
        body: PostingRequest,
        current_user: CurrentUser,
    ) -> PostingResult:
        invoice = _require_invoice(request, invoice_id, current_user, EDIT_ROLES)
        return _execute_posting(
            request,
            current_user,
            invoice,
            target=body.target,
            client_profile_id=body.client_profile_id,
            dry_run=body.dry_run,
        )

    @app.get(
        "/api/v1/invoices/{invoice_id}/postings",
        response_model=List[PostingResult],
        tags=["workflow"],
    )
    def list_invoice_postings(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> List[PostingResult]:
        _require_invoice(request, invoice_id, current_user, READ_ROLES)
        return _repo(request).list_postings_for_invoice(invoice_id, limit=limit)

    @app.get(
        "/api/v1/postings/{posting_id}",
        response_model=PostingResult,
        tags=["workflow"],
    )
    def get_posting(
        request: Request,
        posting_id: str,
        current_user: CurrentUser,
    ) -> PostingResult:
        posting = _repo(request).get_posting(posting_id)
        if not posting:
            raise HTTPException(status_code=404, detail="Posting attempt not found.")
        _require_invoice(request, posting.invoice_id, current_user, READ_ROLES)
        return posting

    @app.post(
        "/api/v1/postings/{posting_id}/retry",
        response_model=PostingResult,
        tags=["workflow"],
    )
    def retry_posting(
        request: Request,
        posting_id: str,
        body: PostingRetryRequest,
        current_user: CurrentUser,
    ) -> PostingResult:
        previous = _repo(request).get_posting(posting_id)
        if not previous:
            raise HTTPException(status_code=404, detail="Posting attempt not found.")
        invoice = _require_invoice(
            request,
            previous.invoice_id,
            current_user,
            EDIT_ROLES,
        )
        return _execute_posting(
            request,
            current_user,
            invoice,
            target=PostingTarget(previous.target),
            client_profile_id=previous.client_profile_id,
            dry_run=previous.dry_run if body.dry_run is None else body.dry_run,
            retry_of=previous.id,
        )

    @app.post(
        "/api/v1/invoices/{invoice_id}/posting-results",
        response_model=PostingResult,
        status_code=status.HTTP_201_CREATED,
        tags=["workflow"],
    )
    def record_posting_result(
        request: Request,
        invoice_id: str,
        body: PostingResultCreate,
        current_user: CurrentUser,
    ) -> PostingResult:
        _require_invoice(request, invoice_id, current_user, EDIT_ROLES)
        posting = _repo(request).create_posting(
            invoice_id=invoice_id,
            target=body.target,
            success=body.success,
            dry_run=body.dry_run,
            actor_id=current_user.id,
            client_profile_id=body.client_profile_id,
            message=body.message,
            external_id=body.external_id,
            issues=body.issues,
            raw=body.raw,
            request_payload=body.request_payload,
            response_payload=body.raw,
        )
        if not body.dry_run:
            final_status = InvoiceStatus.POSTED if body.success else InvoiceStatus.FAILED
            _repo(request).set_status(invoice_id, final_status)
        return posting

    return app


def _repo(request: Request) -> InvoiceRepository:
    return request.app.state.repository


def _storage(request: Request) -> LocalDocumentStorage:
    return request.app.state.storage


def _get_organization(request: Request, organization_id: str) -> Organization:
    organization = _repo(request).get_organization(organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return organization


def _require_membership(
    request: Request,
    current_user: AuthenticatedUser,
    organization_id: str,
    allowed_roles: set[OrganizationRole],
) -> Membership:
    membership = _repo(request).get_membership(current_user.id, organization_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role does not allow this action.",
        )
    return membership


def _require_invoice(
    request: Request,
    invoice_id: str,
    current_user: AuthenticatedUser,
    allowed_roles: set[OrganizationRole],
) -> Invoice:
    invoice = _repo(request).get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    _require_membership(
        request,
        current_user,
        invoice.organization_id,
        allowed_roles,
    )
    return invoice


def _require_client_profile(
    request: Request,
    organization_id: str,
    profile_id: str,
    current_user: AuthenticatedUser,
    allowed_roles: set[OrganizationRole],
) -> ClientProfile:
    _require_membership(request, current_user, organization_id, allowed_roles)
    profile = _repo(request).get_client_profile(profile_id)
    if not profile or profile.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    return profile


def _execute_posting(
    request: Request,
    current_user: AuthenticatedUser,
    invoice: Invoice,
    target: Optional[PostingTarget],
    client_profile_id: Optional[str],
    dry_run: bool,
    retry_of: Optional[str] = None,
) -> PostingResult:
    current_status = InvoiceStatus(invoice.status)
    if current_status not in {
        InvoiceStatus.VALIDATED,
        InvoiceStatus.APPROVED,
        InvoiceStatus.FAILED,
    }:
        raise HTTPException(
            status_code=409,
            detail="Validate the invoice before posting.",
        )

    resolved_target, client_profile = _resolve_posting_target_and_profile(
        request,
        invoice.organization_id,
        target,
        client_profile_id,
        current_user,
        invoice,
    )
    adapter = request.app.state.adapters.get(resolved_target)
    if adapter is None:
        raise HTTPException(status_code=400, detail="Unsupported accounting target.")

    request_payload = _posting_request_payload(
        invoice=invoice,
        target=resolved_target,
        dry_run=dry_run,
        client_profile=client_profile,
        retry_of=retry_of,
    )
    posting = _repo(request).start_posting(
        invoice_id=invoice.id,
        target=resolved_target,
        dry_run=dry_run,
        actor_id=current_user.id,
        client_profile_id=client_profile.id if client_profile else None,
        request_payload=request_payload,
    )
    if not dry_run:
        _repo(request).set_status(invoice.id, InvoiceStatus.POSTING)
    try:
        connector_result = adapter.post(
            invoice,
            dry_run=dry_run,
            client_profile=client_profile,
        )
    except Exception as exc:
        completed = _repo(request).complete_posting(
            posting_id=posting.id,
            success=False,
            message=f"Connector failed unexpectedly: {exc}",
            raw={"error": str(exc), "retry_of": retry_of},
            response_payload={
                "success": False,
                "message": f"Connector failed unexpectedly: {exc}",
                "error": str(exc),
                "retry_of": retry_of,
                "posting_plan": request_payload.get("posting_plan", {}),
            },
        )
        if not dry_run:
            _repo(request).set_status(invoice.id, InvoiceStatus.FAILED)
        return completed

    response_payload = {
        "success": connector_result.success,
        "message": connector_result.message,
        "external_id": connector_result.external_id,
        "issues": [issue.__dict__ for issue in connector_result.issues],
        "raw": connector_result.raw,
        "retry_of": retry_of,
        "posting_plan": request_payload.get("posting_plan", {}),
    }
    completed = _repo(request).complete_posting(
        posting_id=posting.id,
        success=connector_result.success,
        message=connector_result.message,
        external_id=connector_result.external_id,
        issues=[issue.__dict__ for issue in connector_result.issues],
        raw=connector_result.raw,
        response_payload=response_payload,
    )
    if not dry_run:
        final_status = (
            InvoiceStatus.POSTED
            if connector_result.success
            else InvoiceStatus.FAILED
        )
        _repo(request).set_status(invoice.id, final_status)
    return completed


def _resolve_posting_target_and_profile(
    request: Request,
    organization_id: str,
    target: Optional[PostingTarget],
    profile_id: Optional[str],
    current_user: AuthenticatedUser,
    invoice: Optional[Invoice] = None,
) -> tuple[PostingTarget, Optional[ClientProfile]]:
    if profile_id:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            READ_ROLES,
        )
        profile_target = _posting_target_for_profile(profile)
        if target is not None and profile_target != target:
            raise HTTPException(
                status_code=409,
                detail="The selected client profile does not match the posting target.",
            )
        return profile_target, profile

    if target is None:
        raise HTTPException(
            status_code=400,
            detail="Select a client profile or posting target before posting.",
        )

    return target, _resolve_posting_profile(
        request,
        organization_id,
        target,
        None,
        current_user,
        invoice,
    )


def _posting_target_for_profile(profile: ClientProfile) -> PostingTarget:
    system = (
        profile.accounting_system.value
        if hasattr(profile.accounting_system, "value")
        else str(profile.accounting_system)
    )
    try:
        return PostingTarget(system)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="The selected client profile is not connected to a live posting target.",
        ) from exc


def _posting_request_payload(
    invoice: Invoice,
    target: PostingTarget,
    dry_run: bool,
    client_profile: Optional[ClientProfile],
    retry_of: Optional[str],
) -> Dict[str, Any]:
    profile_snapshot = _client_profile_snapshot(client_profile)
    return {
        "target": target.value,
        "dry_run": dry_run,
        "retry_of": retry_of,
        "client_profile_id": client_profile.id if client_profile else None,
        "client_profile_name": client_profile.name if client_profile else None,
        "invoice_number": invoice.invoice_number,
        "source_file": invoice.source_file,
        "posting_plan": {
            "target": target.value,
            "dry_run": dry_run,
            "retry_of": retry_of,
            "profile": profile_snapshot,
            "invoice": {
                "id": invoice.id,
                "number": invoice.invoice_number,
                "supplier": invoice.supplier.name,
                "currency": invoice.currency,
                "total": invoice.total,
                "line_count": len(invoice.lines),
                "direction": invoice.direction,
            },
        },
    }


def _client_profile_snapshot(
    client_profile: Optional[ClientProfile],
) -> Optional[Dict[str, Any]]:
    if not client_profile:
        return None
    return {
        "id": client_profile.id,
        "name": client_profile.name,
        "accounting_system": (
            client_profile.accounting_system.value
            if hasattr(client_profile.accounting_system, "value")
            else str(client_profile.accounting_system)
        ),
        "is_default": client_profile.is_default,
        "settings": _redact_secrets(
            client_profile.settings.model_dump(mode="json")
        ),
        "updated_at": client_profile.updated_at.isoformat(),
    }


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        output: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            secret_markers = (
                "token",
                "secret",
                "password",
                "client_secret",
                "refresh",
            )
            if any(marker in lowered for marker in secret_markers):
                output[key] = "[redacted]" if item else ""
            else:
                output[key] = _redact_secrets(item)
        return output
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _resolve_posting_profile(
    request: Request,
    organization_id: str,
    target: PostingTarget,
    profile_id: Optional[str],
    current_user: AuthenticatedUser,
    invoice: Optional[Invoice] = None,
) -> Optional[ClientProfile]:
    if profile_id:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            READ_ROLES,
        )
        profile_system = (
            profile.accounting_system.value
            if hasattr(profile.accounting_system, "value")
            else str(profile.accounting_system)
        )
        if profile_system != target.value:
            raise HTTPException(
                status_code=409,
                detail="The selected client profile does not match the posting target.",
            )
        return profile

    profiles = _repo(request).list_client_profiles(
        organization_id,
        accounting_system=target.value,
    )
    if invoice and profiles:
        recommended = recommend_client_profiles(invoice, profiles)
        if recommended.auto_profile_id:
            matched_profile = next(
                (
                    profile
                    for profile in profiles
                    if profile.id == recommended.auto_profile_id
                ),
                None,
            )
            if matched_profile:
                return matched_profile
    return next((profile for profile in profiles if profile.is_default), None) or (
        profiles[0] if profiles else None
    )


app = create_app()
