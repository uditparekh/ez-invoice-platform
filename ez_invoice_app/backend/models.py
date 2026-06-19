"""Universal API models shared by invoice workflows and accounting adapters."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceStatus(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    VALIDATED = "validated"
    APPROVED = "approved"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"


class PostingTarget(str, Enum):
    QUICKBOOKS = "quickbooks"
    TALLY = "tally"
    ZOHO_BOOKS = "zoho_books"


class OrganizationRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    VIEWER = "viewer"


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_names: List[str] = Field(default_factory=list)
    default_currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("legal_names")
    @classmethod
    def clean_legal_names(cls, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class Organization(OrganizationCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class User(BaseModel):
    id: str
    email: str
    full_name: str = ""
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class Membership(BaseModel):
    organization_id: str
    organization_name: str
    role: OrganizationRole
    created_at: datetime


class AuthenticatedUser(User):
    memberships: List[Membership] = Field(default_factory=list)


class AuthBootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    full_name: str = Field(default="", max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    legal_names: List[str] = Field(default_factory=list)
    default_currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("default_currency")
    @classmethod
    def normalize_bootstrap_currency(cls, value: str) -> str:
        return value.strip().upper()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=1000)


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: OrganizationRole

    @field_validator("email")
    @classmethod
    def normalize_invitation_email(cls, value: str) -> str:
        return value.strip().lower()


class Invitation(BaseModel):
    id: str
    organization_id: str
    email: str
    role: OrganizationRole
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime
    invitation_token: Optional[str] = None


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=1000)
    password: str = Field(min_length=12, max_length=256)
    full_name: str = Field(default="", max_length=200)


class Party(BaseModel):
    name: str = ""
    tax_id: str = ""
    address: List[str] = Field(default_factory=list)
    email: str = ""
    phone: str = ""


class ExtractionEvidence(BaseModel):
    field: str
    value: str = ""
    page: Optional[int] = None
    snippet: str = ""
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class InvoiceLine(BaseModel):
    id: Optional[str] = None
    line_number: int = Field(default=1, ge=1)
    description: str = ""
    quantity: float = 0
    uom: str = ""
    unit_price: float = 0
    net_amount: float = 0
    tax_amount: float = 0
    total_amount: float = 0
    hsn_sac: str = ""
    category: str = ""
    gl_code: str = ""
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class InvoiceCreate(BaseModel):
    organization_id: str
    source_file: str
    source_path: str = ""
    parser: str = "Generic"
    extraction_engine: str = ""
    page_count: int = Field(default=1, ge=1)
    status: InvoiceStatus = InvoiceStatus.EXTRACTED
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    purchase_order: str = ""
    currency: str = "INR"
    subtotal: float = 0
    tax_total: float = 0
    total: float = 0
    supplier: Party = Field(default_factory=Party)
    customer: Party = Field(default_factory=Party)
    direction: str = "inbound"
    lines: List[InvoiceLine] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    evidence: List[ExtractionEvidence] = Field(default_factory=list)
    validation_issues: List[str] = Field(default_factory=list)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_invoice_currency(cls, value: str) -> str:
        return (value or "INR").strip().upper()


class Invoice(InvoiceCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class InvoicePatch(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    purchase_order: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    total: Optional[float] = None
    supplier: Optional[Party] = None
    customer: Optional[Party] = None
    direction: Optional[str] = None
    lines: Optional[List[InvoiceLine]] = None

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value is not None else None


class ValidationResult(BaseModel):
    invoice_id: str
    valid: bool
    status: InvoiceStatus
    issues: List[str] = Field(default_factory=list)


class PostingRequest(BaseModel):
    target: PostingTarget
    dry_run: bool = False


class PostingResultCreate(BaseModel):
    target: PostingTarget
    success: bool
    dry_run: bool = False
    message: str
    external_id: Optional[str] = None
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


class PostingResult(BaseModel):
    id: str
    invoice_id: str
    target: PostingTarget
    success: bool
    dry_run: bool = False
    message: str
    external_id: Optional[str] = None
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DeleteInvoicesResult(BaseModel):
    organization_id: str
    deleted: int
