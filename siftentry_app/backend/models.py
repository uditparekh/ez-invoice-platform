"""Universal API models shared by invoice workflows and accounting adapters."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


class PostingStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AccountingSystem(str, Enum):
    QUICKBOOKS = "quickbooks"
    TALLY = "tally"
    ZOHO_BOOKS = "zoho_books"
    COUPA = "coupa"
    NETSUITE = "netsuite"
    SAP = "sap"
    EXCEL = "excel"
    CUSTOM = "custom"


class ProfilePostingMode(str, Enum):
    ACCOUNTING_VOUCHER = "accounting_voucher"
    ITEM_INVOICE = "item_invoice"
    SUPPLIER_BILL = "supplier_bill"
    EXPORT_PACKAGE = "export_package"
    CUSTOM = "custom"


class PdfRetentionPolicy(str, Enum):
    REVIEW_WINDOW = "review_window"
    EXTENDED_90_DAYS = "extended_90_days"
    RETAIN_UNTIL_DELETED = "retain_until_deleted"
    DO_NOT_STORE = "do_not_store"


class OrganizationRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    VIEWER = "viewer"


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_names: List[str] = Field(default_factory=list)
    default_currency: str = Field(default="USD", min_length=3, max_length=3)

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


class ClientProfileItemMapping(BaseModel):
    source_description_contains: str = ""
    source_hsn_sac: str = ""
    target_item_name: str = ""
    target_uom: str = ""
    purchase_ledger: str = ""
    tax_ledger: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "source_description_contains",
        "source_hsn_sac",
        "target_item_name",
        "target_uom",
        "purchase_ledger",
        "tax_ledger",
    )
    @classmethod
    def clean_mapping_text(cls, value: str) -> str:
        return value.strip()


class ClientTrainingSample(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    stored_path: str = ""
    size_bytes: int = 0
    content_type: str = "application/pdf"
    sample_type: str = "invoice"
    status: str = "uploaded"
    notes: str = ""
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fields_confirmed: bool = False

    @field_validator(
        "filename",
        "stored_path",
        "content_type",
        "sample_type",
        "status",
        "notes",
    )
    @classmethod
    def clean_sample_text(cls, value: str) -> str:
        return value.strip()


class ClientTrainingProfile(BaseModel):
    onboarding_status: str = "draft"
    business_process: str = "inbound_ap"
    invoice_volume: str = ""
    expected_fields: List[str] = Field(
        default_factory=lambda: [
            "invoice_number",
            "supplier",
            "invoice_date",
            "due_date",
            "currency",
            "subtotal",
            "tax_total",
            "total",
            "line_items",
        ]
    )
    accounting_exports: List[str] = Field(default_factory=list)
    sample_invoices: List[ClientTrainingSample] = Field(default_factory=list)
    extraction_instructions: str = ""
    validation_rules: List[str] = Field(default_factory=list)
    posting_expectations: str = ""
    exception_examples: str = ""
    llm_ready: bool = False
    llm_policy: str = "review_only"

    @field_validator(
        "onboarding_status",
        "business_process",
        "invoice_volume",
        "extraction_instructions",
        "posting_expectations",
        "exception_examples",
        "llm_policy",
    )
    @classmethod
    def clean_training_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("expected_fields", "accounting_exports", "validation_rules")
    @classmethod
    def clean_training_list(cls, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ClientProfileSettings(BaseModel):
    company_name: str = ""
    environment: str = "production"
    connection_settings: Dict[str, Any] = Field(default_factory=dict)
    country_code: str = "US"
    country_name: str = "United States"
    default_currency: str = "USD"
    invoice_format: str = "auto"
    tax_mode: str = "auto"
    tax_registration_label: str = ""
    default_parser: str = "auto"
    direction: str = "inbound"
    posting_mode: ProfilePostingMode = ProfilePostingMode.ACCOUNTING_VOUCHER
    voucher_type: str = "Purchase"
    purchase_ledger: str = ""
    tax_ledger: str = ""
    tcs_ledger: str = ""
    round_off_ledger: str = ""
    stock_item_name: str = ""
    stock_item_hsn: str = ""
    stock_item_uom: str = ""
    godown_name: str = ""
    pdf_retention_policy: PdfRetentionPolicy = PdfRetentionPolicy.REVIEW_WINDOW
    pdf_retention_days: int = Field(default=3, ge=0, le=3650)
    paid_pdf_storage: bool = False
    item_mappings: List[ClientProfileItemMapping] = Field(default_factory=list)
    tax_settings: Dict[str, Any] = Field(default_factory=dict)
    training_profile: ClientTrainingProfile = Field(default_factory=ClientTrainingProfile)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True, extra="allow")

    @field_validator(
        "company_name",
        "environment",
        "country_code",
        "country_name",
        "invoice_format",
        "tax_mode",
        "tax_registration_label",
        "default_parser",
        "direction",
        "voucher_type",
        "purchase_ledger",
        "tax_ledger",
        "tcs_ledger",
        "round_off_ledger",
        "stock_item_name",
        "stock_item_hsn",
        "stock_item_uom",
        "godown_name",
    )
    @classmethod
    def clean_settings_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("country_code")
    @classmethod
    def normalize_profile_country_code(cls, value: str) -> str:
        return value.strip().upper() or "US"

    @field_validator("default_currency")
    @classmethod
    def normalize_profile_currency(cls, value: str) -> str:
        return value.strip().upper() or "USD"


class ClientProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    accounting_system: AccountingSystem
    description: str = Field(default="", max_length=500)
    is_default: bool = False
    settings: ClientProfileSettings = Field(default_factory=ClientProfileSettings)

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("name", "description")
    @classmethod
    def clean_profile_text(cls, value: str) -> str:
        return value.strip()


class ClientProfilePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    accounting_system: Optional[AccountingSystem] = None
    description: Optional[str] = Field(default=None, max_length=500)
    is_default: Optional[bool] = None
    settings: Optional[ClientProfileSettings] = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("name", "description")
    @classmethod
    def clean_optional_profile_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class ClientProfile(ClientProfileCreate):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class User(BaseModel):
    id: str
    email: str
    full_name: str = ""
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class OrganizationMember(BaseModel):
    user_id: str
    email: str
    full_name: str = ""
    role: OrganizationRole
    is_active: bool = True
    member_since: datetime
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
    default_currency: str = Field(default="USD", min_length=3, max_length=3)

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


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_reset_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=1000)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetResponse(BaseModel):
    message: str
    reset_token: Optional[str] = None
    expires_at: Optional[datetime] = None


class CorrectionLearningSignal(BaseModel):
    id: str
    invoice_id: str
    invoice_number: str
    supplier_name: str
    field_path: str
    old_value: Any
    new_value: Any
    actor_id: str
    actor_email: str = ""
    created_at: datetime


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
    currency: str = "USD"
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
        return (value or "USD").strip().upper()


class Invoice(InvoiceCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    document_retention: Optional["InvoiceDocumentRetention"] = None

    model_config = ConfigDict(use_enum_values=True)


class InvoiceDocumentRetention(BaseModel):
    file_id: str
    retained: bool
    retention_policy: PdfRetentionPolicy
    retention_until: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    sha256_hash: str = ""
    size_bytes: int = 0
    storage_backend: str = "local"

    model_config = ConfigDict(use_enum_values=True)


class InvoicePatch(BaseModel):
    invoice_number: Optional[str] = None
    # Review Workspace vendor-memory toggle: when False, corrections from this
    # patch are NOT recorded as learning signals. Defaults to learning on.
    learn_vendor_memory: Optional[bool] = None
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
    target: Optional[PostingTarget] = None
    dry_run: bool = False
    client_profile_id: Optional[str] = None


class PostingRetryRequest(BaseModel):
    dry_run: Optional[bool] = None


class OrganizationSettings(BaseModel):
    """Workspace-level defaults surfaced in Settings (org-scoped, admin-managed)."""

    default_currency: str = Field(default="USD", min_length=3, max_length=3)
    default_country: str = "auto"
    primary_accounting_system: str = "tally"
    data_retention: str = "review_window"
    notifications: Dict[str, bool] = Field(
        default_factory=lambda: {"approvals": True, "failures": True, "digest": False}
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("default_currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.strip().upper()


class BatchPostRequest(BaseModel):
    target: Optional[PostingTarget] = None
    client_profile_id: Optional[str] = None
    dry_run: bool = False
    status: str = "approved"


class BatchPostSkip(BaseModel):
    invoice_id: str
    reason: str


class Job(BaseModel):
    """Background job record — the seam where slow work (posting to
    accounting APIs, LLM extraction) leaves the request path."""

    id: str
    organization_id: str
    kind: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "queued"  # queued | running | done | failed
    attempts: int = 0
    result: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    actor_id: str = ""
    created_at: datetime
    updated_at: datetime


class JobEnqueueResult(BaseModel):
    job: Job
    poll_url: str


class LearningExportBundle(BaseModel):
    """Portable backup of everything the AI learns from — provider-independent.

    This is the same knowledge injected into whichever AI provider is active,
    so migrating brains (or instances) means exporting here and importing
    there; the new model picks up exactly where the old one left off.
    """

    schema_version: str = "siftentry_learning_v1"
    generated_at: datetime
    organization_id: str
    organization_settings: Dict[str, Any] = Field(default_factory=dict)
    client_profiles: List[ClientProfileCreate] = Field(default_factory=list)
    learning_signals: List[CorrectionLearningSignal] = Field(default_factory=list)
    learning_summary: Dict[str, Any] = Field(default_factory=dict)


class LearningImportResult(BaseModel):
    organization_settings_applied: bool
    profiles_created: int
    profiles_updated: int
    learning_signals_received: int
    notes: List[str] = Field(default_factory=list)


class BatchPostResult(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    results: List[PostingResult] = Field(default_factory=list)
    skipped: List[BatchPostSkip] = Field(default_factory=list)


class PostingResultCreate(BaseModel):
    target: PostingTarget
    success: bool
    dry_run: bool = False
    client_profile_id: Optional[str] = None
    message: str
    external_id: Optional[str] = None
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    request_payload: Dict[str, Any] = Field(default_factory=dict)


class PostingResult(BaseModel):
    id: str
    organization_id: str
    invoice_id: str
    target: PostingTarget
    status: PostingStatus
    success: bool
    dry_run: bool = False
    client_profile_id: Optional[str] = None
    actor_id: str = ""
    message: str
    external_id: Optional[str] = None
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    response_payload: Dict[str, Any] = Field(default_factory=dict)
    raw: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class TallyConnectorClaimRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=5, ge=1, le=25)
    dry_run: bool = False

    @field_validator("workspace_id")
    @classmethod
    def clean_workspace_id(cls, value: str) -> str:
        return value.strip()


class TallyConnectorJob(BaseModel):
    posting_id: str
    invoice_id: str
    invoice_number: str
    source_file: str
    dry_run: bool
    client_profile_id: str
    workspace_id: str
    company_name: str
    tally_url: str
    xml: str
    posting_plan: Dict[str, Any] = Field(default_factory=dict)


class TallyConnectorClaimResponse(BaseModel):
    success: bool = True
    workspace_id: str
    jobs: List[TallyConnectorJob] = Field(default_factory=list)


class TallyConnectorResultItem(BaseModel):
    posting_id: str = Field(min_length=1)
    invoice_id: str = Field(min_length=1)
    success: bool
    message: str = Field(default="", max_length=2000)
    external_id: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("posting_id", "invoice_id", "message")
    @classmethod
    def clean_result_text(cls, value: str) -> str:
        return value.strip()


class TallyConnectorResultRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=160)
    results: List[TallyConnectorResultItem] = Field(default_factory=list)

    @field_validator("workspace_id")
    @classmethod
    def clean_result_workspace_id(cls, value: str) -> str:
        return value.strip()


class TallyConnectorResultResponse(BaseModel):
    success: bool
    workspace_id: str
    accepted: int = 0
    rejected: int = 0
    postings: List[PostingResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class DetectedInvoiceProfile(BaseModel):
    country_code: str = "US"
    country_name: str = "United States"
    currency: str = "USD"
    invoice_format: str = "auto"
    tax_mode: str = "auto"
    tax_registration_label: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    signals: List[str] = Field(default_factory=list)


class ClientProfileRecommendation(BaseModel):
    profile: ClientProfile
    score: float = Field(default=0, ge=0, le=1)
    reasons: List[str] = Field(default_factory=list)


class ProfileRecommendationResult(BaseModel):
    invoice_id: str
    detected: DetectedInvoiceProfile
    recommendations: List[ClientProfileRecommendation] = Field(default_factory=list)
    auto_profile_id: Optional[str] = None


class InvoiceReviewSeverity(str, Enum):
    OK = "ok"
    REVIEW = "review"
    ERROR = "error"


class InvoiceReviewField(BaseModel):
    field_path: str
    label: str
    value: str = ""
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    severity: InvoiceReviewSeverity = InvoiceReviewSeverity.OK
    issue: str = ""
    suggestion: str = ""
    evidence: List[ExtractionEvidence] = Field(default_factory=list)


class InvoiceReviewInsight(BaseModel):
    title: str
    detail: str
    severity: InvoiceReviewSeverity = InvoiceReviewSeverity.OK
    action: str = ""


class InvoiceReviewResult(BaseModel):
    invoice_id: str
    overall_score: float = Field(default=0, ge=0, le=1)
    needs_attention: int = 0
    fields: List[InvoiceReviewField] = Field(default_factory=list)
    insights: List[InvoiceReviewInsight] = Field(default_factory=list)
    suggested_patch: Dict[str, Any] = Field(default_factory=dict)
    detected: DetectedInvoiceProfile
    recommended_profile_id: Optional[str] = None
    profile_reasons: List[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class AiExtractionStatus(BaseModel):
    provider: str
    configured: bool
    live_provider: bool
    endpoint_configured: bool
    token_configured: bool
    policy: str
    timeout_seconds: float
    max_payload_chars: int
    mode: str


class DeleteInvoicesResult(BaseModel):
    organization_id: str
    deleted: int


class StorageCleanupResult(BaseModel):
    organization_id: str
    expired_files: int = 0
    deleted_files: int = 0
    errors: List[str] = Field(default_factory=list)
