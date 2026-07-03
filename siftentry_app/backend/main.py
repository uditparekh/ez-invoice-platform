"""FastAPI entry point for the SiftEntry SaaS foundation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
import sqlite3
import uuid
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .adapters import _profiled_legacy_payload, _tally_settings_from_profile, default_adapters
from .ai_parser import AiExtractorConfig, is_ai_parser_mode
from .auth import get_current_user, issue_tokens, rotate_refresh_token
from .email import EmailDeliveryError, EmailService
from .models import (
    AccountingSystem,
    AuthBootstrapRequest,
    AuthenticatedUser,
    AuthTokens,
    AiExtractionStatus,
    ClientProfile,
    ClientProfileCreate,
    ClientProfilePatch,
    ClientProfileSettings,
    ClientTrainingSample,
    CorrectionLearningSignal,
    DeleteInvoicesResult,
    HealthResponse,
    Invitation,
    InvitationAcceptRequest,
    Job,
    JobEnqueueResult,
    InvitationCreate,
    Invoice,
    InvoiceCreate,
    InvoicePatch,
    InvoiceReviewResult,
    InvoiceStatus,
    InboundEmailIntakeResult,
    InboundEmailRequest,
    LoginRequest,
    Membership,
    LearningExportBundle,
    LearningImportResult,
    Organization,
    OrganizationCreate,
    OrganizationSettings,
    OrganizationMember,
    OrganizationRole,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    PdfRetentionPolicy,
    BatchPostRequest,
    BatchPostResult,
    BatchPostSkip,
    PostingRequest,
    PostingRetryRequest,
    PostingResult,
    PostingResultCreate,
    PostingTarget,
    ProfileRecommendationResult,
    RefreshRequest,
    StorageCleanupResult,
    TallyConnectorClaimRequest,
    TallyConnectorClaimResponse,
    TallyConnectorJob,
    TallyConnectorResultRequest,
    TallyConnectorResultResponse,
    ValidationResult,
)
from .parser_service import parse_pdf_invoice
from .profile_recommendation import recommend_client_profiles
from .repository import InvoiceRepository
from .review_service import build_invoice_review
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
from ..tally_integration import build_tally_xml


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


def _profile_export_payload(profile: ClientProfile) -> ClientProfileCreate:
    """Strip identity/timestamps: a profile as a portable creation payload."""
    return ClientProfileCreate(
        name=profile.name,
        accounting_system=profile.accounting_system,
        description=profile.description,
        is_default=profile.is_default,
        settings=profile.settings,
    )


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    resolved = settings or ApiSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved
        app.state.repository = InvoiceRepository(
            resolved.database_path, database_url=resolved.database_url
        )
        app.state.storage = LocalDocumentStorage(resolved.upload_directory)
        app.state.adapters = default_adapters()
        app.state.email = EmailService(resolved)
        app.state.ai_extractor_config = AiExtractorConfig.from_settings(resolved)
        yield

    app = FastAPI(
        title="SiftEntry API",
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
        ai_status = AiExtractorConfig.from_settings(settings).status()
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
                "ai_extraction": ai_status,
            },
            "problems": problems,
        }

    @app.get(
        "/api/v1/system/ai-extraction",
        response_model=AiExtractionStatus,
        tags=["system"],
    )
    def ai_extraction_status(
        request: Request,
        current_user: CurrentUser,
    ) -> AiExtractionStatus:
        return AiExtractionStatus(**request.app.state.ai_extractor_config.status())

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
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/training-samples",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    async def upload_client_profile_training_sample(
        request: Request,
        organization_id: str,
        profile_id: str,
        file: Annotated[UploadFile, File(description="Sample invoice PDF for profile training")],
        current_user: CurrentUser,
        notes: Annotated[str, Form()] = "",
        sample_type: Annotated[str, Form()] = "invoice",
    ) -> ClientProfile:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            EDIT_ROLES,
        )
        filename = Path(file.filename or "training-sample.pdf").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="Only PDF training samples are accepted.")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded training sample is empty.")
        if len(content) > request.app.state.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="The uploaded PDF exceeds the size limit.")

        stored_path = _storage(request).save(
            organization_id,
            f"training-{profile_id}-{filename}",
            content,
        )
        settings = profile.settings.model_copy(deep=True)
        training_profile = settings.training_profile.model_copy(deep=True)
        sample = ClientTrainingSample(
            filename=filename,
            stored_path=str(stored_path),
            size_bytes=len(content),
            content_type=file.content_type or "application/pdf",
            sample_type=sample_type or "invoice",
            notes=notes,
        )
        training_profile.sample_invoices = [
            sample,
            *training_profile.sample_invoices,
        ]
        if training_profile.onboarding_status == "draft":
            training_profile.onboarding_status = "samples_added"
        training_profile.llm_ready = bool(
            training_profile.extraction_instructions.strip()
            and training_profile.expected_fields
            and len(training_profile.sample_invoices) >= 2
        )
        settings.training_profile = training_profile

        updated = _repo(request).update_client_profile(
            profile_id,
            ClientProfilePatch(settings=settings),
            actor_id=current_user.id,
        )
        if not updated:
            _storage(request).delete(stored_path)
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return updated

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

    @app.post(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/submit-review",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def submit_client_profile_review(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> ClientProfile:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            EDIT_ROLES,
        )
        settings = profile.settings.model_copy(deep=True)
        training_profile = settings.training_profile.model_copy(deep=True)
        training_profile.onboarding_status = "ready_for_admin_review"
        settings.training_profile = training_profile
        metadata = dict(settings.metadata or {})
        metadata["submitted_for_review_at"] = datetime.now(timezone.utc).isoformat()
        metadata["submitted_for_review_by"] = current_user.email
        metadata["activation_readiness"] = _client_profile_activation_issues(profile)
        settings.metadata = metadata
        updated = _repo(request).update_client_profile(
            profile_id,
            ClientProfilePatch(settings=settings),
            actor_id=current_user.id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return updated

    @app.post(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/recommend-settings",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def recommend_client_profile_settings(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> ClientProfile:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            EDIT_ROLES,
        )
        settings = _recommended_client_profile_settings(profile, current_user.email)
        updated = _repo(request).update_client_profile(
            profile_id,
            ClientProfilePatch(settings=settings),
            actor_id=current_user.id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return updated

    @app.post(
        "/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/activate",
        response_model=ClientProfile,
        tags=["client-profiles"],
    )
    def activate_client_profile(
        request: Request,
        organization_id: str,
        profile_id: str,
        current_user: CurrentUser,
    ) -> ClientProfile:
        profile = _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            MANAGE_ROLES,
        )
        issues = _client_profile_activation_issues(profile)
        blocking = [issue for issue in issues if issue.get("blocking", True)]
        if blocking:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Client profile is not ready to activate.",
                    "issues": blocking,
                },
            )
        settings = profile.settings.model_copy(deep=True)
        training_profile = settings.training_profile.model_copy(deep=True)
        training_profile.onboarding_status = "active"
        settings.training_profile = training_profile
        metadata = dict(settings.metadata or {})
        metadata["activated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["activated_by"] = current_user.email
        metadata["activation_readiness"] = issues
        settings.metadata = metadata
        updated = _repo(request).update_client_profile(
            profile_id,
            ClientProfilePatch(settings=settings),
            actor_id=current_user.id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return updated

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
        persist: bool = Query(default=True),
        client_profile_id: Optional[str] = Query(default=None),
    ) -> Invoice:
        return _process_invoice_pdf_bytes(
            request,
            organization_id=organization_id,
            filename=file.filename or "invoice.pdf",
            content=await file.read(),
            content_type=file.content_type or "application/pdf",
            parser_mode=parser_mode,
            persist=persist,
            client_profile_id=client_profile_id,
            current_user=current_user,
        )

    @app.post(
        "/api/v1/inbound/email",
        response_model=InboundEmailIntakeResult,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["inbound"],
    )
    def inbound_email_intake(
        request: Request,
        body: InboundEmailRequest,
        x_siftentry_inbound_secret: Annotated[Optional[str], Header()] = None,
    ) -> InboundEmailIntakeResult:
        settings = request.app.state.settings
        if not settings.inbound_email_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inbound email intake is not configured.",
            )
        supplied_secret = x_siftentry_inbound_secret or ""
        if not hmac.compare_digest(supplied_secret, settings.inbound_email_secret):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid inbound email secret.",
            )
        if not body.attachments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one PDF attachment is required.",
            )
        if len(body.attachments) > settings.inbound_email_max_attachments:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    "Too many email attachments. "
                    f"Limit is {settings.inbound_email_max_attachments}."
                ),
            )

        _get_organization(request, body.organization_id)
        invoices: List[Invoice] = []
        errors: List[str] = []
        for attachment in body.attachments:
            filename = Path(attachment.filename).name
            content_type = attachment.content_type or "application/pdf"
            if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
                errors.append(f"{filename}: skipped non-PDF attachment")
                continue
            try:
                content = base64.b64decode(
                    attachment.content_base64.encode("utf-8"),
                    validate=True,
                )
            except (binascii.Error, ValueError) as exc:
                errors.append(f"{filename}: invalid base64 content")
                continue
            try:
                invoices.append(
                    _process_invoice_pdf_bytes(
                        request,
                        organization_id=body.organization_id,
                        filename=filename,
                        content=content,
                        content_type=content_type,
                        parser_mode=body.parser_mode or "auto",
                        persist=True,
                        client_profile_id=body.client_profile_id,
                        current_user=None,
                        source_metadata={
                            "ingestion": {
                                "channel": "email",
                                "from_email": body.from_email,
                                "to_email": body.to_email,
                                "subject": body.subject,
                                "message_id": body.message_id,
                            }
                        },
                    )
                )
            except HTTPException as exc:
                errors.append(f"{filename}: {exc.detail}")

        return InboundEmailIntakeResult(
            organization_id=body.organization_id,
            accepted=len(invoices),
            rejected=len(errors),
            invoices=invoices,
            errors=errors,
        )

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
        document_file = _repo(request).get_active_invoice_file(invoice_id)
        source_path = Path(document_file.local_path) if document_file else Path(invoice.source_path)
        if not source_path.exists() or not source_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Invoice document is not retained or is no longer available.",
            )
        return FileResponse(
            source_path,
            media_type="application/pdf",
            filename=document_file.original_filename if document_file else invoice.source_file,
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

    @app.get(
        "/api/v1/invoices/{invoice_id}/review",
        response_model=InvoiceReviewResult,
        tags=["workflow"],
    )
    def review_invoice_endpoint(
        request: Request,
        invoice_id: str,
        current_user: CurrentUser,
        accounting_system: Optional[AccountingSystem] = Query(default=None),
    ) -> InvoiceReviewResult:
        invoice = _require_invoice(request, invoice_id, current_user, READ_ROLES)
        profiles = _repo(request).list_client_profiles(
            invoice.organization_id,
            accounting_system=(
                accounting_system.value if accounting_system is not None else None
            ),
        )
        profile_result = recommend_client_profiles(invoice, profiles)
        return build_invoice_review(invoice, profile_result)

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
        retained_files = _repo(request).list_organization_invoice_files(organization_id)
        stored_paths = [
            invoice.source_path
            for invoice in _repo(request).list_invoices(
                organization_id=organization_id,
                limit=100_000,
                offset=0,
            )
            if invoice.source_path
        ]
        stored_paths.extend(record.local_path for record in retained_files if record.local_path)
        deleted = _repo(request).delete_organization_invoices(organization_id)
        for stored_path in set(stored_paths):
            _storage(request).delete(Path(stored_path))
        return DeleteInvoicesResult(organization_id=organization_id, deleted=deleted)

    @app.post(
        "/api/v1/organizations/{organization_id}/storage/cleanup",
        response_model=StorageCleanupResult,
        tags=["invoices"],
    )
    def cleanup_organization_storage(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
    ) -> StorageCleanupResult:
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        return _cleanup_expired_documents(request, organization_id)

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

    @app.post(
        "/api/v1/organizations/{organization_id}/invoices/post-ready",
        response_model=BatchPostResult,
        tags=["workflow"],
    )
    def post_ready_invoices(
        request: Request,
        organization_id: str,
        body: BatchPostRequest,
        current_user: CurrentUser,
    ) -> BatchPostResult:
        """Batch-post every invoice in the given status (default: approved).

        Individual posting failures are recorded as failed PostingResults by the
        posting pipeline itself; configuration errors (e.g. missing profile) are
        collected into `skipped` so one bad invoice never blocks the batch.
        """
        _require_membership(request, current_user, organization_id, EDIT_ROLES)
        candidates = [
            invoice
            for invoice in _repo(request).list_invoices(
                organization_id=organization_id,
                limit=100_000,
                offset=0,
            )
            if (
                invoice.status.value
                if hasattr(invoice.status, "value")
                else str(invoice.status)
            )
            == body.status
        ]
        results: List[PostingResult] = []
        skipped: List[BatchPostSkip] = []
        for invoice in candidates:
            try:
                results.append(
                    _execute_posting(
                        request,
                        current_user,
                        invoice,
                        target=body.target,
                        client_profile_id=body.client_profile_id,
                        dry_run=body.dry_run,
                    )
                )
            except HTTPException as exc:
                skipped.append(
                    BatchPostSkip(invoice_id=invoice.id, reason=str(exc.detail))
                )
        succeeded = sum(1 for result in results if result.success)
        return BatchPostResult(
            attempted=len(candidates),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
            skipped=skipped,
        )

    @app.get(
        "/api/v1/organizations/{organization_id}/settings",
        response_model=OrganizationSettings,
        tags=["organizations"],
    )
    def get_organization_settings(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
    ) -> OrganizationSettings:
        _require_membership(request, current_user, organization_id, READ_ROLES)
        stored = _repo(request).get_organization_settings(organization_id)
        return (
            OrganizationSettings.model_validate(stored)
            if stored
            else OrganizationSettings()
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/jobs/post-ready",
        response_model=JobEnqueueResult,
        tags=["workflow"],
        status_code=202,
    )
    def enqueue_post_ready(
        request: Request,
        organization_id: str,
        body: BatchPostRequest,
        current_user: CurrentUser,
    ) -> JobEnqueueResult:
        """Async batch posting: returns immediately with a job to poll.

        The synchronous /invoices/post-ready endpoint remains for small
        batches; this is the path for slow/flaky accounting APIs — a hung
        QuickBooks call never holds an HTTP request open.
        """
        _require_membership(request, current_user, organization_id, EDIT_ROLES)
        job = _repo(request).enqueue_job(
            organization_id,
            "batch_post_ready",
            {
                "target": body.target.value if body.target else None,
                "client_profile_id": body.client_profile_id,
                "dry_run": body.dry_run,
                "status": body.status,
            },
            actor_id=current_user.id,
        )
        return JobEnqueueResult(job=job, poll_url=f"/api/v1/jobs/{job.id}")

    @app.get(
        "/api/v1/organizations/{organization_id}/jobs",
        response_model=List[Job],
        tags=["workflow"],
    )
    def list_organization_jobs(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> List[Job]:
        _require_membership(request, current_user, organization_id, READ_ROLES)
        return _repo(request).list_jobs(organization_id, limit=limit)

    @app.get("/api/v1/jobs/{job_id}", response_model=Job, tags=["workflow"])
    def get_job_status(
        request: Request,
        job_id: str,
        current_user: CurrentUser,
    ) -> Job:
        job = _repo(request).get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        _require_membership(request, current_user, job.organization_id, READ_ROLES)
        return job

    @app.get(
        "/api/v1/organizations/{organization_id}/learning/export",
        response_model=LearningExportBundle,
        tags=["organizations"],
    )
    def export_learning_bundle(
        request: Request,
        organization_id: str,
        current_user: CurrentUser,
        limit: int = Query(default=2000, ge=1, le=10000),
    ) -> LearningExportBundle:
        """One portable JSON bundle of everything the AI learns from.

        Download it as an off-platform backup; import it into a fresh
        instance (or hand it to a new AI provider) and extraction context
        continues from exactly where it left off.
        """
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        repo = _repo(request)
        signals = repo.list_correction_learning_signals(organization_id, limit=limit)
        field_counts: Dict[str, int] = {}
        for signal in signals:
            field_counts[signal.field_path] = field_counts.get(signal.field_path, 0) + 1
        profiles = repo.list_client_profiles(organization_id)
        return LearningExportBundle(
            generated_at=datetime.now(timezone.utc),
            organization_id=organization_id,
            organization_settings=repo.get_organization_settings(organization_id),
            client_profiles=[_profile_export_payload(profile) for profile in profiles],
            learning_signals=signals,
            learning_summary={
                "signal_count": len(signals),
                "field_counts": field_counts,
                "profile_count": len(profiles),
            },
        )

    @app.post(
        "/api/v1/organizations/{organization_id}/learning/import",
        response_model=LearningImportResult,
        tags=["organizations"],
    )
    def import_learning_bundle(
        request: Request,
        organization_id: str,
        body: LearningExportBundle,
        current_user: CurrentUser,
    ) -> LearningImportResult:
        """Restore a learning bundle into this organization.

        Applies organization settings and creates-or-updates client profiles
        by name (the carriers of extraction instructions, mappings, and
        training context). Historical learning signals travel in the bundle
        for reference; the live learning loop repopulates from new reviews.
        """
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        repo = _repo(request)
        notes: List[str] = []
        settings_applied = False
        if body.organization_settings:
            repo.upsert_organization_settings(
                organization_id, dict(body.organization_settings)
            )
            settings_applied = True
        existing = {
            profile.name.strip().lower(): profile
            for profile in repo.list_client_profiles(organization_id)
        }
        created = 0
        updated = 0
        for payload in body.client_profiles:
            key = payload.name.strip().lower()
            if not key:
                continue
            match = existing.get(key)
            if match:
                repo.update_client_profile(
                    match.id,
                    ClientProfilePatch(
                        name=payload.name,
                        accounting_system=payload.accounting_system,
                        description=payload.description,
                        is_default=payload.is_default,
                        settings=payload.settings,
                    ),
                    actor_id=current_user.id,
                )
                updated += 1
            else:
                repo.create_client_profile(
                    organization_id, payload, actor_id=current_user.id
                )
                created += 1
        if body.learning_signals:
            notes.append(
                f"{len(body.learning_signals)} historical learning signals received "
                "for reference; live learning repopulates from new reviews."
            )
        return LearningImportResult(
            organization_settings_applied=settings_applied,
            profiles_created=created,
            profiles_updated=updated,
            learning_signals_received=len(body.learning_signals),
            notes=notes,
        )

    @app.put(
        "/api/v1/organizations/{organization_id}/settings",
        response_model=OrganizationSettings,
        tags=["organizations"],
    )
    def put_organization_settings(
        request: Request,
        organization_id: str,
        body: OrganizationSettings,
        current_user: CurrentUser,
    ) -> OrganizationSettings:
        _require_membership(request, current_user, organization_id, MANAGE_ROLES)
        saved = _repo(request).upsert_organization_settings(
            organization_id,
            body.model_dump(),
        )
        return OrganizationSettings.model_validate(saved)

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

    @app.post(
        "/api/v1/connectors/tally/jobs/claim",
        response_model=TallyConnectorClaimResponse,
        tags=["connectors"],
    )
    def claim_tally_connector_jobs(
        request: Request,
        body: TallyConnectorClaimRequest,
        authorization: Optional[str] = Header(default=None),
        x_siftentry_connector_token: Optional[str] = Header(default=None),
    ) -> TallyConnectorClaimResponse:
        profile = _require_tally_connector_profile(
            request,
            body.workspace_id,
            authorization,
            x_siftentry_connector_token,
        )
        invoices = _repo(request).list_connector_ready_invoices(
            organization_id=profile.organization_id,
            client_profile_id=profile.id,
            target=PostingTarget.TALLY,
            limit=body.limit,
        )
        jobs: List[TallyConnectorJob] = []
        for invoice in invoices:
            request_payload = _posting_request_payload(
                invoice=invoice,
                target=PostingTarget.TALLY,
                dry_run=body.dry_run,
                client_profile=profile,
                retry_of=None,
            )
            posting = _repo(request).start_posting(
                invoice_id=invoice.id,
                target=PostingTarget.TALLY,
                dry_run=body.dry_run,
                actor_id=f"tally-connector:{body.workspace_id}",
                client_profile_id=profile.id,
                request_payload=request_payload,
            )
            if not body.dry_run:
                _repo(request).set_status(invoice.id, InvoiceStatus.POSTING)
            jobs.append(
                _tally_connector_job(
                    invoice=invoice,
                    posting=posting,
                    profile=profile,
                    workspace_id=body.workspace_id,
                    posting_plan=request_payload.get("posting_plan", {}),
                )
            )
        return TallyConnectorClaimResponse(
            workspace_id=body.workspace_id,
            jobs=jobs,
        )

    @app.post(
        "/api/v1/connectors/tally/jobs/results",
        response_model=TallyConnectorResultResponse,
        tags=["connectors"],
    )
    def submit_tally_connector_results(
        request: Request,
        body: TallyConnectorResultRequest,
        authorization: Optional[str] = Header(default=None),
        x_siftentry_connector_token: Optional[str] = Header(default=None),
    ) -> TallyConnectorResultResponse:
        profile = _require_tally_connector_profile(
            request,
            body.workspace_id,
            authorization,
            x_siftentry_connector_token,
        )
        postings: List[PostingResult] = []
        errors: List[str] = []
        for item in body.results:
            posting = _repo(request).get_posting(item.posting_id)
            if not posting:
                errors.append(f"Posting {item.posting_id} was not found.")
                continue
            if (
                posting.organization_id != profile.organization_id
                or posting.client_profile_id != profile.id
                or PostingTarget(posting.target) != PostingTarget.TALLY
                or posting.invoice_id != item.invoice_id
            ):
                errors.append(f"Posting {item.posting_id} does not belong to this connector.")
                continue
            response_payload = {
                "success": item.success,
                "message": item.message,
                "external_id": item.external_id,
                "raw": item.raw,
                "posting_plan": posting.request_payload.get("posting_plan", {}),
                "workspace_id": body.workspace_id,
            }
            completed = _repo(request).complete_posting(
                posting_id=posting.id,
                success=item.success,
                message=item.message or ("Posted to Tally" if item.success else "Tally posting failed."),
                external_id=item.external_id,
                issues=[] if item.success else [{"code": "tally_connector", "message": item.message}],
                raw=item.raw,
                response_payload=response_payload,
            )
            if not posting.dry_run:
                _repo(request).set_status(
                    posting.invoice_id,
                    InvoiceStatus.POSTED if item.success else InvoiceStatus.FAILED,
                )
            postings.append(completed)
        return TallyConnectorResultResponse(
            success=not errors,
            workspace_id=body.workspace_id,
            accepted=len(postings),
            rejected=len(errors),
            postings=postings,
            errors=errors,
        )

    return app


def _repo(request: Request) -> InvoiceRepository:
    return request.app.state.repository


def _storage(request: Request) -> LocalDocumentStorage:
    return request.app.state.storage


def _process_invoice_pdf_bytes(
    request: Request,
    *,
    organization_id: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
    parser_mode: str = "auto",
    persist: bool = True,
    client_profile_id: Optional[str] = None,
    current_user: Optional[AuthenticatedUser] = None,
    source_metadata: Optional[Dict[str, Any]] = None,
) -> Invoice:
    if current_user is not None:
        _require_membership(request, current_user, organization_id, EDIT_ROLES)

    organization = _get_organization(request, organization_id)
    safe_filename = Path(filename or "invoice.pdf").name
    if not safe_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF invoices are accepted.")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if len(content) > request.app.state.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The uploaded PDF exceeds the size limit.")

    client_profile = _resolve_parser_profile(
        request,
        organization_id,
        client_profile_id,
        parser_mode,
        current_user,
    )
    correction_signals = (
        _repo(request).list_correction_learning_signals(organization_id, limit=50)
        if is_ai_parser_mode(parser_mode)
        else []
    )

    retention_policy, retention_until = _resolve_pdf_retention(
        request,
        client_profile,
    )
    should_store_pdf = persist and retention_policy != PdfRetentionPolicy.DO_NOT_STORE.value
    stored_path: Optional[Path] = None
    file_hash = hashlib.sha256(content).hexdigest()
    if should_store_pdf:
        stored_path = _storage(request).save(organization_id, safe_filename, content)

    try:
        parsed = parse_pdf_invoice(
            filename=safe_filename,
            pdf_bytes=content,
            organization_id=organization_id,
            legal_names=organization.legal_names or [organization.name],
            source_path=str(stored_path or ""),
            parser_mode=parser_mode,
            client_profile=client_profile,
            correction_signals=correction_signals,
            ai_config=request.app.state.ai_extractor_config,
        )
        if source_metadata:
            parsed.raw_payload = {**parsed.raw_payload, **source_metadata}
        if persist:
            invoice = _repo(request).create_invoice(parsed)
            if stored_path:
                _repo(request).create_invoice_file(
                    organization_id=organization_id,
                    invoice_id=invoice.id,
                    original_filename=safe_filename,
                    content_type=content_type or "application/pdf",
                    storage_backend="local",
                    storage_key=_storage(request).storage_key(stored_path),
                    local_path=str(stored_path),
                    sha256_hash=file_hash,
                    size_bytes=len(content),
                    retention_policy=retention_policy,
                    retention_until=retention_until,
                )
                invoice = _repo(request).get_invoice(invoice.id) or invoice
            return invoice
        now = datetime.now(timezone.utc)
        return Invoice(
            id=f"preview-{uuid.uuid4()}",
            created_at=now,
            updated_at=now,
            **parsed.model_dump(),
        )
    except ValueError as exc:
        if stored_path:
            _storage(request).delete(stored_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        if stored_path:
            _storage(request).delete(stored_path)
        raise
    except Exception as exc:
        if stored_path:
            _storage(request).delete(stored_path)
        raise HTTPException(status_code=500, detail=f"Invoice processing failed: {exc}") from exc


def _resolve_pdf_retention(
    request: Request,
    client_profile: Optional[ClientProfile],
) -> tuple[str, Optional[datetime]]:
    settings = request.app.state.settings
    policy = str(settings.default_pdf_retention_policy or "review_window").strip().lower()
    days = int(settings.default_pdf_retention_days or 3)
    if client_profile is not None:
        profile_settings = client_profile.settings
        policy = str(
            profile_settings.pdf_retention_policy
            or PdfRetentionPolicy.REVIEW_WINDOW.value
        ).strip().lower()
        days = int(profile_settings.pdf_retention_days or days)

    valid_policies = {item.value for item in PdfRetentionPolicy}
    if policy not in valid_policies:
        policy = PdfRetentionPolicy.REVIEW_WINDOW.value

    if policy == PdfRetentionPolicy.DO_NOT_STORE.value:
        return policy, None
    if policy == PdfRetentionPolicy.RETAIN_UNTIL_DELETED.value:
        return policy, None
    if policy == PdfRetentionPolicy.EXTENDED_90_DAYS.value:
        days = max(days, 90)
    else:
        days = max(days, 1)
    return policy, datetime.now(timezone.utc) + timedelta(days=days)


def _cleanup_expired_documents(
    request: Request,
    organization_id: str,
) -> StorageCleanupResult:
    now = datetime.now(timezone.utc)
    expired = _repo(request).list_expired_invoice_files(
        now=now,
        organization_id=organization_id,
    )
    deleted = 0
    errors: List[str] = []
    for record in expired:
        try:
            if record.local_path:
                _storage(request).delete(Path(record.local_path))
            _repo(request).mark_invoice_file_deleted(record.id, deleted_at=now)
            deleted += 1
        except Exception as exc:  # pragma: no cover - defensive cleanup path
            errors.append(f"{record.original_filename}: {exc}")
    return StorageCleanupResult(
        organization_id=organization_id,
        expired_files=len(expired),
        deleted_files=deleted,
        errors=errors,
    )


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


def _require_tally_connector_profile(
    request: Request,
    workspace_id: str,
    authorization: Optional[str],
    connector_token_header: Optional[str],
) -> ClientProfile:
    supplied_token = _connector_token_from_headers(
        authorization,
        connector_token_header,
    )
    if not supplied_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Connector token is required.",
        )
    for profile in _repo(request).list_client_profiles_by_system(AccountingSystem.TALLY.value):
        connection_settings = profile.settings.connection_settings or {}
        saved_workspace_id = str(connection_settings.get("workspace_id") or "").strip()
        saved_token = str(connection_settings.get("connector_token") or "").strip()
        connector_enabled = bool(connection_settings.get("connector_enabled", True))
        if (
            connector_enabled
            and saved_workspace_id == workspace_id
            and saved_token
            and hmac.compare_digest(saved_token, supplied_token)
        ):
            return profile
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Connector workspace or token was not accepted.",
    )


def _connector_token_from_headers(
    authorization: Optional[str],
    connector_token_header: Optional[str],
) -> str:
    if connector_token_header:
        return connector_token_header.strip()
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _tally_connector_job(
    invoice: Invoice,
    posting: PostingResult,
    profile: ClientProfile,
    workspace_id: str,
    posting_plan: Dict[str, Any],
) -> TallyConnectorJob:
    settings = _tally_settings_from_profile(profile) or {}
    xml = build_tally_xml(
        _profiled_legacy_payload(invoice, profile),
        settings=settings,
        classifier=None,
    )
    return TallyConnectorJob(
        posting_id=posting.id,
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        source_file=invoice.source_file,
        dry_run=posting.dry_run,
        client_profile_id=profile.id,
        workspace_id=workspace_id,
        company_name=str(settings.get("company") or profile.settings.company_name),
        tally_url=str(settings.get("url") or "http://localhost:9000"),
        xml=xml,
        posting_plan=posting_plan,
    )


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


def _client_profile_activation_issues(profile: ClientProfile) -> List[Dict[str, Any]]:
    settings = profile.settings
    system = (
        profile.accounting_system.value
        if hasattr(profile.accounting_system, "value")
        else str(profile.accounting_system)
    )
    issues: List[Dict[str, Any]] = []

    def issue(code: str, message: str, field: str, blocking: bool = True) -> None:
        issues.append(
            {
                "code": code,
                "message": message,
                "field": field,
                "blocking": blocking,
            }
        )

    if not profile.name.strip():
        issue("profile_name_missing", "Profile name is required.", "name")
    if not settings.country_code.strip():
        issue("country_missing", "Country is required for profile recommendation.", "settings.country_code")
    if not settings.default_currency.strip():
        issue("currency_missing", "Default currency is required.", "settings.default_currency")

    if system == AccountingSystem.TALLY.value:
        _tally_activation_issues(settings, issue)
    elif system == AccountingSystem.QUICKBOOKS.value:
        connection = settings.connection_settings or {}
        if not str(connection.get("environment") or "").strip():
            issue("quickbooks_environment_missing", "QuickBooks environment is required.", "settings.connection_settings.environment")
    elif system == AccountingSystem.ZOHO_BOOKS.value:
        connection = settings.connection_settings or {}
        if not str(connection.get("organization_id") or "").strip():
            issue(
                "zoho_organization_missing",
                "Zoho organization ID is recommended before live posting.",
                "settings.connection_settings.organization_id",
                blocking=False,
            )

    samples = settings.training_profile.sample_invoices
    if len(samples) < 1:
        issue(
            "training_samples_missing",
            "Upload at least one sample invoice before activating this profile.",
            "settings.training_profile.sample_invoices",
            blocking=False,
        )
    if not settings.training_profile.extraction_instructions.strip():
        issue(
            "extraction_instructions_missing",
            "Add parser instructions so future AI/OCR extraction has client context.",
            "settings.training_profile.extraction_instructions",
            blocking=False,
        )
    return issues


def _tally_activation_issues(
    settings: ClientProfileSettings,
    issue,
) -> None:
    if not settings.company_name.strip():
        issue("tally_company_missing", "Exact Tally company name is required.", "settings.company_name")
    if not settings.voucher_type.strip():
        issue("tally_voucher_type_missing", "Tally voucher type is required.", "settings.voucher_type")
    if not settings.purchase_ledger.strip():
        issue("tally_purchase_ledger_missing", "Exact Tally purchase ledger is required.", "settings.purchase_ledger")

    tax_mode = (settings.tax_mode or "").lower()
    tax_settings = settings.tax_settings or {}
    igst_ledger = _profile_tax_setting(tax_settings, "igst_ledger", "input_igst_ledger") or settings.tax_ledger
    cgst_ledger = _profile_tax_setting(tax_settings, "cgst_ledger", "input_cgst_ledger") or settings.tax_ledger
    sgst_ledger = _profile_tax_setting(tax_settings, "sgst_ledger", "input_sgst_ledger") or settings.tax_ledger
    if tax_mode in {"gst_auto", "gst_igst"} and not igst_ledger.strip():
        issue("tally_igst_ledger_missing", "IGST ledger is required for India GST/IGST posting.", "settings.tax_ledger")
    if tax_mode == "gst_cgst_sgst":
        if not cgst_ledger.strip():
            issue("tally_cgst_ledger_missing", "CGST ledger is required for CGST/SGST posting.", "settings.tax_settings.cgst_ledger")
        if not sgst_ledger.strip():
            issue("tally_sgst_ledger_missing", "SGST ledger is required for CGST/SGST posting.", "settings.tax_settings.sgst_ledger")

    posting_mode = str(settings.posting_mode or "").lower()
    if posting_mode == "item_invoice":
        if not settings.stock_item_name.strip() and not settings.item_mappings:
            issue("tally_stock_item_missing", "Item Invoice mode needs an exact stock item or item mapping.", "settings.stock_item_name")
        if not settings.stock_item_uom.strip():
            issue("tally_stock_uom_missing", "Item Invoice mode needs the exact Tally UOM.", "settings.stock_item_uom")
        if not settings.stock_item_hsn.strip():
            issue(
                "tally_stock_hsn_missing",
                "HSN/SAC is recommended for India Item Invoice GST validation.",
                "settings.stock_item_hsn",
                blocking=False,
            )

    expectations = " ".join(
        [
            settings.training_profile.posting_expectations,
            settings.training_profile.extraction_instructions,
            " ".join(settings.training_profile.validation_rules),
        ]
    ).lower()
    if "tcs" in expectations and not settings.tcs_ledger.strip():
        issue("tally_tcs_ledger_missing", "TCS is mentioned in onboarding, so the exact TCS ledger is required.", "settings.tcs_ledger")
    if ("round off" in expectations or "round-off" in expectations or "roundoff" in expectations) and not settings.round_off_ledger.strip():
        issue("tally_round_off_ledger_missing", "Round-off is mentioned in onboarding, so the exact round-off ledger is required.", "settings.round_off_ledger")
    if "godown" in expectations and not settings.godown_name.strip():
        issue(
            "tally_godown_missing",
            "Godown/location is mentioned in onboarding. Set it or confirm the client does not use godowns.",
            "settings.godown_name",
            blocking=False,
        )


def _profile_tax_setting(settings: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        for candidate in (key, key.lower(), key.upper()):
            value = str(settings.get(candidate) or "").strip()
            if value:
                return value
    return ""


def _recommended_client_profile_settings(
    profile: ClientProfile,
    actor_email: str,
) -> ClientProfileSettings:
    settings = profile.settings.model_copy(deep=True)
    training_profile = settings.training_profile.model_copy(deep=True)
    sample_text = " ".join(
        " ".join(
            [
                sample.filename,
                sample.sample_type,
                sample.notes,
            ]
        )
        for sample in training_profile.sample_invoices
    )
    context = " ".join(
        [
            profile.name,
            profile.description,
            str(profile.accounting_system),
            settings.company_name,
            training_profile.business_process,
            training_profile.invoice_volume,
            training_profile.extraction_instructions,
            training_profile.posting_expectations,
            training_profile.exception_examples,
            " ".join(training_profile.expected_fields),
            " ".join(training_profile.accounting_exports),
            " ".join(training_profile.validation_rules),
            sample_text,
        ]
    ).lower()

    recommendations: List[str] = []
    missing_fields: List[str] = []
    tax_settings = dict(settings.tax_settings or {})

    india_terms = ("gst", "gstin", "hsn", "sac", "igst", "cgst", "sgst", "tcs")
    if any(term in context for term in india_terms):
        settings.country_code = "IN"
        settings.country_name = "India"
        settings.default_currency = "INR"
        settings.invoice_format = "gst_einvoice"
        settings.tax_registration_label = "GSTIN"
        tax_settings["country_code"] = "IN"
        tax_settings["default_currency"] = "INR"
        recommendations.append("Detected India GST invoice context.")

        has_cgst_sgst = "cgst" in context or "sgst" in context
        has_igst = "igst" in context
        if has_cgst_sgst:
            settings.tax_mode = "gst_cgst_sgst"
            tax_settings["gst_mode"] = "cgst_sgst"
            recommendations.append("Recommended CGST/SGST split posting.")
        elif has_igst:
            settings.tax_mode = "gst_igst"
            tax_settings["gst_mode"] = "igst"
            recommendations.append("Recommended IGST posting.")
        else:
            settings.tax_mode = "gst_auto"
            tax_settings["gst_mode"] = "auto"
            recommendations.append("Recommended GST auto-detection.")

    system = (
        profile.accounting_system.value
        if hasattr(profile.accounting_system, "value")
        else str(profile.accounting_system)
    )
    tally_context = system == AccountingSystem.TALLY.value
    item_invoice_terms = (
        "item invoice",
        "stock item",
        "stock",
        "hsn",
        "godown",
        "quantity",
        "uom",
    )
    if tally_context and any(term in context for term in item_invoice_terms):
        settings.posting_mode = "item_invoice"
        recommendations.append("Recommended Tally Item Invoice mode.")
    elif tally_context and not str(settings.posting_mode or "").strip():
        settings.posting_mode = "accounting_voucher"

    if tally_context:
        if "tcs" in context and not settings.tcs_ledger.strip():
            missing_fields.append("Exact TCS ledger name")
        if (
            "round off" in context
            or "round-off" in context
            or "roundoff" in context
        ) and not settings.round_off_ledger.strip():
            missing_fields.append("Exact round-off ledger name")
        if "godown" in context and not settings.godown_name.strip():
            missing_fields.append("Godown/location name, or confirmation that no godown is used")
        if str(settings.posting_mode or "").lower() == "item_invoice":
            if not settings.stock_item_name.strip() and not settings.item_mappings:
                missing_fields.append("Exact Tally stock item or item mapping")
            if not settings.stock_item_uom.strip():
                missing_fields.append("Exact Tally UOM")
            if settings.country_code == "IN" and not settings.stock_item_hsn.strip():
                missing_fields.append("HSN/SAC for the mapped stock item")
        if settings.tax_mode == "gst_igst" and not (
            _profile_tax_setting(tax_settings, "igst_ledger", "input_igst_ledger")
            or settings.tax_ledger
        ):
            missing_fields.append("Exact IGST ledger name")
        if settings.tax_mode == "gst_cgst_sgst":
            if not _profile_tax_setting(tax_settings, "cgst_ledger", "input_cgst_ledger"):
                missing_fields.append("Exact CGST ledger name")
            if not _profile_tax_setting(tax_settings, "sgst_ledger", "input_sgst_ledger"):
                missing_fields.append("Exact SGST ledger name")

    if system == AccountingSystem.QUICKBOOKS.value:
        settings.posting_mode = "supplier_bill"
        recommendations.append("Recommended QuickBooks Supplier Bill posting.")
    elif system == AccountingSystem.ZOHO_BOOKS.value:
        settings.posting_mode = "supplier_bill"
        recommendations.append("Recommended Zoho Books Bill posting.")
    elif system in {
        AccountingSystem.COUPA.value,
        AccountingSystem.NETSUITE.value,
        AccountingSystem.SAP.value,
        AccountingSystem.EXCEL.value,
    }:
        settings.posting_mode = "export_package"

    training_profile.onboarding_status = (
        "active"
        if training_profile.onboarding_status == "active"
        else "recommendations_generated"
    )
    settings.training_profile = training_profile
    settings.tax_settings = tax_settings
    metadata = dict(settings.metadata or {})
    metadata["recommendations_generated_at"] = datetime.now(timezone.utc).isoformat()
    metadata["recommendations_generated_by"] = actor_email
    metadata["recommendation_summary"] = recommendations or [
        "No strong country or tax pattern detected. Kept current settings."
    ]
    metadata["recommendation_missing_fields"] = list(dict.fromkeys(missing_fields))
    metadata["activation_readiness"] = _client_profile_activation_issues(
        profile.model_copy(update={"settings": settings})
    )
    settings.metadata = metadata
    return settings


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


def _resolve_parser_profile(
    request: Request,
    organization_id: str,
    profile_id: Optional[str],
    parser_mode: str,
    current_user: Optional[AuthenticatedUser],
) -> Optional[ClientProfile]:
    if profile_id:
        if current_user is None:
            profile = _repo(request).get_client_profile(profile_id)
            if not profile or profile.organization_id != organization_id:
                raise HTTPException(status_code=404, detail="Client profile not found.")
            return profile
        return _require_client_profile(
            request,
            organization_id,
            profile_id,
            current_user,
            READ_ROLES,
        )
    if not is_ai_parser_mode(parser_mode):
        return None

    profiles = _repo(request).list_client_profiles(organization_id)
    return next((profile for profile in profiles if profile.is_default), None) or (
        profiles[0] if profiles else None
    )


app = create_app()
