import { FileSearch, LoaderCircle } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import type { Invoice } from "@/lib/types";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

export function InvoiceList({
  invoices,
  selectedId,
  loading,
  onSelect,
  toolbar,
}: {
  invoices: Invoice[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (invoiceId: string) => void;
  toolbar?: React.ReactNode;
}) {
  return (
    <div className="border-b border-line bg-surface lg:border-b-0 lg:border-r lg:border-line">
      {toolbar}
      <div className="flex h-14 items-center justify-between border-b border-line px-4 sm:px-6">
        <span className="text-sm font-extrabold text-ink-secondary">
          {invoices.length} invoice{invoices.length === 1 ? "" : "s"}
        </span>
        <span className="text-xs font-bold text-ink-muted">
          Newest first
        </span>
      </div>
      <div className="max-h-[540px] overflow-y-auto lg:max-h-[calc(100vh-304px)]">
        {loading ? (
          <EmptyQueue loading />
        ) : invoices.length ? (
          invoices.map((invoice) => (
            <button
              key={invoice.id}
              onClick={() => onSelect(invoice.id)}
              className={cn(
                "grid w-full grid-cols-[minmax(0,1fr)_minmax(118px,auto)] gap-x-4 border-b border-line px-4 py-5 text-left transition-colors sm:px-6",
                selectedId === invoice.id
                  ? "border-l-[4px] border-l-accent bg-accent-soft"
                  : "border-l-[4px] border-l-transparent bg-surface hover:bg-surface-subtle",
              )}
            >
              <span className="truncate text-base font-black text-ink">
                {invoice.invoice_number || "Number pending"}
              </span>
              <span className="truncate text-right font-mono text-sm font-black text-ink">
                {formatCurrency(invoice.total, invoice.currency)}
              </span>
              <span className="mt-2 line-clamp-2 text-sm font-semibold leading-5 text-ink-secondary">
                {invoice.supplier.name || "Supplier pending"}
              </span>
              <span className="mt-3 row-span-2 justify-self-end">
                <StatusBadge status={invoice.status} />
              </span>
              <span className="mt-3 text-xs font-bold text-ink-muted">
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
    <div className="grid min-h-80 place-items-center border-b border-line px-6 text-center">
      <div>
        {loading ? (
          <LoaderCircle className="mx-auto animate-spin text-accent" size={24} />
        ) : (
          <FileSearch className="mx-auto text-ink-muted" size={26} />
        )}
        <p className="mt-4 text-base font-black text-ink">
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
