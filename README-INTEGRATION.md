# SiftEntry — Demo Read-Only Hardening, pkg31 (July 24, 2026)

## APPLY ORDER
Base: current main (the one with pkg30 + demo workspace). Unzip over
the repo root. Backend-only — 5 files, no frontend or env changes.

## What this changes
Your ask: the public demo must be view-only with fake invoices only.
The viewer role already blocked most org-scoped writes, but the shared
demo login could still: create a NEW organization (becoming its owner,
able to upload anything under the public demo credentials), accept
invitations into other workspaces, and change the shared demo
password. This package closes all of it with one guard at the auth
chokepoint every authenticated endpoint passes through: the demo
account can read anything it can see, and every write returns 403
("The public demo is read-only...") — except the exact refresh and
logout routes. Because nothing can be uploaded or modified,
the demo's data stays the synthetic seed (DEMO-QB-1001 / DEMO-ZOHO-1002
etc.) by construction. Future endpoints are covered automatically —
the guard sits in get_current_user, not per-route.

## Files (5)
- siftentry_app/backend/auth.py        (the guard)
- tests/test_api.py                    (new guard test)
- CHANGELOG.md
- docs/SIFTENTRY_CHANGELOG.md          (pkg31 row)
- README-INTEGRATION.md                (this file)

## Diff expectations
auth.py: one green helper block + a 2-line change where
get_current_user returns (return authenticated_user(...) becomes
user = ... / guard / return user). tests/test_api.py: one green test
inserted between the existing demo tests, including a change-password
escape attempt. Any red beyond that: STOP.

## Commit message
Demo hardening: read-only enforced at auth layer for the public demo

## Verify steps
1. `python3 -m pytest -q` → 75 passed (was 74).
2. Push; Railway deploys.
3. In production: open the demo (Try demo), confirm browsing works,
   then try any write — e.g. open Settings and attempt a save — expect
   a clear "read-only" error. Sign out from the demo still works.
4. Optional adversarial minute: as demo, attempt to create a workspace
   if the UI offers it anywhere — expect the same 403.

## Notes
- UI may still SHOW some buttons to the demo viewer; pressing them now
  fails safely server-side. Hiding them is cosmetic polish for later.
- Still open from our earlier review (next package, not this one):
  the guard against connector-enabled settings on a second Tally
  profile per org, and the profile-aware claiming audit.
