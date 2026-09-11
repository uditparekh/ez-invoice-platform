"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, FileDown, BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { LoadingState } from "@/components/dashboard/loading-state";
import { EmptyState } from "@/components/dashboard/empty-state";
import {
  ReportControls,
  ReportError,
  ReportMetric,
} from "@/components/dashboard/report-controls";
import { Button } from "@/components/ui/button";
import { useWorkspaceReport } from "@/hooks/use-workspace-report";
import {
  currentMonth,
  downloadCsv,
  rangeQuery,
  reportMoney,
  type WorkspaceAnalytics,
} from "@/lib/reporting";

export default function InsightsPage() {
  const [range, setRange] = useState(currentMonth);
  const report = useWorkspaceReport<WorkspaceAnalytics>(
    "analytics",
    rangeQuery(range),
  );
  const data = report.data;
  function exportReport() {
    if (!data) return;
    downloadCsv(`siftentry-insights-${data.start}-${data.end}.csv`, [
      [
        "period_start_utc",
        "period_end_utc",
        "currency",
        "invoices_received",
        "invoice_value",
        "tax_recorded",
        "received_cohort_currently_posted_value",
      ],
      ...data.currencies.map((row) => [
        data.start,
        data.end,
        row.currency,
        row.count,
        row.total,
        row.tax,
        row.posted_total,
      ]),
    ]);
  }
  return (
    <div className="bg-canvas">
      <PageHeader
        title="Insights"
        description="A clear view of your invoice operations."
        action={
          <Button onClick={exportReport} disabled={!data}>
            <FileDown size={16} />
            Export CSV
          </Button>
        }
      />
      <main className="report-main">
        <ReportControls
          range={range}
          onChange={setRange}
          onRefresh={report.reload}
          loading={report.loading}
        />
        {report.loading && <LoadingState label="Loading workspace insights" />}
        {report.error && (
          <ReportError message={report.error} retry={report.reload} />
        )}
        {data && (
          <>
            <section className="report-metrics" aria-label="Key metrics">
              <ReportMetric
                label="Invoices received"
                value={data.received_count}
                detail="In selected period"
              />
              <ReportMetric
                label="Suppliers"
                value={data.supplier_count}
                detail="In received invoices"
              />
              <ReportMetric
                label="Successful postings"
                value={data.posting_outcomes.succeeded ?? 0}
                detail="Live attempts completed in period"
              />
              <ReportMetric
                label="Needs review now"
                value={
                  (data.queue.needs_review ?? 0) + (data.queue.extracted ?? 0)
                }
                detail="Current queue · all dates"
              />
            </section>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
              <section className="report-panel">
                <div className="report-panel-heading">
                  <h2>Invoice volume</h2>
                  <span className="text-xs text-ink-secondary">
                    Received · UTC
                  </span>
                </div>
                {data.received_count ? (
                  <VolumeChart data={data} />
                ) : (
                  <EmptyState
                    icon={BarChart3}
                    title="No invoices received in this period"
                    description="Choose an earlier date range to see previous activity. Your current queue is shown separately."
                  />
                )}
              </section>
              <section className="report-panel">
                <div className="report-panel-heading">
                  <h2>Current queue</h2>
                </div>
                <dl className="divide-y divide-line">
                  {[
                    [
                      "Needs review",
                      (data.queue.needs_review ?? 0) +
                        (data.queue.extracted ?? 0),
                    ],
                    ["Awaiting approval", data.queue.validated ?? 0],
                    ["Approved", data.queue.approved ?? 0],
                    ["Posting", data.queue.posting ?? 0],
                    ["Failed", data.queue.failed ?? 0],
                  ].map(([label, count]) => (
                    <div
                      key={label}
                      className="flex items-center justify-between gap-4 py-3 text-sm"
                    >
                      <dt className="text-ink-secondary">{label}</dt>
                      <dd className="font-semibold tabular-nums">{count}</dd>
                    </div>
                  ))}
                </dl>
                <Link
                  className="mt-4 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-accent-ink"
                  href="/app/invoices"
                >
                  Open invoices
                  <ArrowRight size={16} />
                </Link>
              </section>
            </div>
            <section className="report-panel">
              <div className="report-panel-heading">
                <div>
                  <h2>Invoice value by currency</h2>
                  <p className="mt-1 text-sm text-ink-secondary">
                    Invoices received in this period. No currency conversion.
                  </p>
                </div>
              </div>
              {data.currencies.length ? (
                <>
                  <div
                    className="divide-y divide-line md:hidden"
                    data-mobile-report="currencies"
                  >
                    {data.currencies.map((row) => (
                      <div
                        key={row.currency}
                        className="py-4 first:pt-0 last:pb-0"
                      >
                        <div className="mb-3 flex justify-between gap-3 text-sm">
                          <h3 className="font-semibold">{row.currency}</h3>
                          <span className="text-ink-secondary">
                            {row.count} invoice{row.count === 1 ? "" : "s"}
                          </span>
                        </div>
                        <dl className="space-y-3 text-sm">
                          {[
                            ["Invoice value", row.total],
                            ["Tax recorded", row.tax],
                            ["Currently posted value", row.posted_total],
                          ].map(([label, value]) => (
                            <div key={label}>
                              <dt className="text-xs text-ink-secondary">
                                {label}
                              </dt>
                              <dd className="mt-1 break-words font-medium tabular-nums">
                                {reportMoney(value, row.currency)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    ))}
                  </div>
                  <div
                    className="report-table-scroll hidden md:block"
                    tabIndex={0}
                    role="region"
                    aria-label="Invoice value by currency"
                    data-scroll-region="true"
                  >
                    <table className="report-table">
                      <thead>
                        <tr>
                          <th>Currency</th>
                          <th className="text-right">Invoices</th>
                          <th className="text-right">Invoice value</th>
                          <th className="text-right">Tax recorded</th>
                          <th className="text-right">Currently posted value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.currencies.map((row) => (
                          <tr key={row.currency}>
                            <th scope="row">{row.currency}</th>
                            <td className="text-right tabular-nums">
                              {row.count}
                            </td>
                            <td className="text-right tabular-nums">
                              {reportMoney(row.total, row.currency)}
                            </td>
                            <td className="text-right tabular-nums">
                              {reportMoney(row.tax, row.currency)}
                            </td>
                            <td className="text-right tabular-nums">
                              {reportMoney(row.posted_total, row.currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <p className="py-6 text-sm text-ink-secondary">
                  No invoice values in this period.
                </p>
              )}
              <p className="mt-4 text-xs leading-5 text-ink-secondary">
                Tax recorded is the tax shown on invoices, not a determination
                of deductible credit. Currently posted value uses the present
                status of invoices received in the selected period; it is not a
                cash-flow or payment total.
              </p>
            </section>
            <section className="report-panel">
              <div className="report-panel-heading">
                <h2>Suppliers in this period</h2>
                <span className="text-xs text-ink-secondary">
                  Grouped by currency
                </span>
              </div>
              {data.suppliers.length ? (
                <SupplierTable data={data} />
              ) : (
                <p className="py-4 text-sm text-ink-secondary">
                  Suppliers appear when invoices are received.
                </p>
              )}
            </section>
            <details className="report-panel text-sm">
              <summary className="cursor-pointer font-medium">
                How these numbers are calculated
              </summary>
              <div className="mt-3 space-y-2 leading-6 text-ink-secondary">
                <p>
                  Received invoices are selected by their recorded creation
                  timestamp, from the start date at 00:00 through the end date
                  at 23:59:59 UTC. All matching workspace invoices are
                  included—not just the first page.
                </p>
                <p>
                  Successful postings counts live posting attempts completed in
                  this period, including invoices received earlier. Dry runs are
                  excluded. Failed live attempts in this period:{" "}
                  {data.posting_outcomes.failed ?? 0}.
                </p>
                <p>
                  Queue counts reflect current invoice status across all dates.
                  Values remain in their original currencies. No exchange rates,
                  estimated savings, or inferred touchless-processing claims are
                  applied.
                </p>
                <p>
                  Updated {new Date(data.generated_at).toLocaleString()}.
                  Refresh to retrieve newer data.
                </p>
              </div>
            </details>
          </>
        )}
      </main>
    </div>
  );
}

function SupplierTable({ data }: { data: WorkspaceAnalytics }) {
  const [page, setPage] = useState(0);
  const pages = Math.ceil(data.suppliers.length / 10);
  const current = Math.min(page, pages - 1);
  const rows = data.suppliers.slice(current * 10, (current + 1) * 10);
  return (
    <>
      <dl
        className="divide-y divide-line md:hidden"
        data-mobile-report="suppliers"
      >
        {rows.map((row) => (
          <div
            key={`${row.supplier}-${row.currency}`}
            className="py-4 first:pt-0 last:pb-0"
          >
            <dt className="break-words text-sm font-medium">{row.supplier}</dt>
            <dd className="mt-1 text-xs text-ink-secondary">
              {row.count} invoice{row.count === 1 ? "" : "s"} · {row.currency}
            </dd>
            <dd className="mt-2 break-words text-sm font-semibold tabular-nums">
              {reportMoney(row.total, row.currency)}
            </dd>
          </div>
        ))}
      </dl>
      <div
        className="report-table-scroll hidden md:block"
        tabIndex={0}
        role="region"
        aria-label="Suppliers"
        data-scroll-region="true"
      >
        <table className="report-table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Currency</th>
              <th className="text-right">Invoices</th>
              <th className="text-right">Invoice value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.supplier}-${row.currency}`}>
                <th scope="row" className="max-w-80 whitespace-normal!">
                  {row.supplier}
                </th>
                <td>{row.currency}</td>
                <td className="text-right tabular-nums">{row.count}</td>
                <td className="text-right tabular-nums">
                  {reportMoney(row.total, row.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-3 text-sm">
          <Button
            size="sm"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            Previous
          </Button>
          <span>
            {current + 1} / {pages}
          </span>
          <Button
            size="sm"
            disabled={current + 1 >= pages}
            onClick={() => setPage(current + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </>
  );
}

function VolumeChart({ data }: { data: WorkspaceAnalytics }) {
  // Aggregate long ranges into a maximum of 20 equal calendar buckets, including
  // zero-volume days, so chart geometry never implies a discontinuous time axis.
  const start = Date.parse(`${data.start}T00:00:00Z`);
  const days =
    Math.round((Date.parse(`${data.end}T00:00:00Z`) - start) / 86400000) + 1;
  const size = Math.max(1, Math.ceil(days / 20));
  const buckets = Array.from({ length: Math.ceil(days / size) }, (_, i) => ({
    date: new Date(start + i * size * 86400000).toISOString().slice(0, 10),
    count: 0,
  }));
  for (const day of data.daily) {
    const index = Math.floor(
      (Date.parse(`${day.date}T00:00:00Z`) - start) / (86400000 * size),
    );
    if (buckets[index]) buckets[index].count += day.count;
  }
  const max = Math.max(1, ...buckets.map((bucket) => bucket.count));
  return (
    <>
      <div
        className="flex h-56 items-end gap-1 border-b border-line pt-6 sm:gap-2"
        role="img"
        aria-label={`${data.received_count} invoices received between ${data.start} and ${data.end}. Daily data is available below.`}
      >
        {buckets.map((bucket) => (
          <div
            key={bucket.date}
            className="group relative flex h-full min-w-0 flex-1 items-end"
            title={`${bucket.date}${size > 1 ? ` · ${size}-day bucket` : ""}: ${bucket.count} invoices`}
          >
            <div
              className="w-full rounded-t-sm bg-accent/85 transition-colors group-hover:bg-accent"
              style={{
                height: `${(bucket.count / max) * 100}%`,
                minHeight: bucket.count ? 3 : 0,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-3 flex justify-between text-xs text-ink-secondary">
        <span>{data.start}</span>
        <span>
          {size > 1 ? `Up to ${size} days per bar` : "Daily invoices"}
        </span>
        <span>{data.end}</span>
      </div>
      <details className="mt-4 text-sm text-ink-secondary">
        <summary className="cursor-pointer">View daily counts</summary>
        <div className="mt-2 max-h-44 overflow-y-auto">
          <table className="report-table">
            <thead>
              <tr>
                <th>Date (UTC)</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {data.daily.map((day) => (
                <tr key={day.date}>
                  <td>{day.date}</td>
                  <td>{day.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs">
          Unlisted days have zero received invoices.
        </p>
      </details>
    </>
  );
}
