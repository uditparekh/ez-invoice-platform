# ADR 0001: Monorepo And Incremental Frontend Migration

- Status: Accepted
- Date: 2026-06-19

## Context

EZ-Invoice has a working Streamlit pilot, a FastAPI backend, PDF parsers, and
multiple accounting integrations. A modern customer-facing web application is
needed without risking the proven accounting workflow.

## Decision

Use one private Git monorepo as the platform source of truth.

- Keep `ez_invoice_app/` as the operational Python pilot and backend.
- Build the new customer-facing application in `apps/web/` using Next.js and
  TypeScript.
- Keep FastAPI as the permanent API and accounting integration boundary.
- Replace Streamlit screens incrementally only after their Next.js equivalents
  pass workflow and visual testing.
- Keep generated ZIP packages, databases, uploaded documents, and credentials
  outside version control.

## Consequences

- The working demo remains available throughout migration.
- Backend and frontend changes can be versioned together.
- Tagged releases provide reproducible client packages.
- Python paths and Windows client scripts remain stable during the first
  frontend milestone.
