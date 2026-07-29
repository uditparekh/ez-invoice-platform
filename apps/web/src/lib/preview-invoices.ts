import type { Invoice } from "@/lib/types";

declare global {
  interface Window {
    __SIFTENTRY_PREVIEW_INVOICES__?: Record<string, Invoice[]>;
  }
}

let serverPreviewInvoices: Record<string, Invoice[]> = {};

function memoryPreviewInvoices() {
  if (typeof window === "undefined") return serverPreviewInvoices;
  if (
    !window.__SIFTENTRY_PREVIEW_INVOICES__ ||
    Array.isArray(window.__SIFTENTRY_PREVIEW_INVOICES__)
  ) {
    window.__SIFTENTRY_PREVIEW_INVOICES__ = {};
  }
  return window.__SIFTENTRY_PREVIEW_INVOICES__;
}

function setMemoryPreviewInvoices(
  organizationId: string,
  invoices: Invoice[],
) {
  if (typeof window === "undefined") {
    serverPreviewInvoices = {
      ...serverPreviewInvoices,
      [organizationId]: invoices,
    };
    return;
  }
  window.__SIFTENTRY_PREVIEW_INVOICES__ = {
    ...memoryPreviewInvoices(),
    [organizationId]: invoices,
  };
}

export function readPreviewInvoices(organizationId: string) {
  return memoryPreviewInvoices()[organizationId] ?? [];
}

export function mergePreviewInvoices(
  organizationId: string,
  invoices: Invoice[],
) {
  const previewInvoices = readPreviewInvoices(organizationId);
  if (!previewInvoices.length) return invoices;
  const seen = new Set(previewInvoices.map((invoice) => invoice.id));
  return [
    ...previewInvoices,
    ...invoices.filter((invoice) => !seen.has(invoice.id)),
  ];
}

export function prependPreviewInvoices(
  organizationId: string,
  invoices: Invoice[],
) {
  if (!invoices.length) return;
  const existing = readPreviewInvoices(organizationId);
  const seen = new Set(invoices.map((invoice) => invoice.id));
  const nextInvoices = [
    ...invoices,
    ...existing.filter((invoice) => !seen.has(invoice.id)),
  ];
  setMemoryPreviewInvoices(organizationId, nextInvoices);
}

export function clearPreviewInvoices(organizationId?: string) {
  if (!organizationId) {
    serverPreviewInvoices = {};
    if (typeof window !== "undefined") {
      window.__SIFTENTRY_PREVIEW_INVOICES__ = {};
    }
    return;
  }
  setMemoryPreviewInvoices(organizationId, []);
}
