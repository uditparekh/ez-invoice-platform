# SiftEntry — Mobile Nav & Header Polish, pkg22 (July 21, 2026)

## APPLY ORDER
Base: pkg21 shipped (your current main). Unzip over the repo root.
Frontend-only — 4 files.

## What this changes
1. Hamburger (mobile menu) button: was a 36px borderless ghost icon —
   nearly invisible next to the logo. Now a 44px bordered icon button
   (Apple HIG / WCAG minimum touch target), bolder 20px icon, using the
   Button "secondary" variant so it belongs to the design system.
2. Drawer close (X) and the mobile search button now share the same
   icon-button language and target size — the header reads as one
   family of controls.
3. Sign out (sidebar account card, same on web and mobile drawer):
   was a washed-out ghost fighting override classes. Now a clean
   neutral resting state that turns danger-tinted on hover/press — the
   standard sign-out affordance — with consistent radius and height.
4. Theme toggle: Light/Dark labels hide below the sm breakpoint
   (icon-only pills) so the 360px header fits hamburger + workspace
   name + search + toggle without crowding.

Also swept for overlap risks: PageHeader stacks correctly on mobile,
dropdown panels are already clamped to the viewport, nowrap usages sit
inside scrollable tables/chips. No further changes needed there.

## Files (4)
- apps/web/src/components/app-shell.tsx
- apps/web/src/components/theme-toggle.tsx
- CHANGELOG.md
- README-INTEGRATION.md (this file)

## Diff expectations
className-only red/green pairs in the two components. Any logic diff
beyond the four buttons and the toggle label span: STOP.

## Commit message
Mobile nav polish: 44px targets, coherent icon buttons, sign-out affordance

## Verify steps
1. From apps/web: pnpm typecheck && pnpm lint && pnpm build → clean.
2. On your phone (or DevTools at 360px): hamburger clearly visible and
   easy to tap; drawer opens, X matches; search button same size;
   theme toggle icon-only; nothing wraps or overlaps in the header.
3. Desktop: sidebar sign-out looks intentional; hover turns it red-
   tinted; click still signs out.
