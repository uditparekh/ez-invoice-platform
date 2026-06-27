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
      const amount = safeLineAmount(invoice, line);
      if (!amount) continue;
      const key = line.category || "Unmapped";
      totals.set(key, (totals.get(key) ?? 0) + amount);
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
      const amount = safeLineAmount(invoice, line);
      if (!amount) continue;
      const key = line.description || "Unmapped line item";
      totals.set(key, (totals.get(key) ?? 0) + amount);
    }
  }
  return [...totals.entries()]
    .map(([label, total]) => ({ label, total }))
    .sort((left, right) => right.total - left.total);
}

function safeLineAmount(invoice: Invoice, line: Invoice["lines"][number]) {
  const amount = line.total_amount || line.net_amount || 0;
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  const invoiceTotalValue = Math.abs(invoice.total || 0);
  if (
    invoiceTotalValue &&
    invoice.lines.length > 1 &&
    amount > Math.max(invoiceTotalValue * 1.25, invoiceTotalValue + 10)
  ) {
    return 0;
  }
  return amount;
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
