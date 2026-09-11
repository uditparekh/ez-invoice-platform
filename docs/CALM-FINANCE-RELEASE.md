# Calm Finance: reporting and interface release

## Design

The selected concept is A: restrained indigo, neutral working surfaces, compact
metrics, fine borders, readable text, and consistent hierarchy. Dark mode uses
charcoal elevations, a darker filled-action accent with white text, and a separate
light indigo text accent. The redesign preserves product workflows and the current
Vercel/Railway architecture. No production invoice records are changed by this release.

Home, Insights and History are rebuilt. Shared tokens and typography carry through
Invoices, review, approvals, Sift, integrations/Tally, profiles, rules, settings,
dialogs and authentication. The invoice queue loses a redundant filter row;
status badges no longer truncate their labels. The workspace dialog uses native
modal focus containment and restores focus when closed.

References: [Linear's calmer interface](https://linear.app/now/behind-the-latest-design-refresh),
[WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

## Report definitions

- **Invoices received:** all workspace invoices with `created_at` within the chosen
  inclusive calendar dates in UTC. The browser's 100-invoice list limit does not apply.
- **Invoice value and tax recorded:** decimal sums from the received cohort, grouped
  by original currency. No exchange rates or deductible-tax assumptions are applied.
- **Currently posted value:** received-cohort invoices whose current status is posted.
  This is not cash paid or value posted during the period.
- **Successful postings:** live posting attempts with succeeded status whose recorded
  completion timestamp (`updated_at`) falls in the period. Dry runs are excluded;
  attempts on older invoices are included. These are attempts, not unique invoices.
- **Current queue:** present statuses across every date, independent of the report range.
- Supplier and volume breakdowns use the same received cohort. Charts include zero
  days and use equal calendar buckets for long ranges. CSV values retain currency codes.

## History

The source is `audit_events`, not the present invoice state. History has stable event
IDs, time/category/invoice-number filters, deterministic timestamp+ID ordering,
cursor pagination and an as-of timestamp. Exports use the same filters and snapshot,
include every matching page, escape CSV delimiters and neutralize formula-leading text.
Raw audit details are never exposed; a field allowlist excludes credentials and paths.
New approvals and corrections record an actor. Missing historical actors are explicitly
labeled. Posting result details use the existing membership-protected posting endpoint.

This is an operational event history, not an immutable or compliance-certified audit
archive. Existing foreign-key deletion behavior is unchanged: deleting an invoice can
delete associated events. No historical actor/event backfill is fabricated. For durable
compliance retention, a separate retention/deletion policy and migration need approval.

## Verification and boundaries

Local gates: backend pytest, pnpm typecheck, pnpm lint, pnpm build. GitHub CI runs the
backend on SQLite and PostgreSQL and the browser regression suite on an isolated
local API/database, never production. Browser coverage includes nine core routes at
1440, 390 and 320 pixels in light/dark mode, History filtering/export/detail links,
and workspace-dialog keyboard focus. Screenshots are retained as CI artifacts.

This release does not change posting policy, connector binaries or the remaining
physical Windows/Tally acceptance test. Analytics remains operational reporting,
not a general ledger. AI spend/accuracy and ROI require actual cost/outcome telemetry;
they should not be reintroduced as estimates disguised as measured performance.
Reports allow up to ten years; History export explicitly rejects more than 100,000
events rather than silently truncating. Very large reporting workloads should move
to database-side decimal summary tables after representative load testing.
