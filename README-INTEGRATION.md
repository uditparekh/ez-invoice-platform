# SiftEntry — Calm Home Redesign (July 15, 2026)

## What this update does

Home becomes a calm "work tray" modeled on the pattern the best 2026 SaaS
products use (Linear, Mercury): the page answers "what needs me right
now?" and nothing else.

Top to bottom on the new Home:
1. Date + greeting: "Good morning — 3 things need you." (or "you're all
   clear." / "upload your first invoice.")
2. The dark Sift mode hero card: pending count + money in flight + white
   "Start sifting" button. When the queue is clear it becomes a calm
   "Queue clear" card with an Upload button instead.
3. Three stat pills — Needs review / Awaiting approval / Exceptions —
   each one tap into the matching filtered view. Exceptions turns red
   only when there are any (color = status, not decoration).
4. The work tray list: only rows that need action appear (review /
   approve / fix), plus a permanent "Upload new invoices" row.
5. The existing dismissible vendor-pattern nudge (unchanged).
6. A quiet footer: "This week: N processed · X% auto-extracted · Y
   posted · View insights".

The purple ROI hero (auto-extracted %, processed value, time saved) did
NOT disappear — it moved to the top of Insights → Overview, where
analysis belongs. Home is for doing; Insights is for measuring.

## Files (4)

| # | File | Change |
|---|------|--------|
| 1 | apps/web/src/app/(product)/app/page.tsx | Full rewrite: calm work tray (324 lines, was 365) |
| 2 | apps/web/src/app/(product)/app/analytics/page.tsx | ROI hero added to the Overview tab |
| 3 | CHANGELOG.md | Entry under [Unreleased] |
| 4 | README-INTEGRATION.md | This note |

## Steps

1. GitHub Desktop → Pull first (package built on commit 7a2b5ce).
2. Unzip over the repo root, replacing files.
3. Check the diffs: page.tsx is a rewrite so it shows large red AND
   green blocks — that is expected FOR THIS FILE ONLY. analytics/page.tsx
   should show one green block (the hero section). CHANGELOG green only.
4. Commit: Calm home redesign: work tray with Sift hero
5. Push. Vercel deploys in ~2 minutes.

## Verify on app.siftentry.com

1. Home shows the greeting, the dark Sift card with your real pending
   count and amount, the three pills, and only the action rows that
   apply. Check light AND dark mode.
2. Tap each pill and each row — every one should land on the right
   filtered view.
3. With everything cleared, Home should show "you're all clear" and the
   calm Queue-clear card — that is correct, not a bug.
4. Insights → Overview now opens with the purple ROI hero.
