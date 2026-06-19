"""FastAPI entry point for the EZ-Invoice SaaS foundation."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .adapters import default_adapters
from .auth import get_current_user, issue_tokens, rotate_refresh_token
from .models import (
    AuthBootstrapRequest,
    AuthenticatedUser,
    AuthTokens,
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
    OrganizationRole,
    PostingRequest,
    PostingResult,
    PostingResultCreate,
    PostingTarget,
    RefreshRequest,
    ValidationResult,
)
from .parser_service import parse_pdf_invoice
from .repository import InvoiceRepository
from .security import (
    AuthenticationError,
    hash_invitation_token,
    hash_password,
    parse_refresh_session_id,
    verify_password,
)
from .settings import ApiSettings
from .storage import LocalDocumentStorage
from .validation import validate_invoice


API_VERSION = "0.2.0"
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
        adapter = request.app.state.adapters.get(body.target)
        if adapter is None:
            raise HTTPException(status_code=400, detail="Unsupported accounting target.")

        if not body.dry_run:
            _repo(request).set_status(invoice_id, InvoiceStatus.POSTING)
        connector_result = adapter.post(invoice, dry_run=body.dry_run)
        posting = _repo(request).create_posting(
            invoice_id=invoice_id,
            target=body.target,
            success=connector_result.success,
            dry_run=body.dry_run,
            message=connector_result.message,
            external_id=connector_result.external_id,
            issues=[issue.__dict__ for issue in connector_result.issues],
            raw=connector_result.raw,
        )
        if not body.dry_run:
            final_status = (
                InvoiceStatus.POSTED if connector_result.success else InvoiceStatus.FAILED
            )
            _repo(request).set_status(invoice_id, final_status)
        return posting

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
            message=body.message,
            external_id=body.external_id,
            issues=body.issues,
            raw=body.raw,
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


app = create_app()
