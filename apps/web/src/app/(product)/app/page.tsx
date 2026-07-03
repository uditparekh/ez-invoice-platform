"use client";

import {
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  X,
  FileText,
  PlugZap,
  Settings2,
  Sparkles,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ContentCard } from "@/components/dashboard/content-card";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import {
  exceptionInvoices,
  invoiceTotal,
  postedTotal,
  readyInvoices,
} from "@/lib/invoice-metrics";
import { cn, formatCurrency } from "@/lib/utils";

export default function HomePage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const currency = invoices[0]?.currency || "USD";
  const ready = readyInvoices(invoices);
  const exceptions = exceptionInvoices(invoices);
  const posted = invoices.filter((invoice) => invoice.status === "posted");
  const awaitingApproval = invoices.filter(
    (invoice) => invoice.status === "validated",
  );

  // ROI hero (spec §5): real extraction rate + processed value, EST time saved
  const extractedPct = invoices.length
    ? Math.round(
        (invoices.filter((invoice) => invoice.status !== "uploaded").length /
          invoices.length) *
          1000,
      ) / 10
    : 0;
  const timeSavedHrs = Math.round((invoices.length * 7) / 60);

  // Proactive nudge (spec §5): a vendor whose invoices repeat the same flag
  const [dismissedNudge, setDismissedNudge] = useState(() =>
    typeof window === "undefined"
      ? true
      : window.localStorage.getItem("siftentry.home.nudgeDismissed") === "true",
  );
  const nudge = useMemo(() => {
    const byPattern = new Map<string, { vendor: string; count: number }>();
    for (const invoice of invoices) {
      const issue = invoice.validation_issues[0];
      if (!issue) continue;
      const vendor = invoice.supplier.name || "Unknown supplier";
      const key = `${vendor}|${issue}`;
      const entry = byPattern.get(key) ?? { vendor, count: 0 };
      entry.count += 1;
      byPattern.set(key, entry);
    }
    const repeat = [...byPattern.values()]
      .filter((entry) => entry.count >= 2)
      .sort((a, b) => b.count - a.count)[0];
    return repeat ?? null;
  }, [invoices]);

  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Home"
        section="Command center"
        description="Start the invoice workflow, review exceptions, and keep accounting connections ready."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading workspace" />
        ) : (
          <>
            {error && (
              <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}

            {/* ROI hero — the one gradient element on this page (spec §5) */}
            {invoices.length > 0 && (
              <section className="grid gap-4 rounded-3xl bg-gradient-to-r from-accent via-[#6366F1] to-[#4338CA] px-6 py-6 shadow-glow sm:grid-cols-3">
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-indigo-100/90">
                    Auto-extracted
                  </p>
                  <p className="mt-1 font-display text-3xl font-black text-white">
                    {extractedPct}%
                  </p>
                </div>
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-indigo-100/90">
                    Processed
                  </p>
                  <p className="mt-1 font-display text-3xl font-black text-white">
                    {formatCurrency(invoiceTotal(invoices), currency)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-indigo-100/90">
                    Time saved · est
                  </p>
                  <p className="mt-1 font-display text-3xl font-black text-[#67E8F9]">
                    {timeSavedHrs} hrs
                  </p>
                </div>
              </section>
            )}

            {/* approvals shortcut — routes to the mobile-first approvals view */}
            {awaitingApproval.length > 0 && (
              <Link
                href="/app/approvals"
                className="flex items-center justify-between rounded-2xl border border-success/30 bg-success-soft px-5 py-4 transition-shadow hover:shadow-card"
              >
                <p className="text-sm font-black text-success">
                  <CheckCircle2 size={15} className="mr-1.5 inline" />
                  {awaitingApproval.length} invoice
                  {awaitingApproval.length === 1 ? "" : "s"} awaiting your
                  approval —{" "}
                  {formatCurrency(invoiceTotal(awaitingApproval), currency)}
                </p>
                <span className="inline-flex items-center gap-1 text-sm font-black text-success">
                  Approve
                  <ArrowRight size={14} />
                </span>
              </Link>
            )}

            {/* proactive nudge — pattern detection, opt-in, dismissible (spec §5) */}
            {nudge && !dismissedNudge && (
              <div className="flex flex-col gap-3 rounded-2xl border border-dashed border-accent/50 bg-accent-soft/60 px-5 py-4 sm:flex-row sm:items-center">
                <p className="min-w-0 flex-1 text-sm font-bold text-accent-ink">
                  <Sparkles size={15} className="mr-1.5 inline" />✦{" "}
                  {nudge.count} {nudge.vendor} invoices carry the same flag —
                  add the mapping or rule once and every future invoice inherits
                  the fix.
                </p>
                <div className="flex shrink-0 items-center gap-2">
                  <Link
                    href="/app/rules"
                    className="inline-flex h-9 items-center rounded-lg bg-accent px-3.5 text-xs font-black text-white transition-colors hover:bg-accent-hover"
                  >
                    Create rule →
                  </Link>
                  <button
                    type="button"
                    onClick={() => {
                      setDismissedNudge(true);
                      window.localStorage.setItem(
                        "siftentry.home.nudgeDismissed",
                        "true",
                      );
                    }}
                    className="rounded-lg p-2 text-accent-ink/70 transition-colors hover:bg-accent-soft hover:text-accent-ink"
                    aria-label="Dismiss suggestion"
                  >
                    <X size={15} />
                  </button>
                </div>
              </div>
            )}

            <section className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
              <div className="rounded-[24px] border border-line bg-surface p-5 shadow-sm shadow-black/[0.03]">
                <p className="text-[11px] font-black uppercase tracking-[0.16em] text-ink-muted">
                  Next best action
                </p>
                <h2 className="mt-3 max-w-3xl text-3xl font-black leading-tight text-ink">
                  {invoices.length
                    ? exceptions.length
                      ? "Review exceptions before posting."
                      : ready.length
                        ? "Post approved invoices to accounting."
                        : "Validate extracted invoices."
                    : "Upload invoices to start the workspace."}
                </h2>
                <p className="mt-3 max-w-2xl text-sm font-semibold leading-6 text-ink-secondary">
                  SiftEntry keeps extraction, review, approval, export, and ERP
                  posting in one profile-aware workflow.
                </p>
                <div className="mt-5 flex flex-wrap gap-3">
                  <HomeAction
                    href="/app/invoices"
                    label={invoices.length ? "Open invoice queue" : "Upload invoices"}
                    icon={<Upload size={16} />}
                    primary
                  />
                  <HomeAction
                    href="/app/settings"
                    label="Client onboarding"
                    icon={<Settings2 size={16} />}
                  />
                  <HomeAction
                    href="/app/integrations"
                    label="Check integrations"
                    icon={<PlugZap size={16} />}
                  />
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <HomeMetric label="Invoices" value={String(invoices.length)} />
                <HomeMetric
                  label="Ready"
                  value={String(ready.length)}
                  tone={ready.length ? "accent" : "default"}
                />
                <HomeMetric
                  label="Posted"
                  value={`${posted.length} / ${invoices.length}`}
                  tone={posted.length ? "success" : "default"}
                />
                <HomeMetric
                  label="Exceptions"
                  value={String(exceptions.length)}
                  tone={exceptions.length ? "danger" : "success"}
                />
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-3">
              <ContentCard
                title="Workflow"
                subtitle="Where the current workspace stands."
                action={<FileText size={18} className="text-ink-muted" />}
              >
                <div className="space-y-3">
                  <FlowRow label="Uploaded" value={invoices.length} />
                  <FlowRow
                    label="Validated or approved"
                    value={
                      invoices.filter((invoice) =>
                        ["validated", "approved", "posted"].includes(
                          invoice.status,
                        ),
                      ).length
                    }
                  />
                  <FlowRow label="Ready to post" value={ready.length} />
                  <FlowRow label="Posted" value={posted.length} />
                </div>
              </ContentCard>

              <ContentCard
                title="Spend"
                subtitle="Current extracted invoice value."
                action={<Sparkles size={18} className="text-ink-muted" />}
              >
                <p className="text-3xl font-black text-ink">
                  {formatCurrency(invoiceTotal(invoices), currency)}
                </p>
                <p className="mt-2 text-sm font-semibold text-ink-secondary">
                  {formatCurrency(postedTotal(invoices), currency)} already
                  posted to accounting.
                </p>
                <Link
                  href="/app/analytics"
                  className="mt-5 inline-flex items-center gap-2 text-sm font-black text-accent dark:text-cyan"
                >
                  View insights <ArrowRight size={15} />
                </Link>
              </ContentCard>

              <ContentCard
                title="Profiles"
                subtitle="Keep tax, ledgers, and posting mode client-owned."
                action={<BadgeCheck size={18} className="text-ink-muted" />}
              >
                <div className="space-y-3 text-sm font-semibold text-ink-secondary">
                  <p>
                    Use onboarding profiles to store each client&apos;s accounting
                    system, country, currency, taxes, Tally mode, ledgers, and
                    sample invoices.
                  </p>
                  <Link
                    href="/app/settings"
                    className="inline-flex items-center gap-2 text-sm font-black text-accent dark:text-cyan"
                  >
                    Manage profiles <ArrowRight size={15} />
                  </Link>
                </div>
              </ContentCard>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function HomeAction({
  href,
  label,
  icon,
  primary = false,
}: {
  href: string;
  label: string;
  icon: ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-11 items-center justify-center gap-2 rounded-xl border px-4 text-sm font-black transition-colors",
        primary
          ? "border-accent bg-accent text-white hover:bg-accent-hover"
          : "border-line-strong bg-canvas text-ink hover:border-accent hover:bg-accent-soft",
      )}
    >
      {icon}
      {label}
    </Link>
  );
}

function HomeMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "accent" | "success" | "danger";
}) {
  return (
    <div className="rounded-[22px] border border-line bg-surface px-4 py-4 shadow-sm shadow-black/[0.03]">
      <p className="text-[11px] font-black uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </p>
      <p
        className={cn(
          "mt-3 text-3xl font-black leading-none text-ink",
          tone === "accent" && "text-accent dark:text-cyan",
          tone === "success" && "text-success",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function FlowRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm font-semibold text-ink-secondary">{label}</span>
      <span className="font-mono text-sm font-black text-ink">{value}</span>
    </div>
  );
}
