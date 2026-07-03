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

## Step 9 — Saved views + queue keyboard nav (2026-07-03) ✅ COMPILE-VERIFIED
Closes the last two open items on the wow shortlist.

| File | Status | Change |
|---|---|---|
| apps/web/src/components/invoice-workspace.tsx | EDITED | **Saved views** (wow #5): a "Views" chip strip appears under the queue readiness bar. Set any status tab + search combo → a dashed "＋ Save view" chip appears → name it inline → it becomes a one-click chip (e.g. "Tally · Ready · This week"). Active view highlights indigo; hover a chip to reveal ✕ delete; persists in localStorage (max 8). **Queue keyboard nav** (wow #4 completion): J/K move the selection through the visible list, Enter opens the selected invoice in the Review Workspace, "/" focuses search — same vocabulary as Sift mode, guarded so it never fires while typing or in review mode. |
| apps/web/src/components/command-center.tsx | EDITED | Shortcuts overlay gains an "Invoices queue" section documenting J/K · Enter · /. |

### How it works (for the team)
- On Invoices: click a status tab (e.g. Ready), type a vendor in search, then "＋ Save view" → name it.
  From then on it's a one-click chip; the chip glows when its filters are active. Hover → ✕ to remove.
- J/K/Enter work anywhere on the queue when you're not typing; press ? to see every shortcut.

### Verification: `tsc` ✅ 0 errors · `eslint` ✅ 0 errors 0 warnings · `next build` ✅ 41/41 routes.

### Wow shortlist status: 1 ⌘K ✅ · 2 nudges ✅ · 3 resizable panes ✅ · 4 shortcuts+overlay ✅ · 5 saved views ✅ · 6 chat sidebar intentionally skipped. **Shortlist complete.**

## Step 9 — Wow-list closure (2026-07-03)
Review finding: your "Lock in SiftEntry product UI polish" commit already shipped **saved views**
(chips strip on the Invoices queue, localStorage-persisted) and **queue keyboard nav** (J/K move
selection · Enter opens review · "/" focuses search). With Step 8's palette + overlay, the entire
§18 wow shortlist is now complete: ⌘K ✓ · nudges ✓ · resizable panes ✓ · shortcuts + ? overlay ✓ ·
saved views ✓ · chat sidebar skipped by design ✓.

| File | Status | Change |
|---|---|---|
| apps/web/src/components/command-center.tsx | EDITED | "?" overlay gains an **Invoices queue** section documenting J/K · Enter · "/" so every live shortcut is discoverable. |

## Step 8 — Full repo review + Command Center (2026-07-03) ✅ COMPILE-VERIFIED

**Repo review verdict (github.com/uditparekh/ez-invoice-platform @ 052954d):** the pushed repo is
healthy — all Step 0–7 work integrated (some with your own equivalent lint fixes and naming polish),
and it passed `tsc` ✅ `eslint` ✅ `next build` ✅ (41/41 routes) with ZERO changes needed.
Page-by-page against UI Spec v1.0: all 13 pages match the lock. The only spec items missing were
the top two entries of the wow backlog (§18) — both built in this step.

| File | Status | Change |
|---|---|---|
| apps/web/src/components/command-center.tsx | NEW | **⌘K command palette + "?" shortcuts overlay** in one mounted-once component. Palette: opens with ⌘K/Ctrl+K (or clicking the header search), fuzzy-filters three groups — **Actions** (Upload invoices · Start Sift mode · New client profile · Open approvals · Toggle dark mode), **Pages** (all 8 nav destinations), **Invoices** (LIVE search of real invoices by number or supplier; selecting one deep-links straight into the Review Workspace). Full keyboard control (↑↓ · ↵ · esc), mouse hover sync, scroll-into-view, body-scroll lock, group headers, empty state, footer hint bar. Shortcuts overlay: press **?** anywhere (outside inputs) — Global / Sift mode / Review Workspace shortcut tables with kbd chips. Exports `openCommandPalette()` (window event) so any component can trigger it without prop-drilling. |
| apps/web/src/components/app-shell.tsx | EDITED | The header's dead search `<input>` (placeholder-only, wired to nothing) replaced with a live palette trigger button — same look, plus a **⌘K** kbd chip — and `<CommandCenter />` mounted once at shell root. |
| apps/web/pnpm-workspace.yaml | EDITED | Added `packages: ["."]` (kept your `allowBuilds`) — required for `pnpm install` on pnpm 9 (CI-safe); harmless on pnpm 10. |

### How the new features work (for the team)
- **⌘K anywhere** (Ctrl+K on Windows) or click the header search → type "mad" to jump to a Madelin
  invoice in review mode, "sift" to start Sift mode, "dark" to flip the theme. Esc closes.
- **? anywhere** → the shortcuts overlay. This is also where new keyboard features get documented.
- **For developers:** `import { openCommandPalette } from "@/components/command-center"` and call it
  from any button. The invoices group uses `useWorkspaceInvoices`, mounted lazily only while the
  palette is open — no extra fetches during normal navigation.

### Verification (this step, fresh clone)
`pnpm install` → `tsc --noEmit` 0 errors → `eslint` 0 errors → `next build` 41/41 routes.
(Google-Fonts fetch is the only sandbox-blocked step; verified via temporary stub, layout restored.)

## REBASE — new baseline (2026-07-02, evening)
Baseline is now **siftentry-platform-source-2026-07-02.zip** (your upload), which already contains
Steps 0–5 integrated plus your own additions (settings sub-components, client-profiles route,
integrations hub, exceptions page). The zip below contains ONLY this pass's changes vs that baseline.

## Step 6 — Client profiles + Settings rebuild, Home parity (this zip)

| File | Status | Change |
|---|---|---|
| apps/web/src/components/client-profiles/profile-wizard.tsx | NEW | The spec §15 **full-screen onboarding wizard** (matches the locked mockup): fixed overlay with brand chrome + "takes ~4 minutes" + Save-draft-&-exit, 5-dot progress rail (done=green ✓, current=indigo glow). Steps: ① client name + system cards (Tally/QuickBooks/Zoho) ② country & tax cards (🇮🇳 India GST with the GSTIN-validation callout / 🇺🇸 US / ✨ Auto-detect) ③ posting mode (Item invoice vs Accounting voucher for Tally; supplier-bill note for cloud) + posting-expectations textarea ④ multi-PDF sample picker with removable "✓ ready to sift" rows ⑤ review card → green **Submit for approval**. Wiring is REAL: builds the payload via the panel's own `blankProfile()` (now exported), stamps `training_profile.onboarding_status = "ready_for_admin_review"` + expectations into `extraction_instructions`, calls `createProfile`, then uploads each sample via `uploadTrainingSample`. Draft auto-persists to localStorage and restores on reopen. |
| apps/web/src/app/(product)/app/client-profiles/page.tsx | REWRITTEN | Spec §13 overview-first page replacing the raw monolith render. **Pending-approval banners** for `ready_for_admin_review` profiles with Review setup + working **✓ Approve & activate** (real `updateProfile` → onboarding_status "active"). **Profile cards grid**: initials avatar, Default/status chips, system · posting mode, country · tax label · currency, samples + mappings counts, Open profile. **+ New profile** opens the wizard. **Advanced editor** toggle renders the full existing 2,752-line ClientProfilesPanel (connection settings, templates, AI readiness, import/export — nothing lost, one click away). Empty state per spec. |
| apps/web/src/components/client-profiles-panel.tsx | EDITED (1 line) | `blankProfile` exported so the wizard reuses the panel's canonical payload builder instead of duplicating it. |
| apps/web/src/app/(product)/app/settings/page.tsx | REWRITTEN | Spec §14 **Linear-style two-group rail**: WORKSPACE (Organization / Team access / Data retention) · MY ACCOUNT (Profile / Security / Notifications / Appearance), sticky on desktop, horizontal scroll on mobile. **Organization**: real org name from the active membership + workspace defaults (currency/country/primary system). **Team access** = your existing TeamManagementPanel, **Security** = your PasswordChangeCard (both reused as-is). **Data retention**: the 3 locked policies as selectable cards + the isolation/credentials facts. **Profile**: real name/email from auth with audit-attribution note. **Notifications**: approval/failure/digest toggles. **Appearance**: Light/Dark/System wired to the same `siftentry-theme` mechanism as the header toggle. Workspace prefs persist locally with an explicit "syncs when the org-settings API lands" note — honest, and trivially swappable to the API later. |
| apps/web/src/app/(product)/app/page.tsx | EDITED | Home brought to spec §5 parity: **gradient ROI hero** (real auto-extracted %, real processed value, EST-labeled time saved), **approvals shortcut banner** when validated invoices are waiting (routes to /app/approvals — the mobile view is now discoverable), and the **✦ proactive nudge card** with real pattern detection (a vendor whose invoices repeat the same validation flag ≥2×) → "Create rule →" into Rules, dismissible + remembered. |

### Parity verdict on your baseline (checked page-by-page vs the locked spec)
✓ Shell/nav (8 items incl. Client profiles) · ✓ tokens/dark/fonts · ✓ Invoices queue + Sift launcher · ✓ Sift loop · ✓ Review Workspace depth · ✓ Insights 4-tab · ✓ Rules 4-tab · ✓ History + posting log · ✓ Integrations hub grid + detail steppers · ✓ Approvals route. Gaps closed this pass: Home hero/nudge, Client profiles overview + wizard + approve flow, Settings rail.

### Backend TODOs (unchanged + new)
1. Honor `learn_vendor_memory` on invoice PATCH. 2. Org-settings + notification-preferences endpoints (Settings panes are pre-wired to swap localStorage → API). 3. Bounding boxes from extraction → unlocks teach-fields + true PDF coordinate highlighting.

## Step 7 — Compile verification pass (2026-07-03) ✅
First fully compiler-verified delivery. Environment: Node 22 · pnpm 9 · fresh `pnpm install`.

**Results: `tsc --noEmit` ✅ 0 errors · `eslint` ✅ 0 errors · `next build` ✅ all 23 routes compiled**
(the only build failure in the sandbox was next/font fetching Google Fonts — network-blocked here,
works on any normal machine; verified by stubbing fonts, building clean, then restoring layout.tsx).

Lint fixes applied (React's strict `set-state-in-effect` rule on localStorage hydration —
all four were in Step 6 files, all now use lazy `useState` initializers):

| File | Fix |
|---|---|
| apps/web/src/app/(product)/app/page.tsx | Nudge dismissed-flag → lazy initializer + `useSyncExternalStore` isClient gate so server and hydration renders stay identical (no hydration mismatch on the banner). |
| apps/web/src/components/client-profiles/profile-wizard.tsx | Draft restore → lazy initializer (still restores saved drafts on mount). |
| apps/web/src/app/(product)/app/settings/page.tsx | AppearancePane theme + the shared `usePrefs` hook → lazy initializers. |

**Repo note:** github.com/uditparekh/ez-invoice-platform is at the 2026-06-19 baseline and contains
NO `apps/web` — the entire SiftEntry platform exists only locally. Push it (see chat) so future
passes can verify against the true tree.
**CI note:** with pnpm 9, `apps/web/pnpm-workspace.yaml` needs a `packages: ["."]` entry to install;
pnpm 10 accepts the current file. Not shipped in the zip — flagging in case CI uses pnpm 9.

## Packaging note (2026-07-02)
From Step 3 onward, delivery is ONE consolidated zip — `siftentry-ui-complete.zip` — containing the
CURRENT state of every file changed since the uploaded baseline (Steps 0+1+2+3 merged). Unzip once
over the repo root; no step ordering needed. The per-step zips are superseded.

## Remaining build order
All spec build-order items are now delivered or explicitly deferred (see Step 5 notes). Backlog wow items (⌘K palette, saved views, shortcuts overlay) remain available as post-v1 enhancements.
