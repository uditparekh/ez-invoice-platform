import { CheckCircle2, FileSearch } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import type { Invoice } from "@/lib/types";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

export function InvoiceDetailPanel({ invoice }: { invoice: Invoice | null }) {
  return (
    <div className="min-w-0 bg-canvas">
      {invoice ? <InvoiceDetail invoice={invoice} /> : <EmptyDetail />}
    </div>
  );
}

function EmptyDetail() {
  return (
    <div className="grid min-h-[520px] place-items-center px-8 text-center">
      <div>
        <FileSearch className="mx-auto text-ink-muted" size={28} />
        <p className="mt-4 text-base font-bold text-ink">Select an invoice</p>
        <p className="mt-2 text-sm text-ink-muted">
          Extracted fields, validation, and line items will appear here.
        </p>
      </div>
    </div>
  );
}

function InvoiceDetail({ invoice }: { invoice: Invoice }) {
  const confidence =
    invoice.confidence == null ? null : Math.round(invoice.confidence * 100);

  return (
    <article className="mx-auto w-full max-w-[1180px] px-4 py-6 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[10px] font-extrabold uppercase text-ink-muted">
            Invoice
          </p>
          <h2 className="mt-3 break-words text-3xl font-bold text-ink">
            {invoice.invoice_number || "Number pending"}
          </h2>
          <p className="mt-3 break-words text-sm font-medium text-ink-secondary">
            {invoice.supplier.name || "Supplier pending"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={invoice.status} />
          {confidence != null && (
            <span className="inline-flex h-7 items-center rounded-full border border-line-strong bg-surface px-2.5 text-[11px] font-bold text-ink-secondary">
              {confidence}% confidence
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-3 py-6 sm:grid-cols-2 xl:grid-cols-4">
        <Fact label="Invoice date" value={formatDate(invoice.invoice_date)} />
        <Fact label="Due date" value={formatDate(invoice.due_date)} />
        <Fact label="Currency" value={invoice.currency || "INR"} />
        <Fact
          label="Total"
          value={formatCurrency(invoice.total, invoice.currency)}
          mono
        />
        <Fact
          label="Purchase order"
          value={invoice.purchase_order || "Not provided"}
        />
        <Fact label="Direction" value={invoice.direction || "Inbound"} />
        <Fact label="Line items" value={String(invoice.lines.length)} />
        <Fact label="Source" value={invoice.source_file} />
      </div>

      {invoice.validation_issues.length > 0 && (
        <div className="mb-6 border-l-2 border-gold bg-gold-soft px-4 py-3">
          <p className="text-xs font-bold text-gold">Review required</p>
          <p className="mt-1 text-sm text-ink-secondary">
            {invoice.validation_issues.join(" · ")}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3 border-y border-line py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-base font-bold text-ink">Line items</h3>
          <p className="mt-1 text-xs text-ink-muted">
            Extracted purchase detail ready for review and mapping.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-accent">
          <CheckCircle2 size={16} />
          {invoice.lines.length} extracted
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-[8px] border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead className="bg-surface-subtle">
              <tr className="text-[10px] font-extrabold uppercase text-ink-muted">
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3 text-right">Quantity</th>
                <th className="px-4 py-3">UOM</th>
                <th className="px-4 py-3 text-right">Unit price</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3">Category</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.length ? (
                invoice.lines.map((line) => (
                  <tr
                    key={line.id ?? line.line_number}
                    className="border-t border-line text-sm text-ink"
                  >
                    <td className="max-w-[360px] px-4 py-4 font-semibold">
                      {line.description || "Description pending"}
                    </td>
                    <td className="px-4 py-4 text-right font-mono">
                      {line.quantity.toLocaleString("en-IN")}
                    </td>
                    <td className="px-4 py-4 text-ink-secondary">
                      {line.uom || "—"}
                    </td>
                    <td className="px-4 py-4 text-right font-mono">
                      {formatCurrency(line.unit_price, invoice.currency)}
                    </td>
                    <td className="px-4 py-4 text-right font-mono font-bold">
                      {formatCurrency(
                        line.net_amount || line.total_amount,
                        invoice.currency,
                      )}
                    </td>
                    <td className="px-4 py-4 text-ink-secondary">
                      {line.category || "Unmapped"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-sm text-ink-muted"
                  >
                    No line items were extracted.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

function Fact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-h-24 rounded-[8px] border border-line bg-surface px-4 py-3.5">
      <p className="text-[10px] font-extrabold uppercase text-ink-muted">
        {label}
      </p>
      <p
        className={cn(
          "mt-3 break-words text-sm font-bold text-ink",
          mono && "font-mono",
        )}
      >
        {value}
      </p>
    </div>
  );
}
