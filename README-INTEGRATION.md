# pkg33 — Consolidation & trust

Built against: main @ 4c6bd2d (pkg32 commit). Verify your local main is at
this commit before applying. If it is not: STOP and tell me the current
commit.

## Files in this zip: 12 total (9 changed, 1 new, 1 deleted, 1 this README)

Apply by copying each file to the same path in the repo. Overwrite when
prompted. ONE FILE MUST BE DELETED BY HAND — see step 0.

0.  DELETE apps/web/src/app/(product)/app/gl-mapping/page.tsx
    (and the now-empty gl-mapping folder). This orphaned demo page is not
    in the zip; removing it is part of the package.

Backend (2 changed):
1.  siftentry_app/backend/models.py
2.  siftentry_app/backend/main.py

Tests (1 changed):
3.  tests/test_api.py

Web (4 changed, 1 new):
4.  apps/web/src/components/client-profiles-panel.tsx
5.  apps/web/src/components/client-profiles/profile-wizard.tsx
6.  apps/web/src/components/settings/team-management-panel.tsx
7.  apps/web/src/app/layout.tsx
8.  apps/web/src/app/api/organizations/[organizationId]/members/[userId]/route.ts
    (NEW — create the [userId] folder inside the existing members folder)

Docs (3 changed):
9.  CHANGELOG.md
10. SIFTENTRY_CHANGELOG.md
11. README-INTEGRATION.md (this file)

## What this package delivers

1. Profile library collapses to a slim rail. Starts collapsed with one
   profile (the editor gets the width), expanded with several. Your
   toggle is remembered. You can still switch profiles from the rail.
2. "Ledgers and stock items" rebuilt: three concept groups (where
   purchases post / default stock item / item mapping rules), helper
   text under every field, optional fields marked, stock fields hidden
   for ledger-only modes. Mapping row replaced by count + link to
   Rules & mapping, which is now the one place mappings are edited.
3. AI readiness as a sentence. No more 43%. The status names what is
   missing or what would improve accuracy. Guidance, validation rules,
   and posting expectations are now labelled recommended (they were
   marked required by a panel that disagreed with the real activation
   gate). Readiness card lives inside the training panel; each
   instruction box shows its own inline status.
4. Role changes without re-inviting: a role dropdown on each Team
   access row (not your own). Backend guards: only owners can promote
   to owner or change an owner; the last owner cannot be demoted.
5. Wizard "Posting expectations" now saves to the right field.
6. Viewport fix: installed PWA gets safe-area handling on notched phones.
7. Orphaned /app/gl-mapping demo route removed.

Deliberately NOT in this package: the ledger fields stay plain text
inputs. They become verified dropdowns fed by Tally in pkg34 (master
sync) — building dropdowns twice would be wasted work.

## Diff expectations in GitHub Desktop

- models.py: one small green class (MemberRoleUpdate).
- main.py: one green import line and one green endpoint block before
  list_organization_invitations. No red. If you see red: STOP.
- test_api.py: green-only appended tests.
- client-profiles-panel.tsx: the large one. Expect: green imports
  (ArrowRight, ChevronUp, PanelLeftClose, PanelLeftOpen, Link); a green
  constants/helper block near postingModes; a red/green block replacing
  the <aside>; a red block removing updatePrimaryMapping and the
  `mapping` const; a large red/green block replacing the "Ledgers,
  items, and mapping" SettingsPanel; a red block removing the "AI/OCR
  readiness" SettingsPanel and a green block inside the training panel;
  red/green inside getAiReadiness (three required: true → false, score
  block → headline); red/green in TextField/TextAreaField signatures
  and a new FieldGroup component. If you see red inside the connector,
  activation, or Tally sections: STOP.
- profile-wizard.tsx: one red/green line (extraction_instructions →
  posting_expectations).
- team-management-panel.tsx: one changed import line, a green handler
  block, a red/green block in the member row.
- layout.tsx: red/green on the viewport object and the import line.
- members/[userId]/route.ts: entirely new.
- CHANGELOG.md / SIFTENTRY_CHANGELOG.md: green only.

## Commit message

Profile editor consolidation, AI readiness as plain language, member role changes

## Verify steps

1. Backend: `python3 -m pytest -q` → 89 passed (was 86).
2. Web, from apps/web: `pnpm typecheck && pnpm lint && pnpm build` → all
   clean; 41 static pages (was 42).
3. Push, confirm the commit on GitHub, let Railway + Vercel deploy.
4. Client profiles: with one profile the library shows as a narrow rail
   on the left and the editor is wide. Click the rail toggle → it
   expands smoothly; reload → it stays expanded (remembered).
5. Ledgers and stock items: three grouped boxes with helper text; on a
   ledger-only profile the stock box is replaced by a one-line note.
6. AI extraction and parser training: a sentence like "AI extraction is
   ready for testing. 3 optional items would improve accuracy: ..." —
   no percentage. Type into Extraction instructions → its pill flips to
   "Sent with every extraction".
7. Settings → Team access: the Udit Viewer row has a role dropdown.
   Change it to Accountant → row updates, message confirms. Your own
   Owner row has no dropdown.
8. /app/gl-mapping returns 404.
