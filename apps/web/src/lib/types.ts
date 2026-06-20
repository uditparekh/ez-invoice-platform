export type OrganizationRole =
  | "owner"
  | "admin"
  | "accountant"
  | "approver"
  | "viewer";

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

export interface ApiErrorPayload {
  detail?: string;
}
