"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";

export interface SupplierFormat {
  supplier_key: string;
  supplier_name: string;
  supplier_tax_id: string;
  status: "training" | "trusted";
  samples_count: number;
  clean_streak: number;
  last_invoice_id: string;
  updated_at: string;
}

export interface UntrainedSupplier {
  supplier_key: string;
  supplier_name: string;
  supplier_tax_id: string;
  invoice_count: number;
}

export interface SupplierFormatsPayload {
  trusted_after_clean: number;
  formats: SupplierFormat[];
  untrained: UntrainedSupplier[];
}

/** Training-mode registry for the active workspace: every supplier format
 *  with its training/trusted state, plus suppliers detected in invoices
 *  that have no training record yet. */
export function useSupplierFormats() {
  const { activeOrganizationId } = useAuth();
  const [data, setData] = useState<SupplierFormatsPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeOrganizationId) return;
    let cancelled = false;
    fetch(`/api/organizations/${activeOrganizationId}/supplier-formats`)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrganizationId]);

  return {
    loading,
    trustedAfter: data?.trusted_after_clean ?? 5,
    formats: data?.formats ?? [],
    untrained: data?.untrained ?? [],
  };
}
