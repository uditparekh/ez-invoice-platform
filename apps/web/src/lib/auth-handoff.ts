import type { AuthenticatedUser } from "@/lib/types";

// One short-lived, in-memory handoff from a successful sign-in response. Never
// persist tokens or identity in browser storage; server authorization still
// protects every request. /auth/me revalidates this identity in the background.
let handoff: { user: AuthenticatedUser; expires: number } | null = null;
export function setAuthHandoff(user: AuthenticatedUser) {
  handoff = { user, expires: Date.now() + 30_000 };
}
export function readAuthHandoff() {
  return handoff && handoff.expires > Date.now() ? handoff.user : null;
}
export function clearAuthHandoff() {
  handoff = null;
}
