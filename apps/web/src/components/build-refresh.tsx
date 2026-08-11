"use client";

import { useEffect, useRef } from "react";

const POLL_INTERVAL_MS = 60_000;

/**
 * Keeps installed PWA sessions on the current deployment.
 *
 * An installed PWA can keep an old JS bundle alive for days because the app
 * shell is never re-requested — the user sees a stale build and has to clear
 * the app data to pick up a fix. This polls a tiny build-id endpoint and, when
 * the deployed build changes underneath a running session, reloads once so the
 * fresh bundle is fetched.
 *
 * Deliberately not a service worker: there is no service worker in this app,
 * and adding one would introduce a cache layer rather than remove one.
 */
export function BuildRefresh() {
  const knownBuildId = useRef<string | null>(null);
  const reloading = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function checkBuild() {
      if (cancelled || reloading.current) return;
      if (typeof document !== "undefined" && document.hidden) return;
      try {
        const response = await fetch("/api/system/build", {
          cache: "no-store",
          headers: { "Cache-Control": "no-cache" },
        });
        if (!response.ok) return;
        const payload = (await response.json()) as { build_id?: string };
        const buildId = payload?.build_id;
        if (!buildId || cancelled) return;

        if (knownBuildId.current === null) {
          knownBuildId.current = buildId;
          return;
        }
        if (knownBuildId.current !== buildId) {
          reloading.current = true;
          window.location.reload();
        }
      } catch {
        // Offline or a transient failure: try again on the next tick.
      }
    }

    void checkBuild();
    const timer = window.setInterval(checkBuild, POLL_INTERVAL_MS);
    window.addEventListener("focus", checkBuild);
    document.addEventListener("visibilitychange", checkBuild);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", checkBuild);
      document.removeEventListener("visibilitychange", checkBuild);
    };
  }, []);

  return null;
}
