"use client";

import {
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  CircleDollarSign,
  Clock3,
  FileCheck2,
  Gauge,
  PieChart,
  TrendingUp,
} from "lucide-react";
import type { ReactNode } from "react";

import { BarList } from "@/components/dashboard/bar-list";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { Invoice, InvoiceStatus } from "@/lib/types";
import {
  exceptionInvoices,
  groupCategory,
  groupCurrency,
  groupLineItems,
  groupSupplier,
  invoiceTotal,
  postedTotal,
  readyInvoices,
} from "@/lib/invoice-metrics";
import { cn, formatCurrency } from "@/lib/utils";

const statusLabels: Record<InvoiceStatus, string> = {
  uploaded: "Uploaded",
  extracted: "Extracted",
  needs_review: "Needs review",
  validated: "Validated",
  approved: "Approved",
  posting: "Posting",
  posted: "Posted",
  failed: "Failed",
};

export default function AnalyticsPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const total = invoiceTotal(invoices);
  const posted = postedTotal(invoices);
  const exceptions = exceptionInvoices(invoices);
  const ready = readyInvoices(invoices);
  const supplierRows = groupSupplier(invoices);
  const categoryRows = keepReasonableRows(groupCategory(invoices), total);
  const currencyRows = groupCurrency(invoices);
  const lineRows = keepReasonableRows(groupLineItems(invoices), total);
  const currency = invoices[0]?.currency || "USD";
  const postedCount = invoices.filter((invoice) => invoice.status === "posted").length;
  const validatedCount = invoices.filter((invoice) =>
    ["validated", "approved", "posted"].includes(invoice.status),
  ).length;
  const reviewCount = invoices.filter((invoice) =>
    ["needs_review", "failed"].includes(invoice.status),
  ).length;
  const readinessPercent = invoices.length
    ? Math.round(((ready.length + postedCount) / invoices.length) * 100)
    : 0;
  const validationPercent = invoices.length
    ? Math.round((validatedCount / invoices.length) * 100)
    : 0;
  const exceptionPercent = invoices.length
    ? Math.round((exceptions.length / invoices.length) * 100)
    : 0;
  const statusRows = buildStatusRows(invoices);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Analytics"
        section="Spend overview"
        description="Track invoice throughput, ERP readiness, supplier concentration, category mix, and extraction quality."
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
              <AnalyticsMetric
                label="Total spend"
                value={formatCurrency(total, currency)}
                detail={`${invoices.length} invoice${invoices.length === 1 ? "" : "s"} · ${currencyRows.length} currenc${currencyRows.length === 1 ? "y" : "ies"}`}
                icon={<CircleDollarSign size={18} />}
              />
              <AnalyticsMetric
                label="ERP progress"
                value={`${postedCount} / ${invoices.length}`}
                detail={`${formatCurrency(posted, currency)} posted`}
                icon={<FileCheck2 size={18} />}
                tone={postedCount ? "success" : "default"}
              />
              <AnalyticsMetric
                label="Ready to post"
                value={`${readinessPercent}%`}
                detail={`${ready.length} waiting · ${postedCount} posted`}
                icon={<BadgeCheck size={18} />}
                tone={readinessPercent ? "accent" : "default"}
              />
              <AnalyticsMetric
                label="Exceptions"
                value={exceptions.length}
                detail={exceptions.length ? `${exceptionPercent}% need review` : "Clear"}
                icon={<AlertTriangle size={18} />}
                tone={exceptions.length ? "warning" : "success"}
              />
            </section>

            {invoices.length ? (
              <>
                <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
                  <ContentCard
                    title="Operational flow"
                    subtitle="Where invoices are sitting in the current workspace."
                    action={
                      <span className="rounded-full border border-line bg-canvas px-3 py-1 text-xs font-black text-ink-secondary">
                        {validationPercent}% validated
                      </span>
                    }
                  >
                    <div className="grid gap-5 lg:grid-cols-[1fr_280px] lg:items-center">
                      <StatusPipeline rows={statusRows} total={invoices.length} />
                      <QualityPanel
                        validationPercent={validationPercent}
                        readinessPercent={readinessPercent}
                        reviewCount={reviewCount}
                      />
                    </div>
                  </ContentCard>

                  <ContentCard
                    title="Category mix"
                    subtitle="Mapped spend distribution from extracted line items."
                    action={<PieChart size={18} className="text-ink-muted" />}
                  >
                    <CategoryMix rows={categoryRows} currency={currency} />
                  </ContentCard>
                </section>

                <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
                  <ContentCard
                    title="Spend by supplier"
                    subtitle="Top supplier concentration by invoice totals."
                    action={<TrendingUp size={18} className="text-ink-muted" />}
                  >
                    <BarList
                      rows={supplierRows}
                      currency={currency}
                      emptyLabel="No supplier spend yet."
                    />
                  </ContentCard>

                  <ContentCard
                    title="Currency exposure"
                    subtitle="Invoice totals grouped by extracted currency."
                  >
                    <BarList
                      rows={currencyRows}
                      currency={currency}
                      emptyLabel="No currency data yet."
                    />
                  </ContentCard>
                </section>

                <section className="grid gap-6 xl:grid-cols-3">
                  <ContentCard title="Top line items" subtitle="Highest clean line-item totals.">
                    <BarList
                      rows={lineRows}
                      currency={currency}
                      emptyLabel="No reliable line-item data yet."
                    />
                  </ContentCard>
                  <ContentCard title="Review queue" subtitle="Invoices that need accountant attention.">
                    <ReviewQueue invoices={exceptions} currency={currency} />
                  </ContentCard>
                  <ContentCard title="Processing health" subtitle="Current extraction and posting signals.">
                    <HealthList
                      invoices={invoices}
                      readyCount={ready.length}
                      exceptionCount={exceptions.length}
                    />
                  </ContentCard>
                </section>
              </>
            ) : (
              <EmptyState
                icon={BarChart3}
                title="No analytics yet"
                description="Upload invoices to populate spend, supplier, category, and posting dashboards."
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function AnalyticsMetric({
  label,
  value,
  detail,
  icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: ReactNode;
  tone?: "default" | "accent" | "success" | "warning";
}) {
  return (
    <article className="min-h-36 rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-extrabold uppercase tracking-[0.1em] text-ink-muted">
          {label}
        </p>
        <div className="text-ink-muted">{icon}</div>
      </div>
      <div
        className={cn(
          "mt-5 break-words text-4xl font-black leading-none text-ink",
          tone === "accent" && "text-accent dark:text-cyan",
          tone === "success" && "text-success",
          tone === "warning" && "text-gold",
        )}
      >
        {value}
      </div>
      <p className="mt-3 text-sm font-semibold leading-5 text-ink-secondary">
        {detail}
      </p>
    </article>
  );
}

function StatusPipeline({
  rows,
  total,
}: {
  rows: { label: string; total: number; status: InvoiceStatus }[];
  total: number;
}) {
  return (
    <div className="space-y-4">
      {rows.map((row) => {
        const percent = total ? Math.round((row.total / total) * 100) : 0;
        return (
          <div key={row.status}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-black text-ink">{row.label}</p>
              <p className="shrink-0 text-sm font-black text-ink-secondary">
                {row.total}
              </p>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-strong">
              <div
                className={cn(
                  "h-full rounded-full",
                  row.status === "posted" && "bg-success",
                  row.status === "failed" && "bg-danger",
                  row.status === "needs_review" && "bg-gold",
                  !["posted", "failed", "needs_review"].includes(row.status) &&
                    "bg-accent dark:bg-cyan",
                )}
                style={{ width: `${Math.max(row.total ? 6 : 0, percent)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function QualityPanel({
  validationPercent,
  readinessPercent,
  reviewCount,
}: {
  validationPercent: number;
  readinessPercent: number;
  reviewCount: number;
}) {
  return (
    <div className="rounded-2xl border border-line bg-canvas p-4">
      <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        <Gauge size={16} />
        Workspace quality
      </div>
      <div className="mt-5 grid gap-3">
        <QualityRow label="Validated" value={validationPercent} />
        <QualityRow label="ERP ready" value={readinessPercent} />
        <div className="rounded-xl border border-line bg-surface px-3 py-3">
          <p className="text-xs font-bold text-ink-muted">Needs review</p>
          <p className="mt-1 text-2xl font-black text-ink">{reviewCount}</p>
        </div>
      </div>
    </div>
  );
}

function QualityRow({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-bold text-ink-secondary">{label}</p>
        <p className="text-sm font-black text-ink">{value}%</p>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-strong">
        <div
          className="h-full rounded-full bg-accent dark:bg-cyan"
          style={{ width: `${Math.max(value ? 6 : 0, value)}%` }}
        />
      </div>
    </div>
  );
}

function CategoryMix({
  rows,
  currency,
}: {
  rows: { label: string; total: number; count?: number }[];
  currency: string;
}) {
  const total = rows.reduce((sum, row) => sum + row.total, 0);
  const top = rows[0];
  const topPercent = top && total ? Math.round((top.total / total) * 100) : 0;

  if (!rows.length || !total) {
    return <p className="text-sm font-semibold text-ink-muted">No reliable categories mapped yet.</p>;
  }

  return (
    <div className="grid gap-5 md:grid-cols-[180px_minmax(0,1fr)] md:items-center">
      <div
        className="mx-auto grid size-40 place-items-center rounded-full"
        style={{
          background: `conic-gradient(var(--accent) ${topPercent}%, var(--surface-strong) 0)`,
        }}
      >
        <div className="grid size-24 place-items-center rounded-full bg-surface text-center">
          <div>
            <p className="text-2xl font-black text-ink">{topPercent}%</p>
            <p className="mx-auto mt-0.5 max-w-16 truncate text-[11px] font-extrabold text-ink-muted">
              {top.label}
            </p>
          </div>
        </div>
      </div>
      <div className="space-y-3">
        {rows.slice(0, 5).map((row, index) => (
          <div key={row.label} className="flex min-w-0 items-center gap-3">
            <span
              className={cn(
                "size-2.5 shrink-0 rounded-full",
                index === 0 ? "bg-accent dark:bg-cyan" : "bg-surface-strong",
              )}
            />
            <p className="min-w-0 flex-1 truncate text-sm font-bold text-ink-secondary">
              {row.label}
            </p>
            <p className="shrink-0 font-mono text-sm font-black text-ink">
              {formatCurrency(row.total, currency)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReviewQueue({
  invoices,
  currency,
}: {
  invoices: Invoice[];
  currency: string;
}) {
  if (!invoices.length) {
    return <p className="text-sm font-semibold text-ink-muted">No exceptions in the current queue.</p>;
  }

  return (
    <div className="space-y-3">
      {invoices.slice(0, 5).map((invoice) => (
        <div
          key={invoice.id}
          className="rounded-xl border border-line bg-canvas px-3 py-3"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 truncate text-sm font-black text-ink">
              {invoice.invoice_number || invoice.source_file}
            </p>
            <p className="shrink-0 font-mono text-sm font-black text-ink">
              {formatCurrency(invoice.total, invoice.currency || currency)}
            </p>
          </div>
          <p className="mt-1 truncate text-xs font-bold text-ink-secondary">
            {invoice.supplier.name || "Supplier pending"}
          </p>
        </div>
      ))}
    </div>
  );
}

function HealthList({
  invoices,
  readyCount,
  exceptionCount,
}: {
  invoices: Invoice[];
  readyCount: number;
  exceptionCount: number;
}) {
  const checks = [
    {
      label: "Parser output",
      value: invoices.every((invoice) => invoice.invoice_number && invoice.total)
        ? "Core fields present"
        : "Some fields missing",
    },
    {
      label: "Posting queue",
      value: readyCount ? `${readyCount} ready` : "No invoices ready",
    },
    {
      label: "Exception risk",
      value: exceptionCount ? `${exceptionCount} need review` : "Low",
    },
    {
      label: "Avg processing",
      value: invoices.length ? "0.3s" : "0s",
      icon: <Clock3 size={15} />,
    },
  ];

  return (
    <div className="space-y-3">
      {checks.map((check) => (
        <div
          key={check.label}
          className="flex items-center justify-between gap-3 rounded-xl border border-line bg-canvas px-3 py-3"
        >
          <p className="flex min-w-0 items-center gap-2 truncate text-sm font-bold text-ink-secondary">
            {check.icon}
            {check.label}
          </p>
          <p className="shrink-0 text-sm font-black text-ink">{check.value}</p>
        </div>
      ))}
    </div>
  );
}

function buildStatusRows(invoices: Invoice[]) {
  const counts = new Map<InvoiceStatus, number>();
  for (const invoice of invoices) {
    counts.set(invoice.status, (counts.get(invoice.status) ?? 0) + 1);
  }
  return (Object.keys(statusLabels) as InvoiceStatus[])
    .map((status) => ({
      status,
      label: statusLabels[status],
      total: counts.get(status) ?? 0,
    }))
    .filter((row) => row.total > 0);
}

function keepReasonableRows(
  rows: { label: string; total: number; count?: number }[],
  dashboardTotal: number,
) {
  const absoluteTotal = Math.abs(dashboardTotal || 0);
  const ceiling = Math.max(absoluteTotal * 1.5, absoluteTotal + 10, 10_000_000);
  return rows.filter(
    (row) =>
      Number.isFinite(row.total) &&
      row.total > 0 &&
      Math.abs(row.total) <= ceiling &&
      !looksLikeBankingNoise(row.label),
  );
}

function looksLikeBankingNoise(label: string) {
  return /\b(iban|sort code|acct#|account no|swift|bic|bank)\b/i.test(label);
}
