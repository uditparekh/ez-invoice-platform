# SiftEntry — Full Review & Cleanup Pass (July 5, 2026)

## How to apply

Unzip `siftentry-review-cleanup.zip` over the repo root, letting it replace
existing files. Then commit in GitHub Desktop and push.

**Suggested commit message:**
`Review pass: headless backend imports, Postgres admin-URL fix, dead-code cleanup`

## File count

**14 files** in this package (13 modified + this note):

| # | File | Change |
|---|------|--------|
| 1 | `siftentry_app/tally_integration.py` | Streamlit import optional + headless fallback |
| 2 | `siftentry_app/qb_integration.py` | Streamlit import optional + headless fallback |
| 3 | `siftentry_app/zoho_integration.py` | Streamlit import optional + headless fallback |
| 4 | `siftentry_app/backend/db.py` | Postgres admin-URL fix; dead import removed |
| 5 | `siftentry_app/backend/main.py` | Unused exception binding removed |
| 6 | `siftentry_app/backend/repository.py` | Dead import removed |
| 7 | `siftentry_app/backend/worker.py` | Dead import removed |
| 8 | `siftentry_app/backend/profile_recommendation.py` | Dead import removed |
| 9 | `siftentry_app/item_classifier.py` | Dead import removed |
| 10 | `siftentry_app/app.py` | Dead import removed |
| 11 | `tests/test_ai_anthropic.py` | Dead import removed |
| 12 | `apps/web/src/lib/server/api.ts` | Forward Content-Disposition on PDF downloads |
| 13 | `CHANGELOG.md` | Review pass recorded under [Unreleased] |
| 14 | `README-INTEGRATION.md` | This note |

## Bugs fixed

**1. Backend hard-required Streamlit (deployment blocker).**
`backend/main.py` imports `build_tally_xml` from `tally_integration.py`, which
imported `streamlit` at module top — so a production container installing
`requirements-api.txt` (documented as "production API dependencies only")
crashed on startup with `ModuleNotFoundError: No module named 'streamlit'`.
The same applied to the worker, and QuickBooks/Zoho posting paths. All three
integration modules now import Streamlit optionally and fall back to a
minimal headless shim: the API and worker start cleanly, Tally posting works
via file/env settings, and QuickBooks/Zoho report "not connected" gracefully
when no pilot session exists. Verified by importing the full API and worker
with Streamlit imports blocked.

**2. Postgres admin-URL corruption in `db.create_database_if_missing`.**
`database_url.replace(f"/{dbname}", "/postgres")` replaces every occurrence,
so `postgresql://siftentry:pw@host/siftentry` became
`postgresql://postgres:pw@host/postgres` — wrong username. Now rebuilt from
the parsed URL path only.

**3. PDF downloads lost their filename.**
The Next.js BFF proxy forwarded only `Content-Type`; it now forwards
`Content-Disposition` too, so downloaded invoice PDFs keep their original
name.

## Cleanup

Removed dead imports and unused exception bindings flagged by ruff across
backend, pilot, and tests. Nothing behavioral was touched in `app.py` beyond
one unused top-level import — the 9k-line Streamlit pilot is working code and
was deliberately left alone otherwise.

## Verification (all run on this exact code)

- Python: `ruff check` clean (E9/F401/F811/F821), **54/54 tests pass**
- Headless simulation: API `create_app` + worker import succeed with
  Streamlit blocked; adapters degrade gracefully
- Frontend: `tsc --noEmit` **0 errors**, `eslint` **0 errors**,
  `next build` **41/41 routes**

## Observations (no action taken — flag for later passes)

- The `next=` redirect param the middleware sets on `/login` is never
  consumed; login always lands on `/app/invoices`. Harmless, minor UX.
- Inbound email intake uses one global secret and takes `organization_id`
  from the request body — fine for the pilot, worth per-org routing before
  opening it to multiple customers.
- The rename pass (`EZ_API_*` → `SIFTENTRY_*`, `ez_` cookies) and deployment
  pass remain as previously sequenced; nothing in this pass conflicts with
  them.
