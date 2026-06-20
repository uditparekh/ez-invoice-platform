import { FileSearch, LoaderCircle } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import type { Invoice } from "@/lib/types";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

export function InvoiceList({
  invoices,
  selectedId,
  loading,
  onSelect,
}: {
  invoices: Invoice[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (invoiceId: string) => void;
}) {
  return (
    <div className="border-b border-line bg-surface lg:border-b-0 lg:border-r">
      <div className="flex h-12 items-center justify-between border-b border-line px-4 sm:px-6">
        <span className="text-xs font-bold text-ink-secondary">
          {invoices.length} invoice{invoices.length === 1 ? "" : "s"}
        </span>
        <span className="text-[11px] font-semibold text-ink-muted">
          Newest first
        </span>
      </div>
      <div className="max-h-[520px] overflow-y-auto lg:max-h-[calc(100vh-260px)]">
        {loading ? (
          <EmptyQueue loading />
        ) : invoices.length ? (
          invoices.map((invoice) => (
            <button
              key={invoice.id}
              onClick={() => onSelect(invoice.id)}
              className={cn(
                "grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-line px-4 py-4 text-left transition-colors sm:px-6",
                selectedId === invoice.id
                  ? "border-l-[3px] border-l-accent bg-accent-soft"
                  : "border-l-[3px] border-l-transparent bg-surface hover:bg-surface-subtle",
              )}
            >
              <span className="truncate text-sm font-bold text-ink">
                {invoice.invoice_number || "Number pending"}
              </span>
              <span className="font-mono text-sm font-bold text-ink">
                {formatCurrency(invoice.total, invoice.currency)}
              </span>
              <span className="mt-1 truncate text-xs text-ink-secondary">
                {invoice.supplier.name || "Supplier pending"}
              </span>
              <span className="mt-2 row-span-2">
                <StatusBadge status={invoice.status} />
              </span>
              <span className="mt-2 text-[11px] font-medium text-ink-muted">
                {formatDate(invoice.invoice_date)}
              </span>
            </button>
          ))
        ) : (
          <EmptyQueue />
        )}
      </div>
    </div>
  );
}

function EmptyQueue({ loading = false }: { loading?: boolean }) {
  return (
    <div className="grid min-h-72 place-items-center px-6 text-center">
      <div>
        {loading ? (
          <LoaderCircle className="mx-auto animate-spin text-accent" size={24} />
        ) : (
          <FileSearch className="mx-auto text-ink-muted" size={26} />
        )}
        <p className="mt-4 text-sm font-bold text-ink">
          {loading ? "Loading invoice queue" : "No invoices found"}
        </p>
        <p className="mt-2 text-xs leading-5 text-ink-muted">
          {loading
            ? "Checking your organization workspace."
            : "Upload a supplier PDF or adjust the current filter."}
        </p>
      </div>
    </div>
  );
}
