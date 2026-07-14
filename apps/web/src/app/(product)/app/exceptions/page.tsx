"use client";

import { CircleAlert, ShieldCheck } from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { exceptionInvoices } from "@/lib/invoice-metrics";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function ExceptionsPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const exceptions = exceptionInvoices(invoices);
  const ready = invoices.length - exceptions.length;

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Exceptions"
        section="Review queue"
        description="Resolve missing fields, unmatched suppliers, totals, tax issues, and accounting mapping blockers."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading exceptions" />
        ) : (
          <>
            {error && (
              <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}
            <section className="grid gap-4 md:grid-cols-3">
              <MetricCard
                label="Exception queue"
                value={exceptions.length}
                detail="Invoices requiring action"
                tone={exceptions.length ? "warning" : "default"}
                icon={<CircleAlert size={18} />}
              />
              <MetricCard
                label="Clean invoices"
                value={ready}
                detail="No current blockers"
                tone="success"
                icon={<ShieldCheck size={18} />}
              />
              <MetricCard
                label="Review rate"
                value={invoices.length ? `${Math.round((exceptions.length / invoices.length) * 100)}%` : "0%"}
                detail="Current workspace"
              />
            </section>

            <ContentCard
              title="Exception worklist"
              subtitle="A future AI layer can explain each blocker and suggest the correction."
            >
              {exceptions.length ? (
                <>
                <div className="md:hidden">
                  {exceptions.map((invoice) => (
                    <article
                      key={`card-${invoice.id}`}
                      className="border-b border-line px-4 py-4 last:border-b-0"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-black text-ink">
                            {invoice.invoice_number || "Pending"}
                          </p>
                          <p className="truncate text-xs font-bold text-ink-muted">
                            {invoice.supplier.name || "Supplier pending"} ·{" "}
                            {formatDate(invoice.invoice_date)}
                          </p>
                        </div>
                        <StatusBadge status={invoice.status} />
                      </div>
                      <p className="mt-2 text-sm leading-5 text-ink-secondary">
                        {invoice.validation_issues[0] ||
                          "Review extraction and accounting mapping."}
                      </p>
                      <p className="mt-2 font-mono text-sm font-black text-ink">
                        {formatCurrency(invoice.total, invoice.currency)}
                      </p>
                    </article>
                  ))}
                </div>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="text-xs font-extrabold uppercase text-ink-muted">
                      <tr className="border-b border-line">
                        <th className="px-3 py-3">Invoice</th>
                        <th className="px-3 py-3">Supplier</th>
                        <th className="px-3 py-3">Issue</th>
                        <th className="px-3 py-3 text-right">Amount</th>
                        <th className="px-3 py-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {exceptions.map((invoice) => (
                        <tr key={invoice.id} className="border-b border-line last:border-b-0">
                          <td className="px-3 py-4 font-black text-ink">
                            {invoice.invoice_number || "Pending"}
                            <span className="block text-xs font-bold text-ink-muted">
                              {formatDate(invoice.invoice_date)}
                            </span>
                          </td>
                          <td className="px-3 py-4 font-semibold text-ink-secondary">
                            {invoice.supplier.name || "Supplier pending"}
                          </td>
                          <td className="px-3 py-4 text-ink-secondary">
                            {invoice.validation_issues[0] || "Review extraction and accounting mapping."}
                          </td>
                          <td className="px-3 py-4 text-right font-mono font-black text-ink">
                            {formatCurrency(invoice.total, invoice.currency)}
                          </td>
                          <td className="px-3 py-4">
                            <StatusBadge status={invoice.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                </>
              ) : (
                <EmptyState
                  icon={ShieldCheck}
                  title="No exceptions"
                  description="The current invoice queue has no open extraction, validation, or posting blockers."
                />
              )}
            </ContentCard>
          </>
        )}
      </main>
    </div>
  );
}
