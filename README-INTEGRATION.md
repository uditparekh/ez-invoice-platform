# pkg33-c — Hotfix: creating a workspace logged you out

Built on top of pkg33-b. Apply after pkg33-b is pushed.

## Files in this zip: 5 total (2 code, 3 docs)

1. apps/web/src/components/create-workspace-dialog.tsx
2. apps/web/src/components/auth-provider.tsx
3. CHANGELOG.md
4. SIFTENTRY_CHANGELOG.md
5. README-INTEGRATION.md (this file)

## What changed

- create-workspace-dialog.tsx: after creating the workspace, reload the
  session FIRST, then switch to the new workspace. (It was the other way
  round, which briefly pointed the app at a workspace it did not know.)
- auth-provider.tsx: refresh() no longer logs you out on a transient
  failure. Only a definitive 401/403 from /api/auth/me clears the session;
  a 5xx or a network blip keeps you signed in and retries on the next
  navigation. This was a pre-existing fragility that the dialog exposed.

## Diff expectations

- create-workspace-dialog.tsx: two lines swap order inside submit(),
  comment updated. Nothing else.
- auth-provider.tsx: fetchAuthenticatedUser gains a status check and a
  small SessionRefreshError class above it; refresh()'s catch block no
  longer calls clearUser. Nothing else. If you see red elsewhere: STOP.

## Commit message

Fix logout after creating a workspace; keep session on transient refresh failures

## Verify

1. From apps/web: pnpm typecheck && pnpm lint && pnpm build → clean.
2. Push, let Vercel deploy.
3. Click "+" in the header, create a throwaway workspace ("Test 2").
   You stay signed in and the header switches to it.
4. Switch back to the Pilot workspace via the header dropdown.
   (There is no delete-workspace in the UI; "Test 2" will simply sit in
   the dropdown. Harmless — or skip step 3 and just watch the real
   client-two creation.)
