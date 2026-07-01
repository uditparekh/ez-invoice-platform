# SiftEntry Documentation Index

Use this index to avoid hunting through the repo.

## Start Here

| Document | Use it for |
|---|---|
| `../README.md` | Project overview, local run commands, and test/build commands |
| `../PROJECT_MAP.md` | File ownership rules, current structure, roadmap state, and default demo commands |
| `ROADMAP_STATUS.md` | Commit checklist and practical product milestone tracking |

## Runbooks

| Document | Use it for |
|---|---|
| `PILOT_RUNBOOK.md` | Local pilot/demo flow, client profile workflow, and client handoff checklist |
| `TALLY_CONNECTOR_WINDOWS.md` | Windows Tally connector packaging and setup |
| `PRODUCTION_DEPLOYMENT.md` | Pilot/staging/production infrastructure requirements |

## Architecture Decisions

| Document | Use it for |
|---|---|
| `decisions/0001-monorepo-and-frontend-migration.md` | Why Streamlit, FastAPI, and Next.js live together for now |
| `decisions/0002-nextjs-bff-session-boundary.md` | Why the browser talks to Next.js API routes instead of directly to FastAPI |
| `decisions/0003-siftentry-brand-system.md` | Brand, naming, logo, and visual system direction |

## Pilot-Specific Docs Kept Beside Scripts

These remain under `ez_invoice_app/` because they are paired with the Streamlit
pilot, Windows `.bat` launchers, or local client setup flows.

| Document | Use it for |
|---|---|
| `../ez_invoice_app/README.md` | Streamlit pilot and local backend bridge details |
| `../ez_invoice_app/CLIENT_WINDOWS_SETUP.md` | Windows client setup for running the pilot locally |
| `../ez_invoice_app/TALLY_DEMO_CHECKLIST.md` | Tally pilot checklist |
| `../ez_invoice_app/API_ARCHITECTURE.md` | Historical migration boundary for the first API slice |
| `../ez_invoice_app/APP_AUDIT.md` | Historical Streamlit audit notes |
| `../ez_invoice_app/ZOHO_BOOKS_SETUP.md` | Zoho Books setup notes |
