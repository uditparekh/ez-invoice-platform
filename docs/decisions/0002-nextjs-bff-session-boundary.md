# ADR 0002: Next.js BFF And Session Boundary

- Status: Accepted
- Date: 2026-06-19

## Context

The browser application needs authenticated access to FastAPI without exposing
refresh tokens to client components or duplicating token-refresh logic across
screens.

## Decision

Use Next.js route handlers as a small backend-for-frontend boundary.

- The browser calls same-origin routes under `/api`.
- Next.js route handlers forward authorized requests to FastAPI.
- Access and refresh tokens are stored in secure, HTTP-only, same-site cookies.
- Token rotation is implemented once in `src/lib/server/api.ts`.
- FastAPI remains responsible for identity, memberships, permissions, invoice
  data, validation, and accounting workflows.
- Client components receive business data, never raw session tokens.

## Consequences

- Authentication behavior is consistent across every frontend workflow.
- Browser JavaScript cannot read the refresh token.
- FastAPI remains usable by the Streamlit pilot and future mobile clients.
- Deployment must configure `EZ_WEB_API_BASE_URL` for the private FastAPI
  service address.
