# SiftEntry — Training Mode UI, Phase B (July 19, 2026)

## APPLY ORDER — read first
Your GitHub main branch currently ends at the health-fix commit — the
activity timeline and training backend commits are NOT pushed yet (they
are committed locally in GitHub Desktop but "Push origin" was not
clicked). BEFORE applying this package:
1. Open GitHub Desktop → if it shows "Push origin" with pending commits,
   click it. Verify on github.com that the latest commits are the
   timeline and the training backend.
2. Then unzip this package over the repo root.

## What this adds
1. Client profiles page: the Training mode hero (same dark gradient
   family as Sift) — "N trusted formats · M in training", with a
   Train formats button into the queue. Below it: a "new formats
   detected" callout naming untrained suppliers, and the format
   collection — each supplier row shows invoices reviewed, a progress
   bar of its clean streak (n/5), and its badge: amber "Training n/5"
   or green "Trusted".
2. Invoice queue: a dashed banner above the filter chips — "✨ New
   format detected: <supplier> — Train it →" — whenever invoices exist
   from suppliers with no training record. Links to Client profiles.
3. New: BFF route + useSupplierFormats hook powering both.

Reviewing invoices IS the training: approve without corrections five
times in a row and the format graduates. The AI-assisted training flow
(Phase C) plugs into this same registry later.

## Files (7)
route.ts (new) · use-supplier-formats.ts (new) ·
training/format-registry.tsx (new) · client-profiles/page.tsx (2 green
blocks) · invoice-workspace.tsx (3 green blocks) · CHANGELOG.md · this

## Steps
1. Push pending commits FIRST (see above), pull, unzip, check diffs
   (green blocks only in the two edited files).
2. Commit: Training mode UI: format registry and detection banner
3. Push. Vercel redeploys.

## Verify on app.siftentry.com
1. Upload/keep an invoice from any supplier, then open Client profiles:
   the Training hero appears with that supplier under "new formats
   detected".
2. The invoice queue shows the "New format detected" banner; it links
   to Client profiles.
3. Approve an invoice untouched → the supplier moves from "new formats"
   into the collection as "Training 1/5" with one bar filled.
4. If nothing shows: the training backend commit is not deployed —
   check Railway's active deployment commit.
