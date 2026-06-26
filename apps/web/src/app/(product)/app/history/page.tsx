"use client";

import { FileClock, ShieldCheck, TimerReset, UploadCloud } from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import {
  exceptionInvoices,
  invoiceTotal,
  readyInvoices,
} from "@/lib/invoice-metrics";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function HistoryPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const ready = readyInvoices(invoices);
  const exceptions = exceptionInvoices(invoices);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="History"
        section="Audit trail"
        description="Review extraction, validation, approval, posting, and correction activity across the workspace."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading audit trail" />
        ) : (
          <>
            {error && (
              <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Invoices"
                value={invoices.length}
                detail={`${ready.length} ready for ERP`}
                icon={<UploadCloud size={18} />}
              />
              <MetricCard
                label="Ready for ERP"
                value={ready.length}
                detail={`${invoices.filter((invoice) => invoice.status === "posted").length} already posted`}
                tone="success"
                icon={<ShieldCheck size={18} />}
              />
              <MetricCard
                label="Total spend"
                value={formatCurrency(invoiceTotal(invoices), invoices[0]?.currency || "USD")}
                detail={`${new Set(invoices.map((invoice) => invoice.supplier.name)).size} vendors`}
                tone="accent"
                icon={<FileClock size={18} />}
              />
              <MetricCard
                label="Exceptions"
                value={exceptions.length}
                detail={exceptions.length ? "Needs review" : "Clear"}
                tone={exceptions.length ? "warning" : "default"}
                icon={<TimerReset size={18} />}
              />
            </section>

            <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
              <ContentCard
                title="Close-ready pipeline"
                subtitle="A compact view of how uploaded invoices move toward ERP posting."
              >
                <div className="space-y-5">
                  <PipelineRow
                    number="1"
                    title="Extracted"
                    detail="PDF captured and invoice fields normalized"
                    count={invoices.filter((invoice) => invoice.status !== "uploaded").length}
                  />
                  <PipelineRow
                    number="2"
                    title="Validated"
                    detail="Totals, supplier, and line items checked"
                    count={ready.length}
                  />
                  <PipelineRow
                    number="3"
                    title="Mapped"
                    detail="Client ledger and category rules applied"
                    count={invoices.filter((invoice) => invoice.lines.some((line) => line.category)).length}
                  />
                  <PipelineRow
                    number="4"
                    title="Posted / exported"
                    detail="Evidence ready for audit and close"
                    count={invoices.filter((invoice) => invoice.status === "posted").length}
                  />
                </div>
              </ContentCard>

              <ContentCard title="Recent activity" subtitle="Newest invoices first.">
                {invoices.length ? (
                  <div className="space-y-4">
                    {invoices.slice(0, 6).map((invoice) => (
                      <div
                        key={invoice.id}
                        className="flex flex-col gap-3 border-b border-line pb-4 last:border-b-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-black text-ink">
                            {invoice.invoice_number || "Number pending"}
                          </p>
                          <p className="mt-1 truncate text-sm text-ink-secondary">
                            {invoice.supplier.name || "Supplier pending"} ·{" "}
                            {formatDate(invoice.invoice_date)}
                          </p>
                        </div>
                        <StatusBadge status={invoice.status} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={FileClock}
                    title="No history yet"
                    description="Upload and process invoices to build the audit trail."
                  />
                )}
              </ContentCard>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function PipelineRow({
  number,
  title,
  detail,
  count,
}: {
  number: string;
  title: string;
  detail: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-line pb-4 last:border-b-0 last:pb-0">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-black text-accent-ink dark:text-cyan">
        {number}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-black text-ink">{title}</p>
        <p className="mt-1 text-sm leading-5 text-ink-secondary">{detail}</p>
      </div>
      <span className="font-mono text-sm font-black text-ink">{count}</span>
    </div>
  );
}
