export type OrganizationRole =
  | "owner"
  | "admin"
  | "accountant"
  | "approver"
  | "viewer";

export type AccountingSystem =
  | "quickbooks"
  | "tally"
  | "zoho_books"
  | "coupa"
  | "netsuite"
  | "sap"
  | "excel"
  | "custom";

export type ProfilePostingMode =
  | "accounting_voucher"
  | "item_invoice"
  | "supplier_bill"
  | "export_package"
  | "custom";

export type PostingTarget = "quickbooks" | "tally" | "zoho_books";

export type PostingStatus = "started" | "succeeded" | "failed";

export type InvoiceStatus =
  | "uploaded"
  | "extracted"
  | "needs_review"
  | "validated"
  | "approved"
  | "posting"
  | "posted"
  | "failed";

export interface Membership {
  organization_id: string;
  organization_name: string;
  role: OrganizationRole;
  created_at: string;
}

export interface OrganizationMember {
  user_id: string;
  email: string;
  full_name: string;
  role: OrganizationRole;
  is_active: boolean;
  member_since: string;
  last_login_at: string | null;
}

export interface Invitation {
  id: string;
  organization_id: string;
  email: string;
  role: OrganizationRole;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  invitation_token?: string | null;
}

export interface AuthenticatedUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  memberships: Membership[];
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthenticatedUser;
}

export interface AiExtractionStatus {
  provider: string;
  configured: boolean;
  live_provider: boolean;
  endpoint_configured: boolean;
  token_configured: boolean;
  policy: string;
  timeout_seconds: number;
  max_payload_chars: number;
  mode: string;
}

export interface PasswordResetResponse {
  message: string;
  reset_token?: string | null;
  expires_at?: string | null;
}

export interface Party {
  name: string;
  tax_id: string;
  address: string[];
  email: string;
  phone: string;
}

export interface InvoiceLine {
  id?: string;
  line_number: number;
  description: string;
  quantity: number;
  uom: string;
  unit_price: number;
  net_amount: number;
  tax_amount: number;
  total_amount: number;
  hsn_sac: string;
  category: string;
  gl_code: string;
  confidence: number | null;
}

export interface ExtractionEvidence {
  field: string;
  value: string;
  page: number | null;
  snippet: string;
  confidence: number | null;
  /** Normalized (0..1) bounding box located in the PDF text layer at parse
   *  time — powers true coordinate highlighting in review. */
  x0?: number | null;
  y0?: number | null;
  x1?: number | null;
  y1?: number | null;
}

export interface Invoice {
  id: string;
  organization_id: string;
  source_file: string;
  source_path: string;
  parser: string;
  extraction_engine: string;
  page_count: number;
  status: InvoiceStatus;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  purchase_order: string;
  currency: string;
  subtotal: number;
  tax_total: number;
  total: number;
  supplier: Party;
  customer: Party;
  direction: string;
  lines: InvoiceLine[];
  confidence: number | null;
  evidence: ExtractionEvidence[];
  validation_issues: string[];
  created_at: string;
  updated_at: string;
}

export type InvoicePatch = Partial<
  Pick<
    Invoice,
    | "invoice_number"
    | "invoice_date"
    | "due_date"
    | "purchase_order"
    | "currency"
    | "subtotal"
    | "tax_total"
    | "total"
    | "supplier"
    | "customer"
    | "direction"
    | "lines"
  >
>;

export interface ClientProfileItemMapping {
  source_description_contains: string;
  source_hsn_sac: string;
  target_item_name: string;
  target_uom: string;
  purchase_ledger: string;
  tax_ledger: string;
  metadata: Record<string, unknown>;
}

export interface ClientTrainingSample {
  id: string;
  filename: string;
  stored_path: string;
  size_bytes: number;
  content_type: string;
  sample_type: string;
  status: string;
  notes: string;
  uploaded_at: string;
  fields_confirmed: boolean;
}

export interface ClientTrainingProfile {
  onboarding_status: string;
  business_process: string;
  invoice_volume: string;
  expected_fields: string[];
  accounting_exports: string[];
  sample_invoices: ClientTrainingSample[];
  extraction_instructions: string;
  validation_rules: string[];
  posting_expectations: string;
  exception_examples: string;
  llm_ready: boolean;
  llm_policy: string;
}

export interface ClientProfileSettings {
  company_name: string;
  environment: string;
  connection_settings: Record<string, unknown>;
  country_code: string;
  country_name: string;
  default_currency: string;
  invoice_format: string;
  tax_mode: string;
  tax_registration_label: string;
  default_parser: string;
  direction: string;
  posting_mode: ProfilePostingMode;
  voucher_type: string;
  purchase_ledger: string;
  tax_ledger: string;
  tcs_ledger: string;
  round_off_ledger: string;
  stock_item_name: string;
  stock_item_hsn: string;
  stock_item_uom: string;
  godown_name: string;
  item_mappings: ClientProfileItemMapping[];
  tax_settings: Record<string, unknown>;
  training_profile: ClientTrainingProfile;
  metadata: Record<string, unknown>;
}

export interface ClientProfile {
  id: string;
  organization_id: string;
  name: string;
  accounting_system: AccountingSystem;
  description: string;
  is_default: boolean;
  settings: ClientProfileSettings;
  created_at: string;
  updated_at: string;
}

export interface CorrectionLearningSignal {
  id: string;
  invoice_id: string;
  invoice_number: string;
  supplier_name: string;
  field_path: string;
  old_value: unknown;
  new_value: unknown;
  actor_id: string;
  actor_email: string;
  created_at: string;
}

export interface ClientProfilePayload {
  name: string;
  accounting_system: AccountingSystem;
  description: string;
  is_default: boolean;
  settings: ClientProfileSettings;
}

export interface PostingRequest {
  target?: PostingTarget;
  dry_run?: boolean;
  client_profile_id?: string | null;
}

export interface ValidationResult {
  invoice_id: string;
  valid: boolean;
  status: InvoiceStatus;
  issues: string[];
}

export interface PostingResult {
  id: string;
  organization_id: string;
  invoice_id: string;
  target: PostingTarget;
  status: PostingStatus;
  success: boolean;
  dry_run: boolean;
  client_profile_id: string | null;
  actor_id: string;
  message: string;
  external_id: string | null;
  issues: Record<string, unknown>[];
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  raw: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DetectedInvoiceProfile {
  country_code: string;
  country_name: string;
  currency: string;
  invoice_format: string;
  tax_mode: string;
  tax_registration_label: string;
  confidence: number;
  signals: string[];
}

export interface ClientProfileRecommendation {
  profile: ClientProfile;
  score: number;
  reasons: string[];
}

export interface ProfileRecommendationResult {
  invoice_id: string;
  detected: DetectedInvoiceProfile;
  recommendations: ClientProfileRecommendation[];
  auto_profile_id: string | null;
}

export type InvoiceReviewSeverity = "ok" | "review" | "error";

export interface InvoiceReviewField {
  field_path: string;
  label: string;
  value: string;
  confidence: number | null;
  severity: InvoiceReviewSeverity;
  issue: string;
  suggestion: string;
  evidence: ExtractionEvidence[];
}

export interface InvoiceReviewInsight {
  title: string;
  detail: string;
  severity: InvoiceReviewSeverity;
  action: string;
}

export interface InvoiceReviewResult {
  invoice_id: string;
  overall_score: number;
  needs_attention: number;
  fields: InvoiceReviewField[];
  insights: InvoiceReviewInsight[];
  suggested_patch: Record<string, unknown>;
  detected: DetectedInvoiceProfile;
  recommended_profile_id: string | null;
  profile_reasons: string[];
}

export interface ApiErrorPayload {
  detail?: string | Record<string, unknown>;
}

export interface TallyConnectorProfileStatus {
  client_profile_id: string;
  profile_name: string;
  workspace_id: string;
  connector_enabled: boolean;
  connector_configured: boolean;
  connected: boolean;
  last_seen_at: string | null;
  seconds_since_seen: number | null;
  connector_host: string;
  connector_version: string;
  tally_detected: boolean | null;
  tally_company: string;
  last_posting_at: string | null;
  last_posting_success: boolean | null;
  last_posting_message: string;
  last_posting_invoice_number: string;
}

export interface TallyConnectorStatusResponse {
  organization_id: string;
  generated_at: string;
  connected_window_seconds: number;
  statuses: TallyConnectorProfileStatus[];
}
