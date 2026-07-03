import type { Invoice } from "@/lib/types";

declare global {
  interface Window {
    __SIFTENTRY_PREVIEW_INVOICES__?: Invoice[];
  }
}

let serverPreviewInvoices: Invoice[] = [];

function memoryPreviewInvoices() {
  if (typeof window === "undefined") return serverPreviewInvoices;
  window.__SIFTENTRY_PREVIEW_INVOICES__ ??= [];
  return window.__SIFTENTRY_PREVIEW_INVOICES__;
}

function setMemoryPreviewInvoices(invoices: Invoice[]) {
  if (typeof window === "undefined") {
    serverPreviewInvoices = invoices;
    return;
  }
  window.__SIFTENTRY_PREVIEW_INVOICES__ = invoices;
}

export function readPreviewInvoices() {
  return memoryPreviewInvoices();
}

export function mergePreviewInvoices(invoices: Invoice[]) {
  const previewInvoices = readPreviewInvoices();
  if (!previewInvoices.length) return invoices;
  const seen = new Set(previewInvoices.map((invoice) => invoice.id));
  return [
    ...previewInvoices,
    ...invoices.filter((invoice) => !seen.has(invoice.id)),
  ];
}

export function prependPreviewInvoices(invoices: Invoice[]) {
  if (!invoices.length) return;
  const existing = readPreviewInvoices();
  const seen = new Set(invoices.map((invoice) => invoice.id));
  const nextInvoices = [
    ...invoices,
    ...existing.filter((invoice) => !seen.has(invoice.id)),
  ];
  setMemoryPreviewInvoices(nextInvoices);
}

export function clearPreviewInvoices() {
  setMemoryPreviewInvoices([]);
}
