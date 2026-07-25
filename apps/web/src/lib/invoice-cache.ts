import type { Invoice } from "@/lib/types";

// Stale-while-revalidate cache for workspace invoices, shared by every
// consumer of useWorkspaceInvoices. Navigations render the last known data
// instantly while a background refresh replaces it.
export const invoiceCache = new Map<string, Invoice[]>();

export function clearWorkspaceInvoiceCache() {
  invoiceCache.clear();
}
