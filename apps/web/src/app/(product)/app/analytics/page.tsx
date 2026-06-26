"use client";

import { BarChart3, CircleDollarSign, Clock3, FileCheck2 } from "lucide-react";

import { BarList } from "@/components/dashboard/bar-list";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import {
  exceptionInvoices,
  groupCategory,
  groupCurrency,
  groupLineItems,
  groupSupplier,
  invoiceTotal,
  postedTotal,
} from "@/lib/invoice-metrics";
import { formatCurrency } from "@/lib/utils";

export default function AnalyticsPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const total = invoiceTotal(invoices);
  const posted = postedTotal(invoices);
  const exceptions = exceptionInvoices(invoices);
  const supplierRows = groupSupplier(invoices);
  const categoryRows = groupCategory(invoices);
  const currencyRows = groupCurrency(invoices);
  const lineRows = groupLineItems(invoices);
  const currency = invoices[0]?.currency || "USD";
  const firstCategory = categoryRows[0];
  const categoryPercent = firstCategory && total
    ? Math.round((firstCategory.total / total) * 100)
    : 0;

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Analytics"
        section="Spend overview"
        description="Monitor processing throughput, supplier spend, category concentration, and posting progress."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading analytics" />
        ) : (
          <>
            {error && (
              <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Total spend"
                value={formatCurrency(total, currency)}
                detail={`${invoices.length} invoice${invoices.length === 1 ? "" : "s"} · ${currencyRows.length} currenc${currencyRows.length === 1 ? "y" : "ies"}`}
                tone="accent"
                icon={<CircleDollarSign size={18} />}
              />
              <MetricCard
                label="Sent to ERP"
                value={`${invoices.filter((invoice) => invoice.status === "posted").length} / ${invoices.length}`}
                detail={`${formatCurrency(posted, currency)} posted`}
                tone="success"
                icon={<FileCheck2 size={18} />}
              />
              <MetricCard
                label="Avg processing"
                value={invoices.length ? "0.3s" : "0s"}
                detail="Extraction pipeline"
                icon={<Clock3 size={18} />}
              />
              <MetricCard
                label="Exceptions"
                value={exceptions.length}
                detail={exceptions.length ? "Needs review" : "Clear"}
                tone={exceptions.length ? "warning" : "default"}
                icon={<BarChart3 size={18} />}
              />
            </section>

            {invoices.length ? (
              <>
                <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                  <ContentCard title="Spend by supplier" subtitle="Top supplier concentration in the active workspace.">
                    <BarList
                      rows={supplierRows}
                      currency={currency}
                      emptyLabel="No supplier spend yet."
                    />
                  </ContentCard>
                  <ContentCard title="Spend by category" subtitle="Distribution from extracted line categories.">
                    <div className="grid gap-5 md:grid-cols-[220px_minmax(0,1fr)] md:items-center">
                      <div
                        className="mx-auto grid size-48 place-items-center rounded-full"
                        style={{
                          background: `conic-gradient(var(--accent) ${categoryPercent}%, var(--surface-strong) 0)`,
                        }}
                      >
                        <div className="grid size-24 place-items-center rounded-full bg-surface text-center">
                          <span className="text-2xl font-black text-ink">
                            {categoryPercent}%
                          </span>
                        </div>
                      </div>
                      <BarList
                        rows={categoryRows}
                        currency={currency}
                        emptyLabel="No categories mapped yet."
                      />
                    </div>
                  </ContentCard>
                </section>

                <section className="grid gap-6 xl:grid-cols-3">
                  <ContentCard title="By currency">
                    <BarList
                      rows={currencyRows}
                      currency={currency}
                      emptyLabel="No currency data yet."
                    />
                  </ContentCard>
                  <ContentCard title="Top vendors">
                    <BarList
                      rows={supplierRows}
                      currency={currency}
                      emptyLabel="No vendor data yet."
                    />
                  </ContentCard>
                  <ContentCard title="Top line items">
                    <BarList
                      rows={lineRows}
                      currency={currency}
                      emptyLabel="No line item data yet."
                    />
                  </ContentCard>
                </section>
              </>
            ) : (
              <EmptyState
                icon={BarChart3}
                title="No analytics yet"
                description="Upload invoices to populate spend, supplier, and category dashboards."
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
