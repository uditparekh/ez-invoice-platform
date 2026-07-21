# SiftEntry — Design-System Consolidation, pkg21 (July 21, 2026)

## APPLY ORDER
Base: pkg20 shipped (your current main). Unzip over the repo root.
Frontend-only — 8 files, no backend changes.

## What this changes (structural, not cosmetic)
The audit found the app's 40 hardcoded hex colors were almost all your
own design tokens pasted as literals — the Sift page was built "always
dark" by copying the dark values instead of scoping the dark class.
This package removes every hardcoded color in the app (40 → 0):

1. Sift page: root now carries the `dark` scope and every color is a
   semantic class (bg-surface, border-line, text-ink-secondary, …).
   Any future token tweak now updates Sift automatically. Bonus fix:
   chips/gradients that previously resolved LIGHT token values onto the
   dark background (when the user was in light mode) now resolve
   correctly.
2. Training-hero gradient (Client profiles + Home use the same one) is
   now three named tokens: --hero-from/-via/-to.
3. Analytics gradients + the cyan stat color on dark banners are named
   tokens: --accent-grad-via/-to, --stat-on-dark.
4. Theme toggle: its one literal is now var(--canvas).
The only remaining hex literals are layout.tsx's meta theme-color tags,
which cannot use CSS variables.

## Files (8)
- apps/web/src/app/globals.css                      (6 new tokens)
- apps/web/src/app/(product)/app/sift/page.tsx      (dark scope + semantic classes)
- apps/web/src/app/(product)/app/page.tsx           (hero tokens)
- apps/web/src/app/(product)/app/analytics/page.tsx (gradient tokens)
- apps/web/src/components/training/format-registry.tsx
- apps/web/src/components/theme-toggle.tsx
- CHANGELOG.md
- README-INTEGRATION.md (this file)

## Diff expectations
Red/green pairs on className strings only — hex arbitrary values
becoming semantic classes or var() references. globals.css: green-only
token block insert. Any logic-looking diff: STOP.

## Deliberate visual normalizations (eyeball after deploy)
Three tiny shifts where literals sat between tokens — all normalized to
the locked spec:
- Sift PDF rail background: #0F1524 → shell (#131A2B), slightly lighter
- Sift empty-panel gradient top: #1B2238 → surface-strong (#212940)
- Sift "open queue" CTA gradient: light accent/cyan → dark accent/cyan
  (brighter, now matching the progress bar's gradient)
If any of these read wrong to you on the live Sift page, tell me which
and it's a one-line token tweak.

## Commit message
Design-system consolidation: zero hardcoded colors, Sift on dark tokens

## Verify steps
1. From apps/web: pnpm typecheck && pnpm lint && pnpm build → clean.
2. After deploy, in BOTH light and dark app themes: Sift page (dark
   focus mode intact, chip/CTA/progress gradients consistent), Home
   hero, Client profiles training hero, Analytics banner + gradient
   card.
3. Optional proof: grep -rn "#[0-9A-Fa-f]\{6\}" apps/web/src --include="*.tsx" | grep -v layout.tsx → nothing.
