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

import type { AuthenticatedUser } from "@/lib/types";

interface AuthContextValue {
  user: AuthenticatedUser | null;
  activeOrganizationId: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  selectOrganization: (organizationId: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchAuthenticatedUser() {
  const response = await fetch("/api/auth/me", { cache: "no-store" });
  if (!response.ok) return null;
  return (await response.json()) as AuthenticatedUser;
}

function preferredOrganizationId(user: AuthenticatedUser) {
  const savedOrganization = window.localStorage.getItem(
    "ez-active-organization",
  );
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
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);

  const applyUser = useCallback((nextUser: AuthenticatedUser) => {
    setUser(nextUser);
    setActiveOrganizationId(preferredOrganizationId(nextUser));
  }, []);

  const clearUser = useCallback(() => {
    setUser(null);
    setActiveOrganizationId(null);
    if (pathname !== "/login") router.replace("/login");
  }, [pathname, router]);

  const refresh = useCallback(async () => {
    try {
      const nextUser = await fetchAuthenticatedUser();
      if (nextUser) applyUser(nextUser);
      else clearUser();
    } catch {
      clearUser();
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
        if (active) clearUser();
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [applyUser, clearUser]);

  const selectOrganization = useCallback((organizationId: string) => {
    window.localStorage.setItem("ez-active-organization", organizationId);
    setActiveOrganizationId(organizationId);
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setUser(null);
    setActiveOrganizationId(null);
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = useMemo(
    () => ({
      user,
      activeOrganizationId,
      loading,
      refresh,
      selectOrganization,
      logout,
    }),
    [
      user,
      activeOrganizationId,
      loading,
      refresh,
      selectOrganization,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}
