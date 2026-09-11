"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { invoiceCache } from "@/lib/invoice-cache";
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
  const cacheKey = `${organizationId ?? ""}|${status ?? ""}|${limit}`;
  const cached = invoiceCache.get(cacheKey);
  const [invoices, setInvoices] = useState<Invoice[]>(cached ?? []);
  const [responseKey, setResponseKey] = useState(cacheKey);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState("");

  const loadInvoices = useCallback(
    async (signal?: AbortSignal) => {
      if (!organizationId) {
        setInvoices([]);
        setResponseKey(cacheKey);
        setLoading(false);
        return;
      }

      const hit = invoiceCache.get(cacheKey);
      if (hit) {
        setInvoices(hit);
        setResponseKey(cacheKey);
        setLoading(false);
      } else {
        setLoading(true);
      }
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
        const fresh = mergePreviewInvoices(
          organizationId,
          (await response.json()) as Invoice[],
        );
        if (signal?.aborted) return;
        invoiceCache.set(cacheKey, fresh);
        setInvoices(fresh);
        setResponseKey(cacheKey);
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setInvoices(hit ?? []);
          setResponseKey(cacheKey);
          setError((loadError as Error).message);
        }
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [organizationId, limit, status, cacheKey],
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
    invoices: responseKey === cacheKey ? invoices : [],
    loading: loading || responseKey !== cacheKey,
    error: responseKey === cacheKey ? error : "",
    reload: () => loadInvoices(),
  };
}
