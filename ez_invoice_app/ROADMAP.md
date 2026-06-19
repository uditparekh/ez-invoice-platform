# EZ-Invoice Product Roadmap

## Product Vision

EZ-Invoice should become a universal B2B invoice automation platform: ingest any supplier invoice, extract structured data, validate it, route exceptions for review, and post approved bills into accounting systems with an audit trail.

## Phase 1: Universal Intake MVP

- Multi-PDF upload with automatic extraction mode selection.
- Generic invoice parser for invoice number, supplier, customer, dates, currency, totals, tax, and line items.
- Adapter framework for supplier-specific templates without exposing supplier names in the UI.
- Normalized invoice schema used by every export and connector.
- Review dashboard with confidence score, missing fields, duplicate invoice detection, total reconciliation, and raw text preview.
- Exports for JSON, Excel, QuickBooks, TallyPrime XML, Coupa, NetSuite, and SAP.

## Phase 2: Accounting Connectors

- QuickBooks OAuth hardening, token storage, retry handling, duplicate bill prevention, and account mapping.
- TallyPrime local connector for each client workspace: authenticate connector, test gateway, validate company/ledgers, then post approved vouchers.
- Initial local connector prototype: token-protected Flask agent that validates voucher XML, probes TallyPrime, and posts approved voucher jobs.
- Connector abstraction so new systems can be added without touching parser code.
- Per-client ledger/category mapping profiles.
- Send queue with success/failure history and re-send controls.

## Client Workflow Target

1. Client logs in to EZ-Invoice and enters its workspace.
2. Client connects one or more accounting systems, such as TallyPrime or QuickBooks.
3. Client uploads inbound supplier invoices or outbound customer invoices.
4. EZ-Invoice detects direction, normalizes the invoice, validates totals, and applies client ledger rules.
5. Approved inbound invoices are posted as bills/purchase vouchers; approved outbound invoices are posted as sales invoices.
6. Posting responses, errors, and source PDFs remain in the workspace audit trail.

## Phase 3: Human Review Workflow

- Editable extracted fields before export.
- Line-item split/merge/edit controls.
- Approval statuses: New, Needs Review, Approved, Posted, Failed.
- Exception queue for low-confidence invoices and total mismatches.
- User notes and activity timeline per invoice.

## Phase 4: SaaS Foundation

- Tenant model: organizations, users, roles, permissions, and client workspaces.
- Client-owned connector settings for each accounting system and legal entity.
- Local Tally connector agent because TallyPrime commonly runs on the customer's desktop/LAN rather than as a cloud API.
- Persistent database for invoices, files, extraction results, mappings, connector settings, and audit logs.
- Secure file storage with retention policy.
- Background processing workers for large batches.
- Login, admin console, account settings, and usage dashboard.

## Phase 5: Intelligent Extraction

- OCR for scanned PDFs and images.
- Layout-aware table extraction for invoices with complex line-item grids.
- Vendor learning: remember corrections and improve future extraction for that supplier.
- Confidence model by field, row, and document.
- Duplicate vendor and duplicate invoice detection across tenants.

## Phase 6: Enterprise Readiness

- Role-based approval workflows.
- SOC 2-ready audit logging and security controls.
- Encryption for secrets and uploaded documents.
- Webhook/API access for enterprise integrations.
- Monitoring, alerting, connector health checks, and operational runbooks.

## Near-Term Build Order

1. Remove supplier-specific product language from the UI and exports.
2. Add editable review fields for header and line items.
3. Persist invoices locally with SQLite so processed batches survive refreshes.
4. Add a connector interface and move QuickBooks/Tally behind the same contract.
5. Add Tally ledger validation and a dry-run voucher preview.
6. Add OCR fallback for scanned invoices.
7. Add user/client profiles and per-client mapping storage.
