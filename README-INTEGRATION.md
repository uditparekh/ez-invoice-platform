# SiftEntry — Training Mode, Phase B backend (July 19, 2026)

## IMPORTANT — apply order
This package is built ON TOP of the activity-timeline commit. Only apply
it AFTER the timeline is committed and pushed. main.py and repository.py
in this zip CONTAIN the timeline code plus the new training code — if
your repo already has the timeline, the diff shows only green training
blocks. If the diff shows the timeline code being REMOVED (red), stop:
your timeline commit is missing — push it first.

## What this adds (the brain; the buttons come next session)
1. supplier_formats table: one record per supplier format per workspace,
   with status training/trusted, samples count, clean streak, and a
   hints slot reserved for the AI format hints.
2. Graduation logic wired into invoice approval: approve with zero
   corrections → streak +1; any correction → streak resets to 0 (and a
   trusted format demotes back to training). Five consecutive clean
   approvals → trusted. Approval itself is never blocked by this.
3. GET /api/v1/organizations/{id}/supplier-formats → every format with
   its status and progress, plus "untrained": suppliers appearing in
   invoices that have no format record yet — the "new format detected"
   feed the UI will surface.

## Files (5)
main.py (+approve hook, +endpoint) · repository.py (+schema, +methods)
· tests/test_supplier_formats.py (new, 3 tests) · CHANGELOG.md · this file

## Steps
1. Pull first. Confirm your latest commit is the activity timeline.
2. Unzip over repo root → check diffs per the note above.
3. Commit: Training mode backend: supplier format registry
4. Push — Railway redeploys; the new table creates itself on startup.

## Verify (after deploy)
Approve any invoice without editing it, then in the browser open
https://siftentry-api-production.up.railway.app/docs → GET
/organizations/{id}/supplier-formats (authorize with your login token) —
or simply wait for next session's UI. Tests: python3 -m pytest -q → 61.
