import type { Invoice } from "@/lib/types";

export function invoiceTotal(invoices: Invoice[]) {
  return invoices.reduce((sum, invoice) => sum + (invoice.total || 0), 0);
}

export function postedTotal(invoices: Invoice[]) {
  return invoices
    .filter((invoice) => invoice.status === "posted")
    .reduce((sum, invoice) => sum + (invoice.total || 0), 0);
}

export function readyInvoices(invoices: Invoice[]) {
  return invoices.filter((invoice) =>
    ["validated", "approved"].includes(invoice.status),
  );
}

export function exceptionInvoices(invoices: Invoice[]) {
  return invoices.filter(
    (invoice) =>
      invoice.status === "needs_review" ||
      invoice.status === "failed" ||
      invoice.validation_issues.length > 0,
  );
}

export function groupCurrency(invoices: Invoice[]) {
  return groupByValue(invoices, (invoice) => invoice.currency || "USD");
}

export function groupSupplier(invoices: Invoice[]) {
  return groupByValue(
    invoices,
    (invoice) => invoice.supplier.name || "Unknown supplier",
  );
}

export function groupCategory(invoices: Invoice[]) {
  const totals = new Map<string, number>();
  for (const invoice of invoices) {
    for (const line of invoice.lines) {
      const key = line.category || "Unmapped";
      totals.set(key, (totals.get(key) ?? 0) + (line.total_amount || line.net_amount || 0));
    }
  }
  return [...totals.entries()]
    .map(([label, total]) => ({ label, total }))
    .sort((left, right) => right.total - left.total);
}

export function groupLineItems(invoices: Invoice[]) {
  const totals = new Map<string, number>();
  for (const invoice of invoices) {
    for (const line of invoice.lines) {
      const key = line.description || "Unmapped line item";
      totals.set(key, (totals.get(key) ?? 0) + (line.total_amount || line.net_amount || 0));
    }
  }
  return [...totals.entries()]
    .map(([label, total]) => ({ label, total }))
    .sort((left, right) => right.total - left.total);
}

function groupByValue(invoices: Invoice[], getLabel: (invoice: Invoice) => string) {
  const totals = new Map<string, { total: number; count: number }>();
  for (const invoice of invoices) {
    const label = getLabel(invoice);
    const current = totals.get(label) ?? { total: 0, count: 0 };
    totals.set(label, {
      count: current.count + 1,
      total: current.total + (invoice.total || 0),
    });
  }
  return [...totals.entries()]
    .map(([label, value]) => ({ label, ...value }))
    .sort((left, right) => right.total - left.total);
}
