# pkg35B — Client Profile organization

## Delivered scope

The main Client Profiles page and accounting integration pages use one shared
editor, organized into Company, Connection, Posting rules, Extraction guidance,
and Samples & checks. Existing profile IDs, storage fields and posting adapters
are unchanged. There is no data migration or connector installer change.

- Full-width company/ledger fields and guidance, existing Calm Finance tokens,
  keyboard-operated section tabs, light/dark and mobile layouts.
- Connection status is scoped to the selected saved profile, read-only and
  refreshed every 15 seconds. It distinguishes heartbeat/Tally reporting from
  company configuration and explicitly unverified accounting masters. Fresh
  diagnostics still run on Windows; the browser never polls posting jobs.
- Technical connection fields sit under Advanced. Tokens remain masked; only
  owners/admins can generate or replace credentials in the editor.
- Manual Tally names show Unverified. Inventory defaults are hidden in
  non-inventory modes without deleting them. Ledger/tax line mappings remain
  visible because they can apply in accounting-only modes too.
- Save draft and Activate profile are separate actions. Already-active profiles
  say Save changes and require confirmation before saving edits. Activation uses
  the existing validated endpoint, not the old overview's generic PATCH shortcut.
- Saving normalizes the form from the server response. Unsaved changes block
  activation, recommendations, review submission and sample uploads; changing
  profiles/templates prompts before discarding edits. Workspace switches reset
  the editor so one workspace's draft cannot be saved into another.
- Sample expected values are reviewer notes in the existing notes field. A
  reviewer can mark them checked against the original PDF. Editing values clears
  that confirmation; Save records it. This is not an automated extraction score.
- Guidance labels no longer promise automatic model training, sample-based
  accuracy, executable free-text rules or AI consumption of exception notes.
- Viewer/demo access is read-only. No automatic approval toggle was added.

## Behavior that deliberately remains unchanged

Saving an active profile updates its configuration immediately. A draft is not
a versioned staging copy of an active profile. Approval is still mandatory for
connector claims; profile activation is a setup-review state, not invoice
approval. Frozen posting plans/reapproval rules belong to pkg35C, not this UI
release. Company/master verification and voucher reconciliation remain pkg36.

The structured sample regression harness, supplier correction retrieval and
measured extraction accuracy remain in the later learning phase. The sample
checkbox is a human review marker, not a tamper-proof approval audit.

## Verification

- Four backend contract regressions: hidden stock defaults do not change
  accounting-voucher XML; all three Tally posting modes preserve stored settings,
  metadata, active state and the redacted connector credential on edit/save.
- Browser coverage at 1440px, 390px and 320px in both themes: all five sections,
  field bounds, saved-settings equality, hidden-value preservation, separate
  activation, sample confirmation invalidation, keyboard navigation, discard
  protection and demo read-only access.
- Existing reporting and native connector gateway suites remain in CI.
- Release gate: full Python suite, typecheck, lint, production build, browser
  regressions and SQLite/PostgreSQL GitHub checks before main is advanced.

No production client settings or invoices are edited by QA. Browser fixtures use
an isolated localhost API and refuse a non-local QA API hostname.

Local verification completed: 167 Python tests passed (five existing SWIG
deprecation warnings), 17 browser tests passed, typecheck/lint/production build
passed. Desktop/light and desktop/mobile dark screenshots were inspected.
GitHub verification and live deployment status are checked before handoff.

Accessibility references: [WAI tabs pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)
and [MDN unload warnings](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event).
Browser unload prompts are best-effort, especially on mobile; they are not
persistent draft storage. Save explicitly before leaving the editor.
