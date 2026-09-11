"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, FileText, Upload } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { LoadingState } from "@/components/dashboard/loading-state";
import {
  ReportError,
  ReportMetric,
} from "@/components/dashboard/report-controls";
import { StatusBadge } from "@/components/status-badge";
import { useAuth } from "@/components/auth-provider";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { useWorkspaceReport } from "@/hooks/use-workspace-report";
import {
  currentMonth,
  rangeQuery,
  reportMoney,
  type WorkspaceAnalytics,
} from "@/lib/reporting";

export default function HomePage() {
  const { user, activeOrganizationId } = useAuth();
  const [range] = useState(currentMonth);
  const report = useWorkspaceReport<WorkspaceAnalytics>(
    "analytics",
    rangeQuery(range),
  );
  const {
    invoices,
    error: invoiceError,
    loading: invoicesLoading,
  } = useWorkspaceInvoices({ limit: 5 });
  const role = user?.memberships.find(
    (item) => item.organization_id === activeOrganizationId,
  )?.role;
  const readOnly = role === "viewer";
  const data = report.data;
  const needsReview =
    (data?.queue.needs_review ?? 0) + (data?.queue.extracted ?? 0);
  const actions = [
    {
      label: "Review invoices",
      count: needsReview,
      detail: "Check extracted fields and resolve flagged items.",
      href: "/app/invoices?status=needs_review",
    },
    {
      label: "Awaiting approval",
      count: data?.queue.validated ?? 0,
      detail: "Validated invoices waiting for an approver.",
      href: "/app/invoices?status=validated",
    },
    {
      label: "Failed postings",
      count: data?.queue.failed ?? 0,
      detail: "Review the result before trying again.",
      href: "/app/history",
    },
  ];
  return (
    <div className="bg-canvas">
      <PageHeader
        title="Home"
        description={
          readOnly
            ? "Explore your read-only workspace."
            : "Your invoice operations, at a glance."
        }
        action={
          <Link
            href="/app/invoices"
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover"
          >
            {readOnly ? <FileText size={16} /> : <Upload size={16} />}
            {readOnly ? "Browse invoices" : "Open invoice workspace"}
          </Link>
        }
      />
      <main className="report-main">
        {report.loading && <LoadingState label="Loading workspace overview" />}
        {report.error && (
          <ReportError message={report.error} retry={report.reload} />
        )}
        {data && (
          <>
            <div className="flex flex-wrap justify-between gap-2 text-sm text-ink-secondary">
              <span>
                This month · {data.start} — {data.end} · UTC
              </span>
              <Link
                href="/app/analytics"
                className="inline-flex items-center gap-1 font-medium text-accent-ink"
              >
                View insights
                <ArrowRight size={15} />
              </Link>
            </div>
            <section className="report-metrics">
              <ReportMetric
                label="Invoices received"
                value={data.received_count}
                detail="This month"
              />
              <ReportMetric
                label="Successful postings"
                value={data.posting_outcomes.succeeded ?? 0}
                detail="Live attempts completed this month"
              />
              <ReportMetric
                label="Needs review"
                value={needsReview}
                detail="Current queue · all dates"
              />
              <ReportMetric
                label="Awaiting approval"
                value={data.queue.validated ?? 0}
                detail="Current queue · all dates"
              />
            </section>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
              <section className="report-panel">
                <div className="report-panel-heading">
                  <h2>Needs your attention</h2>
                  <span className="text-xs text-ink-secondary">
                    Current queue
                  </span>
                </div>
                <div className="divide-y divide-line">
                  {actions.map((action) => (
                    <Link
                      key={action.label}
                      href={action.href}
                      className="group flex min-h-24 items-center gap-4 py-4"
                    >
                      <span
                        className={`grid size-11 shrink-0 place-items-center rounded-lg text-lg font-semibold tabular-nums ${action.count ? "bg-accent-soft text-accent-ink" : "bg-surface-subtle text-ink-secondary"}`}
                      >
                        {action.count}
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-medium">{action.label}</h3>
                        <p className="mt-1 text-sm leading-5 text-ink-secondary">
                          {action.detail}
                        </p>
                      </div>
                      <ArrowRight
                        size={16}
                        className="shrink-0 text-ink-muted group-hover:text-accent-ink"
                      />
                    </Link>
                  ))}
                </div>
              </section>
              <section className="report-panel">
                <div className="report-panel-heading">
                  <h2>Received value</h2>
                </div>
                <p className="text-sm leading-6 text-ink-secondary">
                  Invoice values received this month, kept in their original
                  currencies.
                </p>
                <dl className="mt-4 divide-y divide-line">
                  {data.currencies.map((row) => (
                    <div key={row.currency} className="py-4">
                      <dt className="text-xs text-ink-secondary">
                        {row.currency} · {row.count} invoices
                      </dt>
                      <dd className="mt-1 break-words text-xl font-semibold tabular-nums">
                        {reportMoney(row.total, row.currency)}
                      </dd>
                    </div>
                  ))}
                </dl>
                {!data.currencies.length && (
                  <p className="mt-6 text-sm text-ink-secondary">
                    No invoices received this month.
                  </p>
                )}
                <Link
                  href="/app/history"
                  className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-accent-ink"
                >
                  Explore recorded history
                  <ArrowRight size={15} />
                </Link>
              </section>
            </div>
          </>
        )}
        <section className="report-panel">
          <div className="report-panel-heading">
            <h2>Recent invoices</h2>
            <Link
              href="/app/invoices"
              className="text-sm font-medium text-accent-ink"
            >
              View all
            </Link>
          </div>
          {invoiceError ? (
            <p role="alert" className="text-sm text-danger">
              {invoiceError}
            </p>
          ) : invoicesLoading ? (
            <LoadingState label="Loading recent invoices" />
          ) : !invoices.length ? (
            <p className="py-6 text-sm text-ink-secondary">
              Your latest invoices will appear here.
            </p>
          ) : (
            <div className="divide-y divide-line">
              {invoices.map((invoice) => (
                <Link
                  key={invoice.id}
                  href={`/app/invoices/${invoice.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 py-4"
                >
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-sm font-medium">
                      {invoice.supplier.name || "Supplier pending"}
                    </p>
                    <p className="mt-1 text-xs text-ink-secondary">
                      {invoice.invoice_number || "Number pending"}
                    </p>
                  </div>
                  <StatusBadge status={invoice.status} />
                  <p className="w-full text-sm font-medium tabular-nums sm:w-auto sm:min-w-40 sm:text-right">
                    {reportMoney(invoice.total, invoice.currency)}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
