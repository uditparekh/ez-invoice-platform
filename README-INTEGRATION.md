# SiftEntry — Tally Connector Productization, pkg18 (July 20, 2026)

## APPLY ORDER — read first
1. Open GitHub Desktop. Confirm your latest commit is "Training mode UI"
   and that it is pushed (no "Push origin" pending). If pending, push
   first and verify on github.com.
2. Unzip this package over the repo root, replacing files when asked.
3. In GitHub Desktop, review the changed-files list against the counts
   below. STOP IF YOU SEE RED BLOCKS (deleted lines) in any file NOT
   listed here — that means the zip landed in the wrong folder.
4. One deletion is intentional and must be done by hand (zips cannot
   delete files): in the repo, delete this folder entirely —
   apps/web/src/app/api/integrations
   (it contains only tally/test-connector/route.ts, which is dead code
   that tried to reach the client's 127.0.0.1 from Vercel).

## What this adds
1. Connector heartbeat: the Windows connector now checks in with
   SiftEntry on every poll — including when TallyPrime is closed — so
   the platform always knows it is alive, which machine it is on, and
   which version it runs.
2. Live status in the web app: Integrations → Tally now shows a
   "Windows connector status" card per client profile — Connected /
   Disconnected / Waiting badge, last check-in, Tally company, computer
   name + connector version, TallyPrime detected, and last posting —
   auto-refreshing every 15 seconds. The old localhost test card (which
   could never work from Vercel) is gone.
3. Client kit: a downloadable zip your client's accountant can follow
   solo — linked right on the Tally page and served from
   app.siftentry.com/downloads/SiftEntry-Tally-Connector-Kit.zip after
   deploy. Plain-language README, one-time setup script, start script,
   optional start-with-Windows.
4. Connector v0.3.0: needs only `requests` on the client PC, reuses the
   settings saved once in its status window, and the RUN bat starts
   production cloud polling directly.

## Files (20 changed/added in this zip + 1 manual folder deletion)

Backend (4):
- siftentry_app/backend/models.py — claim request carries connector
  host/version/tally state; new heartbeat + status models
- siftentry_app/backend/repository.py — connector_heartbeats table
  (auto-creates on SQLite and PostgreSQL, no manual migration on
  Railway) + record/read heartbeat + latest-posting-per-profile
- siftentry_app/backend/main.py — heartbeat recorded on every claim;
  new POST /api/v1/connectors/tally/heartbeat (connector-token auth);
  new GET /api/v1/organizations/{id}/connectors/tally/status (member
  auth); 60-second online window constant
- tests/test_api.py — new test: heartbeat auth rejected without/with
  wrong token, never-seen → heartbeat → claim status progression,
  status endpoint requires sign-in

Connector (4):
- siftentry_app/tally_connector_runtime.py — v0.3.0; sends
  host/version/tally state with claims; sends a heartbeat instead of
  going silent when Tally is unreachable
- siftentry_app/tally_connector_agent.py — Flask optional (cloud mode
  needs only requests); cloud polling falls back to the saved config
  from the status window
- siftentry_app/RUN_TALLY_CONNECTOR_WINDOWS.bat — cloud polling against
  https://app.siftentry.com
- siftentry_app/TALLY_DEMO_CHECKLIST.md — rewritten for the production
  flow (app.siftentry.com + connector + TallyPrime, nothing else local)

Client kit (7):
- packaging/client-kit/README-START-HERE.txt — accountant guide
- packaging/client-kit/SETUP_WINDOWS.bat — one-time pip install
- packaging/client-kit/START_CONNECTOR.bat — opens the status window
- packaging/client-kit/INSTALL_STARTUP.bat / UNINSTALL_STARTUP.bat
- packaging/client-kit/make_client_kit.py — rebuilds the kit zip
- apps/web/public/downloads/SiftEntry-Tally-Connector-Kit.zip — the
  generated kit (committed so Vercel serves it; rerun make_client_kit.py
  after future connector changes)

Web (3):
- apps/web/src/lib/types.ts — connector status types
- apps/web/src/app/api/organizations/[organizationId]/connectors/tally/status/route.ts
  — new proxy route (net route count unchanged: one added, one deleted)
- apps/web/src/components/accounting/accounting-system-page.tsx —
  status card replaces the localhost test card; Tally stepper updated;
  kit download row added

Docs (2):
- CHANGELOG.md — pkg18 entries
- README-INTEGRATION.md — this file

## Diff expectations
- Green-only additions everywhere EXCEPT:
  - accounting-system-page.tsx: large red block removing TallySetupCard's
    URL/token inputs and test buttons, replaced by the status card
  - tally_connector_runtime.py: small red blocks in claim_cloud_jobs and
    poll_once where heartbeat behavior was added
  - tally_connector_agent.py: red blocks around the Flask import and
    run_cloud_polling config fallback
  - RUN_TALLY_CONNECTOR_WINDOWS.bat and TALLY_DEMO_CHECKLIST.md: fully
    rewritten
  - CHANGELOG.md: green insert under [Unreleased] only
- If you see red blocks in backend/main.py beyond small inserts at the
  claim endpoint and two new endpoint blocks near the end: STOP.

## Commit message
Tally connector productization: heartbeat, live status card, client kit

## Verify steps
1. Backend: `python3 -m pytest -q` → 62 passed (was 61).
2. Web, from apps/web: `pnpm typecheck && pnpm lint && pnpm build` →
   all clean; build lists
   /api/organizations/[organizationId]/connectors/tally/status and no
   longer lists /api/integrations/tally/test-connector.
3. Push, let Railway + Vercel deploy.
4. Open app.siftentry.com → Integrations → Tally. The status card shows
   your Tally profile with "Waiting for first check-in" and the correct
   Tally company name. The "Download the Windows connector kit" link
   downloads the zip.
5. On the Tally Windows machine, start the connector (status window or
   RUN bat). Within ~15s the web card flips to Connected with the
   machine name and v0.3.0. Close TallyPrime: within ~30s the card shows
   Connected but "TallyPrime: Not detected — open TallyPrime". Stop the
   connector: within ~60s the card shows Disconnected.
6. Optional: rebuild the installer .exe later on Windows — it picks up
   v0.3.0 automatically; existing installed 0.2.x connectors keep
   working (they just heartbeat only while Tally is open).

## Notes
- The token you already store in each Tally client profile's connection
  settings is the same one the accountant types into the connector —
  nothing new to provision.
- The 60-second "online" window = 4 missed polls at the default 15s.
