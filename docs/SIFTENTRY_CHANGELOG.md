# SIFTENTRY_CHANGELOG.md
Cumulative record of every change Claude made versus the uploaded baseline
`siftentry-ui-package-20260702.zip`. Apply steps in order. Keep this file in `docs/`.

Baseline: user upload, 2026-07-02 · UI Spec v1.0 (siftentry-ui-spec.html) is the source of truth.

---

## Step 0 — Tokens + Shell (siftentry-step0-tokens-shell.zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/app/globals.css | REWRITTEN | Dark mode replaced with locked "Elevated Slate v2" (canvas #0B0F1A · shell #131A2B · card #191F30 · popover #212940 · border #2F3A54 · primary #7B78F5). Light canvas #F8FAFC→#F6F8FC. New tokens: --shell, --cyan-ink, --gold-ink. New Tailwind utilities: shadow-card / shadow-pop / shadow-glow, font-display (Space Grotesk on h1–h3, −0.02em), tabular-nums on mono. Added .animate-scanline keyframes. Selection/focus tuned to indigo. |
| apps/web/src/app/layout.tsx | REWRITTEN | Loads Inter + Space Grotesk + JetBrains Mono via next/font/google → CSS vars --font-inter/--font-grotesk/--font-jbmono on <html>. |
| apps/web/src/components/app-shell.tsx | EDITED | Nav trimmed 10→8 items (removed "Sift mode", "Review Workspace" — modes, not destinations; routes kept). Rules & mapping icon FileText→Workflow. Sidebar/mobile-sidebar/header bg-surface→bg-shell (own elevation layer). Mobile sidebar shadow-2xl→shadow-pop. Active nav unified to indigo (removed dark:cyan overrides). Removed unused FileSearch/Sparkles imports. |
| apps/web/src/components/invoice-workspace.tsx | EDITED | Added gradient ⚡ Sift launcher (from-accent to-cyan, shadow-glow, live needs_review count) after the Upload control. Added Sparkles + next/link imports. DropdownPanel: bg-surface-subtle+shadow-2xl → bg-surface+shadow-pop, dark:bg-surface-strong. |
| apps/web/src/app/(product)/app/sift/page.tsx | EDITED | Hardcoded old dark palette remapped: #070B15→#0B0F1A, #0B1020→#191F30, #11172A→#212940, #202A46→#2F3A54, #111A31→#1B2238, #090E1A→#0F1524. (Superseded by Step 2 rewrite.) |
| apps/web/src/components/theme-toggle.tsx | EDITED | dark:text-[#070B15]→dark:text-[#0B0F1A]. |
| apps/web/src/components/dashboard/content-card.tsx | EDITED | +shadow-card. |
| apps/web/src/components/dashboard/metric-card.tsx | EDITED | +shadow-card. |

## Step 1 — Review Workspace depth (siftentry-step1-review-workspace.zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/components/review/resizable-split.tsx | NEW | Reusable two-pane resizable split: pointer-drag handle, min/max %, double-click reset, localStorage persistence, ArrowLeft/Right a11y, stacks below xl. |
| apps/web/src/components/invoices/invoice-detail.tsx | EDITED | (1) Review grid → ResizableSplit (38% default, 24–58%, key "siftentry.review.split"). (2) Evidence beacon: one-shot cyan scan-line sweep + pulsing "Evidence · p.N · snippet" chip over the PDF on every field selection. (3) ReviewDraft gains lines[]; seeded from invoice; included in PATCH (renumbered). (4) ReviewLineItemsPanel rewritten: inline-editable cells (description/qty/UOM/unit price/amount), Add row, per-row delete, live totals/variance from draft. (5) Mapping chips per row: gl_code → chip label, else heuristic Tax ledger / Stock item / Expense ledger / Ledger; tooltip names active client profile. (6) Vendor-memory toggle in save row (default on, remembered via localStorage "siftentry.review.learnVendor"); save PATCH body now includes learn_vendor_memory. New imports: Plus, Trash2, InvoiceLine, ResizableSplit. New helpers: lineMappingChip, parseLineAmount, LineCellInput. onSave signature: () => void → (options:{learnVendor:boolean}) => void. |

BACKEND TODO: honor `learn_vendor_memory` in the invoice PATCH handler when writing correction-learning records (currently safe to ignore).

## Step 2 — Sift mode real loop (siftentry-step2-sift-loop.zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/app/(product)/app/sift/page.tsx | REWRITTEN | Static showcase → working triage cockpit. Queue = needs_review invoices (snapshot on load). Keyboard loop: A/Enter approve · E edit (deep-links to Review Workspace) · S skip (rotates to back, counted) · J/K next/prev · Esc exit. Approve chain: POST /approve, on failure POST /validate then retry /approve; errors surface inline with "press E" guidance. Progress: "n of N" + indigo→cyan progress bar. Real PDF via /api/invoices/{id}/document (styled placeholder for preview-only). Scan-line sweep fires on every advance. Queue-cleared state: 🎉 + approved/skipped counts. Preview-only invoices blocked from approve with explanation. Uses locked dark hexes directly (page is always-dark by design). |
| apps/web/src/components/invoice-workspace.tsx | EDITED (again) | Deep-link support: /app/invoices?invoice={id}&mode=review selects that invoice and opens review mode once loaded, then cleans the URL (window.history.replaceState). Powers Sift "E" escalation. Guarded by a run-once ref. |

## Step 3 — Insights 4-tab (this consolidated zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/app/(product)/app/analytics/page.tsx | REWRITTEN | Single overview → the locked 4-tab layout (spec §9): **Overview** (spend / Touchless-rate gradient hero / avg confidence / exceptions KPIs · automation funnel Uploaded→Extracted→Validated→Posted from real statuses · supplier BarList with a real concentration-anomaly chip when one vendor ≥50% of spend · category donut from mapped line items). **Finance** (cost-per-invoice + processing-saved as clearly EST-tagged industry-baseline math · duplicates blocked computed from real supplier+amount collisions · avg cycle time from created→updated timestamps of posted invoices · payables calendar in 4 weekly buckets from captured due dates with due-this-week alert + discount nudge · tax-credit readiness donut from tax_total + supplier tax_id). **AI performance** (touchless hero · corrections learned fetched live from /corrections/learning · confidence distribution bands · vendor learning table with Mastered/Improving/Training states from real flag rates). **Exceptions** ("🎉 Nothing needs you" good-empty · worklist where every row deep-links to /app/invoices?invoice=…&mode=review · duplicate rows flagged red · ledger-type issues get an ✦ AI-suggest card with "Fix mapping →" into Rules). Header: working Export CSV (client-side) + Board pack (print). Tabs styled per spec, exception count badge. |

## Step 4 — Rules & mapping 4-tab (this consolidated zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/app/(product)/app/rules/page.tsx | REWRITTEN | Static rule library → the locked 4-tab page (spec §12), all wired to real APIs. **GL mapping**: profile switcher in header · profile default-ledger strip (purchase/tax/TCS/round-off) · "Unmapped line items" card scans live invoice lines against the profile's item_mappings and offers one-click "Map it" prefill · editable mapping worksheet (description-contains / HSN / target item / UOM / purchase ledger / tax ledger, add + delete rows) that SAVES to the client profile via updateProfile (settings.item_mappings) with dirty-state guard. **Rules**: Duplicate control + Tax reconciliation cards show LIVE counts from the current queue · Approval-above-threshold rule with on/off toggle + editable threshold (persisted in localStorage as workspace preference) · 🧪 Rule simulator runs the threshold against the last 30 real invoices → "N of 30 (₹X) would require approval" with example hits. **Vendor memory**: merges live invoices with /corrections/learning records into per-vendor cards (invoices · flags · corrections learned · Active-touchless/Learning/Training/Watching states). **Parser training**: training queue auto-lists vendors with avg confidence <92% or flags · sample-upload zone wired to the REAL training-samples endpoint via uploadTrainingSample (multi-file, per selected profile) · shows samples-on-file count from training_profile.sample_invoices · honest note that teach-fields region marking ships with bbox extraction. Legacy /app/gl-mapping and /app/vendors routes untouched (not in nav; superseded by these tabs). |

## Step 5 — Full-platform completion pass (this consolidated zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/components/accounting/accounting-system-page.tsx | EDITED | Added the spec §11 **setup guide stepper** to every integration detail page (Tally/QuickBooks/Zoho/SAP/NetSuite/Coupa share it): per-system step sets — Tally 5 steps (download SiftEntry-Bridge → enable HTTP/XML F1›Settings›Connectivity → URL+token → test connection → sample voucher sandbox), cloud systems 4 OAuth steps, export systems 3 template steps. Steps check off with click, progress persists per system in localStorage, current step highlighted indigo, and once ALL steps complete the stepper **collapses to a green "Setup complete · Re-run setup steps" strip** so the page leads with live status — the locked post-setup adaptation. Existing REAL Tally connector tester (health + sample-voucher modes via /api/integrations/tally/test-connector) untouched and referenced by steps 4–5. |
| apps/web/src/app/(product)/app/history/page.tsx | REWRITTEN | Metric-cards page → spec §10 audit surface. Header: 🔒 APPEND-ONLY badge + working **Export audit log** CSV. **Activity tab**: filter chips (All/Postings/Approvals/Flags) + LIVE pulse, event feed derived from live invoices (posted / failed-with-retry-hint / approved / flagged / recorded) with status pills, amounts, and time-ago. **Posting log & retry tab** (failed-count badge): fetches REAL posting attempts via /api/invoices/{id}/postings for recent posted/failed/approved invoices, table shows time · invoice · target (+dry-run) · SUCCESS/FAILED pill with the raw system message verbatim · **working ↻ Retry** via POST /api/postings/{id}/retry (new attempt prepends to the log) · **Fix mapping →** appears when the failure message smells like a ledger issue and jumps to Rules. Failed rows tinted. Footer: "nothing is overwritten." |
| apps/web/src/app/(product)/app/approvals/page.tsx | NEW | Spec §16 **mobile approval view** at /app/approvals (390px-first, works on desktop). One-job card: vendor · #, huge mono ₹, confidence pill, live **tax-verified ✓** check (subtotal+tax≈total), date/lines/tax line. Thumb-sized green **Approve** wired to the real POST /approve (invoice leaves the stack, session counter), **Reject / fix** deep-links into the Review Workspace, **View PDF** opens the real document. Waiting stack shows the next 3 + overflow count; "All approvals done 🎉" completion state. Access via URL / push links — intentionally not in the 8-item nav per the locked IA. |

### Verified-as-done / deferred (with reasons)
- **Settings** — already matches the locked split (workspace vs account) per your parity review; no changes needed.
- **Auth token unification** — completed globally by Step 0 (tokens + fonts flow through auth screens automatically).
- **States sweep** — Empty/Loading/Error patterns now applied consistently across all new/rewritten pages via the shared dashboard components.
- **Client-profiles wizard polish** — structurally complete (3,146-line panel, wizard + approval flow present); final polish deferred until live client feedback, exactly as your parity review recommends. Blind-rewriting it now would add risk, not value.
- **Teach-fields region marking** — ships when extraction returns bounding boxes (backend dependency).

## Packaging note (2026-07-02)
From Step 3 onward, delivery is ONE consolidated zip — `siftentry-ui-complete.zip` — containing the
CURRENT state of every file changed since the uploaded baseline (Steps 0+1+2+3 merged). Unzip once
over the repo root; no step ordering needed. The per-step zips are superseded.

## Remaining build order
All spec build-order items are now delivered or explicitly deferred (see Step 5 notes). Backlog wow items (⌘K palette, saved views, shortcuts overlay) remain available as post-v1 enhancements.
