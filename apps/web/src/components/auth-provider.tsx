"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { clearWorkspaceInvoiceCache } from "@/lib/invoice-cache";
import { clearPreviewInvoices } from "@/lib/preview-invoices";
import type { AuthenticatedUser } from "@/lib/types";

interface AuthContextValue {
  user: AuthenticatedUser | null;
  activeOrganizationId: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  selectOrganization: (organizationId: string) => void;
  logout: (options?: LogoutOptions) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

type LogoutReason = "manual" | "inactive";

interface LogoutOptions {
  reason?: LogoutReason;
}

const DEFAULT_IDLE_LOGOUT_MINUTES = 30;
const IDLE_CHECK_INTERVAL_MS = 15_000;
const ACTIVITY_THROTTLE_MS = 10_000;
const IDLE_WARNING_MS = 2 * 60_000;
const LAST_ACTIVITY_STORAGE_KEY = "siftentry:last-activity-at";

function configuredIdleTimeoutMs() {
  const configured = Number(process.env.NEXT_PUBLIC_IDLE_LOGOUT_MINUTES);
  const minutes =
    Number.isFinite(configured) && configured > 0
      ? configured
      : DEFAULT_IDLE_LOGOUT_MINUTES;
  return Math.max(5, minutes) * 60_000;
}

const IDLE_TIMEOUT_MS = configuredIdleTimeoutMs();

function readLastActivityAt() {
  if (typeof window === "undefined") return Date.now();
  const raw = window.localStorage.getItem(LAST_ACTIVITY_STORAGE_KEY);
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : Date.now();
}

function writeLastActivityAt(value = Date.now()) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LAST_ACTIVITY_STORAGE_KEY, String(value));
  } catch {
    // Private-mode storage failures should not break auth or logout.
  }
}

class SessionRefreshError extends Error {}

/**
 * Returns the user, or null only when the server definitively says the
 * session is gone (401/403). Any other failure — a 5xx, a network blip, a
 * token mid-rotation — throws, so callers can keep the current session
 * instead of logging the person out over a transient error.
 */
async function fetchAuthenticatedUser() {
  const response = await fetch("/api/auth/me", { cache: "no-store" });
  if (response.status === 401 || response.status === 403) return null;
  if (!response.ok) {
    throw new SessionRefreshError(
      `Session refresh failed (${response.status})`,
    );
  }
  return (await response.json()) as AuthenticatedUser;
}

function preferredOrganizationId(user: AuthenticatedUser) {
  const savedOrganization =
    window.localStorage.getItem("siftentry-active-organization") ??
    window.localStorage.getItem("ez-active-organization");
  return user.memberships.some(
    (membership) => membership.organization_id === savedOrganization,
  )
    ? savedOrganization
    : (user.memberships[0]?.organization_id ?? null);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [activeOrganizationId, setActiveOrganizationId] = useState<
    string | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [idleWarningOpen, setIdleWarningOpen] = useState(false);

  const applyUser = useCallback((nextUser: AuthenticatedUser) => {
    writeLastActivityAt();
    setUser(nextUser);
    setActiveOrganizationId(preferredOrganizationId(nextUser));
  }, []);

  const clearUser = useCallback(() => {
    setUser(null);
    setActiveOrganizationId(null);
    setIdleWarningOpen(false);
    if (pathname !== "/login") router.replace("/login");
  }, [pathname, router]);

  const refresh = useCallback(async () => {
    try {
      const nextUser = await fetchAuthenticatedUser();
      if (nextUser) applyUser(nextUser);
      else clearUser();
    } catch {
      // Transient failure: keep the session we already have. The next
      // navigation or refresh will try again.
    } finally {
      setLoading(false);
    }
  }, [applyUser, clearUser]);

  useEffect(() => {
    let active = true;
    void fetchAuthenticatedUser()
      .then((nextUser) => {
        if (!active) return;
        if (nextUser) applyUser(nextUser);
        else clearUser();
      })
      .catch(() => {
        // Transient failure (5xx, network): keep whatever session we already
        // have. Only a definitive 401/403 (resolved to null above) signs out.
        // With no session yet, the login redirect still happens via loading=false.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [applyUser, clearUser]);

  const selectOrganization = useCallback((organizationId: string) => {
    window.localStorage.setItem(
      "siftentry-active-organization",
      organizationId,
    );
    setActiveOrganizationId(organizationId);
  }, []);

  const logout = useCallback(
    async (options: LogoutOptions = {}) => {
      try {
        await fetch("/api/auth/logout", { method: "POST" });
      } catch {
        // Even if the network is unavailable, clear this browser session.
      }
      clearWorkspaceInvoiceCache();
      clearPreviewInvoices();
      setUser(null);
      setActiveOrganizationId(null);
      setIdleWarningOpen(false);
      const destination =
        options.reason === "inactive" ? "/login?reason=inactive" : "/login";
      router.replace(destination);
      router.refresh();
    },
    [router],
  );

  useEffect(() => {
    if (!user) return;

    writeLastActivityAt();
    let lastActivityWrite = 0;

    const markActivity = () => {
      const now = Date.now();
      if (now - lastActivityWrite < ACTIVITY_THROTTLE_MS) return;
      lastActivityWrite = now;
      writeLastActivityAt(now);
      setIdleWarningOpen(false);
    };

    const checkIdle = () => {
      const idleFor = Date.now() - readLastActivityAt();
      if (idleFor >= IDLE_TIMEOUT_MS) {
        void logout({ reason: "inactive" });
        return;
      }
      setIdleWarningOpen(idleFor >= IDLE_TIMEOUT_MS - IDLE_WARNING_MS);
    };

    const activityEvents: Array<keyof WindowEventMap> = [
      "keydown",
      "pointerdown",
      "scroll",
      "touchstart",
      "mousemove",
    ];
    activityEvents.forEach((eventName) => {
      window.addEventListener(eventName, markActivity, {
        passive: true,
        capture: true,
      });
    });
    const interval = window.setInterval(checkIdle, IDLE_CHECK_INTERVAL_MS);

    return () => {
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, markActivity, {
          capture: true,
        });
      });
      window.clearInterval(interval);
    };
  }, [logout, user]);

  const value = useMemo(
    () => ({
      user,
      activeOrganizationId,
      loading,
      refresh,
      selectOrganization,
      logout,
    }),
    [user, activeOrganizationId, loading, refresh, selectOrganization, logout],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      {idleWarningOpen && user ? (
        <div
          role="status"
          className="fixed bottom-5 right-5 z-50 w-[min(360px,calc(100vw-2.5rem))] rounded-2xl border border-line-strong bg-panel p-4 shadow-2xl"
        >
          <p className="text-sm font-semibold text-ink">Still working?</p>
          <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
            This device will sign out soon to protect the workspace. Other
            devices stay signed in until they are inactive too.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              className="rounded-xl border border-line-strong bg-surface px-3 py-2 text-xs font-semibold text-ink transition hover:border-accent/40 hover:text-accent-ink"
              onClick={() => {
                writeLastActivityAt();
                setIdleWarningOpen(false);
              }}
            >
              Stay signed in
            </button>
            <button
              type="button"
              className="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white shadow-soft transition hover:bg-accent-strong"
              onClick={() => void logout()}
            >
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}
