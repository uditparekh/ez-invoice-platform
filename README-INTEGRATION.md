# pkg33-b — Create workspace

Built against: main @ 3517528 (pkg33 commit). Verify your local main is at
this commit before applying. If it is not: STOP and tell me the current
commit.

## Files in this zip: 8 total (5 changed, 3 new)

Web (3 changed, 2 new):
1. apps/web/src/app/api/organizations/route.ts
2. apps/web/src/components/create-workspace-dialog.tsx            (NEW)
3. apps/web/src/components/app-shell.tsx
4. apps/web/src/app/(product)/app/settings/page.tsx
5. apps/web/src/app/api/organizations/[organizationId]/members/[userId]/route.ts
   (NEW — this is the pkg33 file that did not make it into your push.
   Create the [userId] folder inside the existing members folder.
   Without it the Team access role dropdown fails with a 404.)

Docs (3 changed):
6. CHANGELOG.md
7. SIFTENTRY_CHANGELOG.md
8. README-INTEGRATION.md (this file)

## What this package delivers

1. A "+" button beside the workspace name in the header, and a "New
   workspace" card under Settings → Organization. Both open a dialog:
   workspace name + default currency. Creating it makes you its owner
   and switches you into it immediately, so the next click can be the
   client profile wizard in the right place.
2. The header now behaves as a workspace switcher once you have more
   than one workspace (it already did — you just never had two).
3. The missing pkg33 PATCH proxy route, so role changes in Team access
   actually work.

No backend changes: POST /api/v1/organizations already existed and is
covered by tests. The web app simply never called it.

## Diff expectations in GitHub Desktop

- organizations/route.ts: green POST function appended.
- create-workspace-dialog.tsx: entirely new.
- app-shell.tsx: one green import line (Plus), one green import
  (CreateWorkspaceDialog), one green useState line, a green button block
  after the role label in the header, and a green dialog mount before
  the main content div. No red. If you see red: STOP.
- settings/page.tsx: green imports (Plus, CreateWorkspaceDialog, Button),
  one green useState line at the top of OrganizationPane, and a green
  card + dialog block after the "Managed by the workspace owner" hint.
  No red.
- members/[userId]/route.ts: entirely new.
- CHANGELOG.md / SIFTENTRY_CHANGELOG.md: green only.

## Commit message

Create workspace from the app; add missing members role PATCH proxy route

## Verify steps

1. Web, from apps/web: `pnpm typecheck && pnpm lint && pnpm build` → clean.
2. Backend: `python3 -m pytest -q` → 89 passed (unchanged).
3. Push, confirm the commit on GitHub, let Vercel deploy.
4. Header: a small "+" appears right after "Owner". Click it → dialog.
5. Create a workspace named after client one. The header switches to it
   and now shows a dropdown listing Pilot Workspace and the new one.
6. Settings → Team access → change Udit Viewer's role → it saves (this
   confirms the re-shipped route).
7. Client profiles in the new workspace is empty — correct. Run the
   wizard (or Import JSON) there.
