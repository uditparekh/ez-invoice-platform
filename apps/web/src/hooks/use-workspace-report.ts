"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";

/** A response belongs to its exact workspace/query; never flash another tenant's data. */
export function useWorkspaceReport<T>(resource: string, query: string) {
  const { activeOrganizationId } = useAuth();
  const key = `${activeOrganizationId}/${resource}?${query}`;
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    key: string;
    revision: number;
    data?: T;
    error?: string;
  }>({ key: "", revision: -1 });
  useEffect(() => {
    if (!activeOrganizationId) return;
    const controller = new AbortController();
    void fetch(
      `/api/organizations/${encodeURIComponent(activeOrganizationId)}/${resource}?${query}`,
      {
        cache: "no-store",
        signal: controller.signal,
      },
    )
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            "This report is temporarily unavailable. Please try again.",
          );
        const data = (await response.json()) as T;
        if (!controller.signal.aborted) setState({ key, revision, data });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted)
          setState({ key, revision, error: error.message });
      });
    return () => controller.abort();
  }, [activeOrganizationId, resource, query, key, revision]);
  const current = state.key === key && state.revision === revision;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: Boolean(activeOrganizationId) && !current,
    reload: () => setRevision((value) => value + 1),
    organizationId: activeOrganizationId,
  };
}
