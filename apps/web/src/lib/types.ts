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
  validation_issues: string[];
  created_at: string;
  updated_at: string;
}

export interface ClientProfileItemMapping {
  source_description_contains: string;
  source_hsn_sac: string;
  target_item_name: string;
  target_uom: string;
  purchase_ledger: string;
  tax_ledger: string;
  metadata: Record<string, unknown>;
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

export interface ClientProfilePayload {
  name: string;
  accounting_system: AccountingSystem;
  description: string;
  is_default: boolean;
  settings: ClientProfileSettings;
}

export interface PostingRequest {
  target: PostingTarget;
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

export interface ApiErrorPayload {
  detail?: string;
}
