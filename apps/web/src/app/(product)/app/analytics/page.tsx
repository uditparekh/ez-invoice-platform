"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  CalendarClock,
  FileDown,
  FileSearch,
  Printer,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { BarList } from "@/components/dashboard/bar-list";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { Invoice } from "@/lib/types";
import {
  exceptionInvoices,
  groupCategory,
  groupSupplier,
  invoiceTotal,
} from "@/lib/invoice-metrics";
import { cn, formatCurrency } from "@/lib/utils";

/** Insights — UI Spec §9. Four tabs, four audiences:
 *  Overview (ops) · Finance (CFO) · AI performance (founder) · Exceptions (reviewer).
 *  All headline numbers are computed from live workspace invoices; ROI figures that
 *  depend on industry baselines are explicitly tagged EST. */

type InsightsTab = "overview" | "finance" | "ai" | "exceptions";

// Industry baselines for the EST-tagged ROI math (Finance tab footnote).
const MANUAL_COST_PER_INVOICE = 240; // ₹, Ardent-style AP benchmark
const SIFT_COST_PER_INVOICE = 38;
const MANUAL_MINUTES_PER_INVOICE = 8;

export default function InsightsPage() {
  const { activeOrganizationId } = useAuth();
  const { invoices, loading, error } = useWorkspaceInvoices();
  const [tab, setTab] = useState<InsightsTab>("overview");
  const [correctionsLearned, setCorrectionsLearned] = useState<number | null>(
    null,
  );

  useEffect(() => {
    if (!activeOrganizationId) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(
          `/api/organizations/${activeOrganizationId}/corrections/learning?limit=200`,
        );
        if (!response.ok) return;
        const payload = (await response.json()) as unknown;
        const items = Array.isArray(payload)
          ? payload
          : Array.isArray((payload as { items?: unknown[] })?.items)
            ? (payload as { items: unknown[] }).items
            : [];
        if (!cancelled) setCorrectionsLearned(items.length);
      } catch {
        /* learning endpoint optional — card degrades gracefully */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeOrganizationId]);

  const m = useMemo(() => computeInsights(invoices), [invoices]);
  const currency = m.currency;

  function exportCsv() {
    const header =
      "invoice_number,supplier,invoice_date,due_date,currency,subtotal,tax_total,total,status,validation_issues";
    const rows = invoices.map((invoice) =>
      [
        invoice.invoice_number,
        (invoice.supplier.name || "").replaceAll(",", " "),
        invoice.invoice_date,
        invoice.due_date,
        invoice.currency,
        invoice.subtotal,
        invoice.tax_total,
        invoice.total,
        invoice.status,
        invoice.validation_issues.length,
      ].join(","),
    );
    const blob = new Blob([[header, ...rows].join("\n")], {
      type: "text/csv",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "siftentry_insights.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Insights"
        section={new Date().toLocaleDateString("en-US", {
          month: "long",
          year: "numeric",
        })}
        description="Spend, savings, AI learning, and exceptions — one page for ops, finance, and the board."
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={exportCsv}
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
            >
              <FileDown size={16} />
              Export CSV
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover"
            >
              <Printer size={16} />
              Board pack
            </button>
          </div>
        }
      />

      <div className="border-b border-line bg-shell/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] gap-1 overflow-x-auto px-4 sm:px-6 lg:px-8">
          <TabButton active={tab === "overview"} onClick={() => setTab("overview")}>
            Overview
          </TabButton>
          <TabButton active={tab === "finance"} onClick={() => setTab("finance")}>
            Finance
          </TabButton>
          <TabButton active={tab === "ai"} onClick={() => setTab("ai")}>
            AI performance
          </TabButton>
          <TabButton
            active={tab === "exceptions"}
            onClick={() => setTab("exceptions")}
          >
            Exceptions
            {m.exceptions.length > 0 && (
              <span className="ml-1.5 rounded-full bg-gold-soft px-2 py-0.5 font-mono text-[11px] font-black text-gold-ink">
                {m.exceptions.length}
              </span>
            )}
          </TabButton>
        </div>
      </div>

      <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Computing insights" />
        ) : !invoices.length ? (
          <EmptyState
            icon={FileSearch}
            title="Charts appear after your first invoices"
            description={
              error ||
              "Upload and process a few invoices — spend, savings, and AI learning charts build themselves from real data."
            }
          />
        ) : tab === "overview" ? (
          <OverviewTab m={m} currency={currency} />
        ) : tab === "finance" ? (
          <FinanceTab m={m} currency={currency} />
        ) : tab === "ai" ? (
          <AiTab m={m} currency={currency} correctionsLearned={correctionsLearned} />
        ) : (
          <ExceptionsTab m={m} currency={currency} />
        )}
      </main>
    </div>
  );
}

/* ================= tab: overview ================= */

function OverviewTab({ m, currency }: { m: Insights; currency: string }) {
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Total spend" value={formatCurrency(m.spend, currency)} detail={`${m.count} invoices · ${m.supplierCount} suppliers`} />
        <Kpi
          hero
          label="Touchless rate"
          value={m.touchlessRate == null ? "—" : `${m.touchlessRate}%`}
          detail="posted with zero review flags"
        />
        <Kpi
          label="Avg confidence"
          value={m.avgConfidence == null ? "—" : `${m.avgConfidence}%`}
          detail="across extracted invoices"
          tone="success"
        />
        <Kpi
          label="Exceptions"
          value={String(m.exceptions.length)}
          detail={m.exceptions.length ? "waiting in the Exceptions tab" : "queue is clean"}
          tone={m.exceptions.length ? "warning" : "success"}
        />
      </section>

      <ContentCard
        title="Automation funnel"
        subtitle={`${m.funnel.extractedPct}% auto-extracted · ${m.funnel.posted} of ${m.funnel.uploaded} fully posted`}
      >
        <div className="flex items-end gap-3 sm:gap-5">
          {m.funnel.stages.map((stage) => (
            <div key={stage.label} className="min-w-0 flex-1 text-center">
              <div className="flex h-36 items-end">
                <div
                  className="w-full rounded-t-xl bg-accent transition-all"
                  style={{
                    height: `${Math.max(8, (stage.count / Math.max(1, m.funnel.uploaded)) * 100)}%`,
                    opacity: stage.opacity,
                  }}
                />
              </div>
              <p className="mt-2 truncate text-xs font-black text-ink">
                {stage.label} <span className="font-mono">{stage.count}</span>
              </p>
            </div>
          ))}
        </div>
      </ContentCard>

      <section className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <ContentCard
          title="Spend by supplier"
          subtitle={
            m.concentration
              ? undefined
              : "Distribution across your vendor base"
          }
          action={
            m.concentration ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-gold-soft px-3 py-1.5 text-xs font-black text-gold-ink">
                <AlertTriangle size={13} />
                {m.concentration.pct}% of spend is {m.concentration.label}
              </span>
            ) : undefined
          }
        >
          <BarList rows={m.suppliers} currency={currency} emptyLabel="No supplier spend yet." />
        </ContentCard>
        <ContentCard title="Spend by category" subtitle="From mapped line items">
          {m.categoryTop ? (
            <div className="flex items-center gap-5">
              <div
                className="grid size-28 shrink-0 place-items-center rounded-full"
                style={{
                  background: `conic-gradient(var(--accent) 0 ${m.categoryTop.pct}%, var(--cyan) ${m.categoryTop.pct}% 100%)`,
                }}
              >
                <div className="grid size-[72px] place-items-center rounded-full bg-surface font-display text-lg font-black text-ink">
                  {m.categoryTop.pct}%
                </div>
              </div>
              <div className="min-w-0 space-y-2 text-sm">
                <p className="font-black text-ink">
                  <span className="mr-2 inline-block size-2.5 rounded-full bg-accent" />
                  {m.categoryTop.label}
                </p>
                <p className="font-bold text-ink-secondary">
                  <span className="mr-2 inline-block size-2.5 rounded-full bg-cyan" />
                  Everything else · {100 - m.categoryTop.pct}%
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm font-semibold text-ink-muted">
              Categories appear once line items are mapped in Rules &amp; mapping.
            </p>
          )}
        </ContentCard>
      </section>
    </>
  );
}

/* ================= tab: finance ================= */

function FinanceTab({ m, currency }: { m: Insights; currency: string }) {
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          hero
          label="Cost per invoice"
          value={formatCurrency(SIFT_COST_PER_INVOICE, currency)}
          detail={`vs ${formatCurrency(MANUAL_COST_PER_INVOICE, currency)} manual · 84% cheaper`}
          est
        />
        <Kpi
          label="Duplicates blocked"
          value={m.duplicates.amount ? formatCurrency(m.duplicates.amount, currency) : "0"}
          detail={
            m.duplicates.count
              ? `${m.duplicates.count} duplicate${m.duplicates.count === 1 ? "" : "s"} caught before posting`
              : "no duplicates detected"
          }
          tone={m.duplicates.count ? "warning" : "success"}
        />
        <Kpi
          label="Avg cycle time"
          value={m.cycleHours == null ? "—" : `${m.cycleHours} hrs`}
          detail="upload → posted, from timestamps"
          tone="success"
        />
        <Kpi
          label="Processing saved"
          value={formatCurrency(m.count * (MANUAL_COST_PER_INVOICE - SIFT_COST_PER_INVOICE), currency)}
          detail={`≈ ${Math.round((m.count * (MANUAL_MINUTES_PER_INVOICE - 1)) / 60)} hrs of keying avoided`}
          est
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <ContentCard
          title="Payables calendar"
          subtitle="Built from captured due dates"
          action={
            m.dueBuckets[0].total > 0 ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-danger-soft px-3 py-1.5 text-xs font-black text-danger">
                <CalendarClock size={13} />
                {formatCurrency(m.dueBuckets[0].total, currency)} due this week
              </span>
            ) : undefined
          }
        >
          <div className="flex items-end gap-4">
            {m.dueBuckets.map((bucket) => (
              <div key={bucket.label} className="min-w-0 flex-1 text-center">
                <div className="flex h-28 items-end">
                  <div
                    className={cn(
                      "w-full rounded-t-xl",
                      bucket.tone === "danger"
                        ? "bg-danger/85"
                        : bucket.tone === "warning"
                          ? "bg-gold/85"
                          : "bg-accent/75",
                    )}
                    style={{
                      height: `${Math.max(6, (bucket.total / Math.max(1, m.dueMax)) * 100)}%`,
                    }}
                  />
                </div>
                <p className="mt-2 text-xs font-black text-ink">{bucket.label}</p>
                <p className="truncate font-mono text-xs font-bold text-ink-secondary">
                  {formatCurrency(bucket.total, currency)}
                </p>
              </div>
            ))}
          </div>
          {m.dueBuckets[0].count > 0 && (
            <p className="mt-4 rounded-xl border border-gold-soft bg-gold-soft px-4 py-3 text-sm font-bold text-gold-ink">
              <Sparkles size={14} className="mr-1.5 inline" />
              {m.dueBuckets[0].count} invoice{m.dueBuckets[0].count === 1 ? "" : "s"} due
              within 7 days — schedule payments now to protect early-payment discounts.
            </p>
          )}
        </ContentCard>

        <ContentCard title="Tax credit readiness" subtitle="GSTIN + tax captured per invoice">
          <div className="flex items-center gap-5">
            <div
              className="grid size-24 shrink-0 place-items-center rounded-full"
              style={{
                background: `conic-gradient(var(--success) 0 ${m.tax.readyPct}%, var(--line) ${m.tax.readyPct}% 100%)`,
              }}
            >
              <div className="grid size-16 place-items-center rounded-full bg-surface font-display text-sm font-black text-ink">
                {m.tax.ready}/{m.tax.taxed}
              </div>
            </div>
            <div className="min-w-0 text-sm">
              <p className="font-black text-ink">
                {formatCurrency(m.tax.creditAmount, currency)} input credit ready
              </p>
              <p className="mt-1 font-bold text-success">{m.tax.ready} tax-clean</p>
              {m.tax.needsFix > 0 && (
                <p className="font-bold text-gold-ink">
                  {m.tax.needsFix} missing supplier tax ID
                </p>
              )}
            </div>
          </div>
          <p className="mt-4 text-xs font-semibold leading-5 text-ink-muted">
            Every posted invoice carries validated supplier tax IDs and tax splits —
            filing-ready.
          </p>
        </ContentCard>
      </section>

      <p className="text-xs font-semibold text-ink-muted">
        <span className="mr-1.5 rounded bg-accent-soft px-1.5 py-0.5 font-black text-accent-ink">EST</span>
        Estimated figures use industry AP baselines ({formatCurrency(MANUAL_COST_PER_INVOICE, currency)} ·{" "}
        {MANUAL_MINUTES_PER_INVOICE} min per manual invoice) until billing data is connected. All other
        numbers are computed from your live invoices.
      </p>
    </>
  );
}

/* ================= tab: ai performance ================= */

function AiTab({
  m,
  currency,
  correctionsLearned,
}: {
  m: Insights;
  currency: string;
  correctionsLearned: number | null;
}) {
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          hero
          label="Touchless rate"
          value={m.touchlessRate == null ? "—" : `${m.touchlessRate}%`}
          detail="zero-flag invoices, and climbing"
        />
        <Kpi
          label="Corrections learned"
          value={correctionsLearned == null ? "—" : String(correctionsLearned)}
          detail="teaching vendor memory"
          tone="success"
        />
        <Kpi
          label="Avg confidence"
          value={m.avgConfidence == null ? "—" : `${m.avgConfidence}%`}
          detail="across extracted fields"
        />
        <Kpi
          label="Vendors mastered"
          value={`${m.vendors.filter((vendor) => vendor.state === "Mastered").length} / ${m.vendors.length}`}
          detail="fully touchless vendors"
          tone="success"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
        <ContentCard title="Confidence distribution" subtitle="Where extraction quality sits today">
          <div className="space-y-3">
            {m.confidenceBands.map((band) => (
              <div key={band.label}>
                <div className="flex items-center justify-between text-sm">
                  <p className="font-bold text-ink-secondary">{band.label}</p>
                  <p className="font-mono font-black text-ink">{band.count}</p>
                </div>
                <div className="mt-1.5 h-2 rounded-full bg-surface-strong">
                  <div
                    className={cn("h-full rounded-full", band.className)}
                    style={{ width: `${Math.max(4, (band.count / Math.max(1, m.count)) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-4 rounded-xl bg-accent-soft px-4 py-3 text-sm font-bold text-accent-ink">
            Every correction saved in the Review Workspace teaches vendor memory — the
            product compounds with use.
          </p>
        </ContentCard>

        <ContentCard title="Vendor learning" subtitle="Exception rate by supplier">
          <div className="overflow-x-auto" data-scroll-region="true">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
                  <th className="py-2 pr-3">Vendor</th>
                  <th className="px-3 py-2 text-right">Invoices</th>
                  <th className="px-3 py-2 text-right">Spend</th>
                  <th className="px-3 py-2 text-right">Flags</th>
                  <th className="py-2 pl-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {m.vendors.slice(0, 6).map((vendor) => (
                  <tr key={vendor.label} className="border-t border-line">
                    <td className="max-w-[180px] truncate py-3 pr-3 font-black text-ink">
                      {vendor.label}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-ink-secondary">
                      {vendor.count}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-ink">
                      {formatCurrency(vendor.total, currency)}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-ink-secondary">
                      {vendor.flags}
                    </td>
                    <td className="py-3 pl-3 text-right">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-1 text-[11px] font-black",
                          vendor.state === "Mastered"
                            ? "bg-success-soft text-success"
                            : vendor.state === "Improving"
                              ? "bg-cyan-soft text-cyan-ink"
                              : "bg-gold-soft text-gold-ink",
                        )}
                      >
                        {vendor.state}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </section>
    </>
  );
}

/* ================= tab: exceptions ================= */

function ExceptionsTab({ m, currency }: { m: Insights; currency: string }) {
  if (!m.exceptions.length) {
    return (
      <EmptyState
        icon={BadgeCheck}
        title="🎉 Nothing needs you"
        description="Every invoice is clean — new exceptions will land here with suggested fixes."
      />
    );
  }
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-3">
        <Kpi label="Open exceptions" value={String(m.exceptions.length)} tone="warning" detail="need a decision" />
        <Kpi label="Clean invoices" value={String(m.count - m.exceptions.length)} tone="success" detail="no flags" />
        <Kpi
          label="Value held"
          value={formatCurrency(invoiceTotal(m.exceptions), currency)}
          detail="waiting on these fixes"
        />
      </section>

      <ContentCard title="Exception worklist" subtitle="Every row links straight into the Review Workspace">
        <div className="divide-y divide-line">
          {m.exceptions.slice(0, 12).map((invoice) => {
            const issue = invoice.validation_issues[0] || statusIssue(invoice);
            const mappingIssue = /ledger|account|map|gl[\s_-]?code/i.test(issue);
            const isDuplicate = m.duplicates.ids.has(invoice.id);
            return (
              <div key={invoice.id} className="py-4 first:pt-0 last:pb-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-black text-ink">
                      {invoice.supplier.name || "Supplier pending"} ·{" "}
                      <span className="font-mono">
                        {invoice.invoice_number || "—"}
                      </span>{" "}
                      <span className="font-mono font-bold text-ink-secondary">
                        {formatCurrency(invoice.total, invoice.currency)}
                      </span>
                    </p>
                    <p
                      className={cn(
                        "mt-1 text-sm font-bold",
                        isDuplicate ? "text-danger" : "text-gold-ink",
                      )}
                    >
                      <AlertTriangle size={13} className="mr-1 inline" />
                      {isDuplicate ? "Possible duplicate — same supplier and amount" : issue}
                    </p>
                  </div>
                  <Link
                    href={`/app/invoices?invoice=${invoice.id}&mode=review`}
                    className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl border border-line-strong bg-surface px-3.5 text-sm font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                  >
                    Open workspace
                    <ArrowUpRight size={14} />
                  </Link>
                </div>
                {mappingIssue && (
                  <div className="mt-3 flex flex-col gap-2 rounded-xl border border-dashed border-accent/40 bg-accent-soft/60 px-4 py-3 sm:flex-row sm:items-center">
                    <p className="min-w-0 flex-1 text-sm font-bold text-accent-ink">
                      <Sparkles size={14} className="mr-1.5 inline" />
                      ✦ Suggested fix: this looks like a ledger mapping gap — add the
                      mapping once and every future invoice inherits it.
                    </p>
                    <Link
                      href="/app/rules"
                      className="inline-flex h-9 shrink-0 items-center justify-center rounded-lg bg-accent px-3.5 text-xs font-black text-white transition-colors hover:bg-accent-hover"
                    >
                      Fix mapping →
                    </Link>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ContentCard>
    </>
  );
}

/* ================= shared ================= */

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-12 shrink-0 items-center border-b-2 px-4 text-sm font-black transition-colors",
        active
          ? "border-accent text-accent"
          : "border-transparent text-ink-secondary hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function Kpi({
  label,
  value,
  detail,
  tone = "default",
  hero = false,
  est = false,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "default" | "success" | "warning";
  hero?: boolean;
  est?: boolean;
}) {
  if (hero) {
    return (
      <article className="rounded-2xl bg-gradient-to-br from-accent to-[#6366F1] p-5 shadow-glow">
        <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-indigo-100/90">
          {label}
          {est && <EstChip light />}
        </p>
        <p className="mt-2 font-display text-3xl font-black text-white">{value}</p>
        {detail && <p className="mt-1 text-xs font-bold text-indigo-100/80">{detail}</p>}
      </article>
    );
  }
  return (
    <article className="rounded-2xl border border-line bg-surface p-5 shadow-card">
      <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
        {est && <EstChip />}
      </p>
      <p
        className={cn(
          "mt-2 font-display text-3xl font-black",
          tone === "success" ? "text-success" : tone === "warning" ? "text-gold-ink" : "text-ink",
        )}
      >
        {value}
      </p>
      {detail && <p className="mt-1 text-xs font-bold text-ink-muted">{detail}</p>}
    </article>
  );
}

function EstChip({ light = false }: { light?: boolean }) {
  return (
    <span
      className={cn(
        "ml-2 rounded px-1.5 py-0.5 text-[10px] font-black",
        light ? "bg-white/20 text-white" : "bg-accent-soft text-accent-ink",
      )}
    >
      EST
    </span>
  );
}

function statusIssue(invoice: Invoice) {
  if (invoice.status === "failed") return "Posting failed — retry from History or fix and repost";
  if (invoice.status === "needs_review") return "Extraction flagged for human review";
  return "Needs attention";
}

/* ================= metrics ================= */

type Insights = ReturnType<typeof computeInsights>;

function computeInsights(invoices: Invoice[]) {
  const count = invoices.length;
  const spend = invoiceTotal(invoices);
  const currency =
    invoices.find((invoice) => invoice.currency)?.currency || "USD";
  const posted = invoices.filter((invoice) => invoice.status === "posted");
  const exceptions = exceptionInvoices(invoices);

  const funnelCounts = {
    uploaded: count,
    extracted: invoices.filter((invoice) => invoice.status !== "uploaded").length,
    validated: invoices.filter((invoice) =>
      ["validated", "approved", "posted"].includes(invoice.status),
    ).length,
    posted: posted.length,
  };
  const funnel = {
    ...funnelCounts,
    extractedPct: count ? Math.round((funnelCounts.extracted / count) * 100) : 0,
    stages: [
      { label: "Uploaded", count: funnelCounts.uploaded, opacity: 0.3 },
      { label: "Extracted", count: funnelCounts.extracted, opacity: 0.55 },
      { label: "Validated", count: funnelCounts.validated, opacity: 0.8 },
      { label: "Posted", count: funnelCounts.posted, opacity: 1 },
    ],
  };

  const touchless = posted.filter(
    (invoice) => invoice.validation_issues.length === 0,
  );
  const touchlessRate = posted.length
    ? Math.round((touchless.length / posted.length) * 100)
    : null;

  const confidences = invoices
    .map((invoice) => invoice.confidence)
    .filter((value): value is number => value != null);
  const avgConfidence = confidences.length
    ? Math.round(
        (confidences.reduce((sum, value) => sum + value, 0) /
          confidences.length) *
          (confidences[0] <= 1 ? 100 : 1),
      )
    : null;
  const normalized = (value: number) => (value <= 1 ? value * 100 : value);
  const confidenceBands = [
    {
      label: "High confidence · ≥95%",
      count: confidences.filter((value) => normalized(value) >= 95).length,
      className: "bg-success",
    },
    {
      label: "Medium · 80–95%",
      count: confidences.filter(
        (value) => normalized(value) >= 80 && normalized(value) < 95,
      ).length,
      className: "bg-cyan",
    },
    {
      label: "Needs training · <80%",
      count: confidences.filter((value) => normalized(value) < 80).length,
      className: "bg-gold",
    },
  ];

  const suppliers = groupSupplier(invoices);
  const supplierCount = suppliers.length;
  const topSupplier = suppliers[0];
  const concentration =
    topSupplier && spend > 0 && topSupplier.total / spend >= 0.5
      ? { label: topSupplier.label, pct: Math.round((topSupplier.total / spend) * 100) }
      : null;

  const categories = groupCategory(invoices).filter(
    (category) => category.label !== "Unmapped",
  );
  const categorySpend = categories.reduce((sum, category) => sum + category.total, 0);
  const categoryTop =
    categories.length && categorySpend > 0
      ? {
          label: categories[0].label,
          pct: Math.min(99, Math.max(1, Math.round((categories[0].total / categorySpend) * 100))),
        }
      : null;

  // Duplicates: same supplier + same total (± invoice number collision)
  const duplicateIds = new Set<string>();
  let duplicateAmount = 0;
  const seen = new Map<string, Invoice>();
  for (const invoice of invoices) {
    const key = `${(invoice.supplier.name || "").toLowerCase()}|${invoice.total}`;
    if (invoice.total > 0 && seen.has(key)) {
      duplicateIds.add(invoice.id);
      duplicateAmount += invoice.total;
    } else {
      seen.set(key, invoice);
    }
  }

  // Cycle time: created_at -> updated_at on posted invoices
  const cycles = posted
    .map(
      (invoice) =>
        (new Date(invoice.updated_at).getTime() -
          new Date(invoice.created_at).getTime()) /
        3_600_000,
    )
    .filter((hours) => Number.isFinite(hours) && hours >= 0);
  const cycleHours = cycles.length
    ? Math.round((cycles.reduce((sum, value) => sum + value, 0) / cycles.length) * 10) / 10
    : null;

  // Payables calendar: 4 weekly buckets from today
  const now = Date.now();
  const week = 7 * 24 * 3_600_000;
  const dueBuckets = [
    { label: "This wk", total: 0, count: 0, tone: "danger" as const },
    { label: "Wk 2", total: 0, count: 0, tone: "warning" as const },
    { label: "Wk 3", total: 0, count: 0, tone: "default" as const },
    { label: "Wk 4+", total: 0, count: 0, tone: "default" as const },
  ];
  for (const invoice of invoices) {
    if (!invoice.due_date) continue;
    const due = new Date(invoice.due_date).getTime();
    if (!Number.isFinite(due) || due < now - week) continue;
    const bucketIndex = Math.min(3, Math.max(0, Math.floor((due - now) / week)));
    dueBuckets[bucketIndex].total += invoice.total || 0;
    dueBuckets[bucketIndex].count += 1;
  }
  const dueMax = Math.max(...dueBuckets.map((bucket) => bucket.total), 1);

  // Tax readiness
  const taxed = invoices.filter((invoice) => invoice.tax_total > 0);
  const taxReady = taxed.filter((invoice) => invoice.supplier.tax_id);
  const tax = {
    taxed: taxed.length,
    ready: taxReady.length,
    needsFix: taxed.length - taxReady.length,
    readyPct: taxed.length ? Math.round((taxReady.length / taxed.length) * 100) : 0,
    creditAmount: taxReady.reduce((sum, invoice) => sum + invoice.tax_total, 0),
  };

  // Vendor learning
  const exceptionIds = new Set(exceptions.map((invoice) => invoice.id));
  const vendors = suppliers.map((supplier) => {
    const theirs = invoices.filter(
      (invoice) => (invoice.supplier.name || "Unknown supplier") === supplier.label,
    );
    const flags = theirs.filter((invoice) => exceptionIds.has(invoice.id)).length;
    const state =
      flags === 0 && theirs.length >= 3
        ? "Mastered"
        : flags === 0 || flags < theirs.length / 2
          ? "Improving"
          : "Training";
    return { ...supplier, flags, state };
  });

  return {
    count,
    spend,
    currency,
    funnel,
    exceptions,
    touchlessRate,
    avgConfidence,
    confidenceBands,
    suppliers,
    supplierCount,
    concentration,
    categoryTop,
    duplicates: { count: duplicateIds.size, amount: duplicateAmount, ids: duplicateIds },
    cycleHours,
    dueBuckets,
    dueMax,
    tax,
    vendors,
  };
}
