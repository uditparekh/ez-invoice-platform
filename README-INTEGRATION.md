# SiftEntry — Pilot Readiness + Full QA Pass (July 10, 2026)

## How to apply

Unzip `siftentry-pilot-ready-qa.zip` over the repo root, letting it replace
existing files. Commit in GitHub Desktop and push.

**Suggested commit message:**
`Pilot readiness + QA: worker lifespan fix, hosted Tally connector fix, Resend bridge, e2e QA harness`

## File count

**10 files** (6 modified, 3 new, plus this note):

| # | File | Change |
|---|------|--------|
| 1 | `railway.worker.json` | NEW — Railway config for the worker service |
| 2 | `nixpacks.toml` | Python 3.11 → 3.12 |
| 3 | `siftentry_app/backend/worker.py` | FIX — standalone worker crashed on first poll (lifespan never entered) |
| 4 | `siftentry_app/backend/adapters.py` | FIX — hosted Tally posts hit a phantom 127.0.0.1:8765 connector |
| 5 | `apps/web/src/app/api/inbound/resend/route.ts` | NEW — Resend inbound → SiftEntry intake bridge |
| 6 | `apps/web/src/components/login-form.tsx` | Honor validated `?next=` redirect |
| 7 | `tests/pilot_e2e_qa.py` | NEW — 42-check end-to-end pilot QA harness |
| 8 | `docs/PILOT_INFRA_CHECKLIST.md` | Worker, spend limit, Resend, monitoring, pre-launch QA, signup order |
| 9 | `CHANGELOG.md` | All entries under [Unreleased] |
| 10 | `README-INTEGRATION.md` | This note |

## The two bugs QA caught (both would have hit the pilot on day one)

**1. The worker service crashed instantly.** `python -m
siftentry_app.backend.worker` — the exact Railway start command — died on
its first poll with `'State' object has no attribute 'repository'`. The
repository/storage/adapters are wired inside the FastAPI lifespan, which
only an ASGI server runs; the standalone worker never entered it. The 54
unit tests all pass because TestClient enters the lifespan automatically —
only running the real entrypoint exposed it. Fixed: the worker now enters
the lifespan context explicitly. Verified by running the actual entrypoint.

**2. Hosted Tally posting was broken for profile-based clients.** The
legacy default connector settings are `enabled: true` at
`http://127.0.0.1:8765` — correct when the Streamlit pilot runs on the
client's own Windows machine, wrong on Railway, where every web-initiated
Tally post or dry run tried to reach a connector bridge on the server
itself and failed with a confusing connection error. Fixed: client profiles
that define no local bridge URL now explicitly disable that default. Cloud
desktop connectors are unaffected (they use the claim/results endpoints).

## The QA harness (keep running this)

`python tests/pilot_e2e_qa.py` from the repo root — 42 checks over the full
two-client lifecycle on a throwaway SQLite database: auth + session
rotation, two orgs, Tally + QuickBooks profiles, upload/parse/evidence, the
reviewer correct→validate→approve flow, send-back, dry-run posting, batch
jobs through the worker, the Tally connector claim/results loop (with
wrong-token rejection), document download, inbound email intake (with
wrong-secret rejection), invitations, password reset, cross-org isolation,
learning export/import, retention cleanup, and AI-off confirmation.

Final state: **42/42 QA checks, 54/54 unit tests, ruff clean.** Frontend
unchanged since the previous verified build (typecheck 0, lint 0, 42/42
routes).

## Required Tally profile values (QA-proven)

Dry-run preflight BLOCKS posting until these are set on a Tally client
profile: `company_name` (exact TallyPrime company name), plus
`purchase_ledger`, `tax_mode`, `tax_ledger`, and `round_off_ledger` for
India GST clients. The checklist section 8 records this.

## Known parser-quality expectation (not a bug)

The deterministic parsers are format-specific. On unfamiliar synthetic
layouts they misread totals/GSTIN — by design, the review screen exists to
correct this and corrections feed vendor memory. Onboarding rule: run 5-10
of each client's REAL invoices through review before go-live and check the
correction rate; do not judge extraction on invoices the parsers were never
built for.
