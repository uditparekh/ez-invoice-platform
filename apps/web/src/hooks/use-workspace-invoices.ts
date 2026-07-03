"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { mergePreviewInvoices } from "@/lib/preview-invoices";
import type { Invoice, InvoiceStatus } from "@/lib/types";

interface UseWorkspaceInvoicesOptions {
  status?: InvoiceStatus;
  limit?: number;
}

export function useWorkspaceInvoices({
  status,
  limit = 100,
}: UseWorkspaceInvoicesOptions = {}) {
  const { activeOrganizationId: organizationId } = useAuth();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadInvoices = useCallback(
    async (signal?: AbortSignal) => {
      if (!organizationId) {
        setInvoices([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams({
          organization_id: organizationId,
          limit: String(limit),
        });
        if (status) query.set("status", status);
        const response = await fetch(`/api/invoices?${query}`, {
          cache: "no-store",
          signal,
        });
        if (!response.ok) throw new Error("Unable to load invoice workspace.");
        setInvoices(mergePreviewInvoices((await response.json()) as Invoice[]));
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setError((loadError as Error).message);
        }
      } finally {
        setLoading(false);
      }
    },
    [organizationId, limit, status],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadInvoices(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadInvoices]);

  return {
    invoices,
    loading,
    error,
    reload: () => loadInvoices(),
  };
}
