# SiftEntry Web

The customer-facing SiftEntry application is a Next.js App Router project
written in strict TypeScript. It runs alongside the proven Streamlit pilot and
uses FastAPI as the permanent domain and accounting-integration boundary.

## Architecture

- Browser requests use same-origin Next.js route handlers under `/api`.
- Route handlers call FastAPI and keep access and refresh tokens in secure,
  `httpOnly`, same-site cookies.
- Expired access tokens are refreshed in one server-only module.
- React components never receive or persist accounting API credentials.
- The active organization comes from authenticated FastAPI memberships.

## Run Locally

Start FastAPI from the repository root:

```bash
export EZ_API_JWT_SECRET="replace-with-a-long-random-secret"
python3 -m uvicorn siftentry_app.backend.main:app --reload --port 8000
```

Start the web app:

```bash
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

Open `http://127.0.0.1:3000`.

## Quality Checks

```bash
pnpm lint
pnpm typecheck
pnpm build
```

## Source Layout

```text
src/app/                  Routes and same-origin API handlers
src/components/           Reusable product and workflow components
src/lib/server/           Server-only FastAPI and session boundary
src/lib/types.ts          Frontend representation of API contracts
src/lib/utils.ts          Formatting and class-name helpers
src/proxy.ts              Protected application route guard
```
