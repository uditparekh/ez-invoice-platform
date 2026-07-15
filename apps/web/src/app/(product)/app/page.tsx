"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Eye,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { invoiceTotal, postedTotal } from "@/lib/invoice-metrics";
import { formatCurrency } from "@/lib/utils";

export default function HomePage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const currency = invoices[0]?.currency || "USD";

  const needsReview = invoices.filter(
    (invoice) =>
      invoice.status === "extracted" || invoice.status === "needs_review",
  );
  const awaitingApproval = invoices.filter(
    (invoice) => invoice.status === "validated",
  );
  const failed = invoices.filter((invoice) => invoice.status === "failed");
  // Same predicate as the workspace's Sift button: everything Sift can clear.
  const siftable = invoices.filter(
    (invoice) =>
      invoice.status === "extracted" ||
      invoice.status === "needs_review" ||
      invoice.status === "validated" ||
      invoice.status === "failed" ||
      invoice.validation_issues.length > 0,
  );
  const inFlight = invoiceTotal(siftable);

  const actionGroups = [
    needsReview.length > 0,
    awaitingApproval.length > 0,
    failed.length > 0,
  ].filter(Boolean).length;

  // Weekly footer stats.
  const extractedPct = invoices.length
    ? Math.round(
        (invoices.filter((invoice) => invoice.status !== "uploaded").length /
          invoices.length) *
          1000,
      ) / 10
    : 0;

  // Date and greeting render after mount so the server and client HTML match.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setNow(new Date()), 0);
    return () => window.clearTimeout(timer);
  }, []);
  const today = now
    ? now.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
      })
    : "";
  const hour = now?.getHours() ?? -1;
  const dayGreeting =
    hour < 0
      ? "Welcome back"
      : hour < 12
        ? "Good morning"
        : hour < 17
          ? "Good afternoon"
          : "Good evening";

  // Proactive nudge: a vendor whose invoices repeat the same flag.
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

  const reviewVendors = [
    ...new Set(
      needsReview
        .map((invoice) => invoice.supplier.name)
        .filter((name): name is string => Boolean(name)),
    ),
  ].slice(0, 2);

  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Home"
        section="Today"
        description="Everything that needs you, in one glance."
      />
      <main className="mx-auto max-w-[880px] px-4 py-8 sm:px-6">
        {loading ? (
          <LoadingState label="Loading workspace" />
        ) : (
          <>
            {error && (
              <div className="mb-6 rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}

            <p className="text-sm font-bold text-ink-muted">{today}</p>
            <h1 className="mt-2 font-display text-3xl font-black leading-tight text-ink">
              {invoices.length === 0
                ? `${dayGreeting} — upload your first invoice.`
                : actionGroups === 0
                  ? `${dayGreeting} — you're all clear.`
                  : `${dayGreeting} — ${actionGroups} thing${actionGroups === 1 ? "" : "s"} need${actionGroups === 1 ? "s" : ""} you.`}
            </h1>

            {/* Sift hero — the one bold element on this page */}
            {siftable.length > 0 ? (
              <Link
                href="/app/sift"
                className="mt-6 flex flex-col gap-4 rounded-3xl bg-gradient-to-r from-[#111827] via-[#1E1B4B] to-[#312E81] px-6 py-5 shadow-glow transition-transform hover:scale-[1.005] sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-indigo-200/80">
                    Sift mode
                  </p>
                  <p className="mt-1 text-lg font-black leading-snug text-white sm:text-xl">
                    {siftable.length} invoice{siftable.length === 1 ? "" : "s"}{" "}
                    · {formatCurrency(inFlight, currency)} in flight — clear it
                    one keypress at a time.
                  </p>
                </div>
                <span className="inline-flex h-12 shrink-0 items-center gap-2 self-start rounded-xl bg-white px-5 text-sm font-black text-[#1E1B4B] shadow-sm sm:self-auto">
                  <Zap size={16} />
                  Start sifting
                  <ArrowRight size={15} />
                </span>
              </Link>
            ) : (
              <div className="mt-6 flex flex-col gap-4 rounded-3xl border border-line bg-surface px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                    Queue clear
                  </p>
                  <p className="mt-1 text-lg font-black leading-snug text-ink">
                    Nothing waiting on you right now.
                  </p>
                </div>
                <Link
                  href="/app/invoices"
                  className="inline-flex h-12 shrink-0 items-center gap-2 self-start rounded-xl bg-accent px-5 text-sm font-black text-white transition-colors hover:bg-accent-hover sm:self-auto"
                >
                  <Upload size={16} />
                  Upload invoices
                </Link>
              </div>
            )}

            {/* Glanceable counts — each pill is a one-tap filter */}
            {invoices.length > 0 && (
              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <StatPill
                  label="Needs review"
                  value={needsReview.length}
                  href="/app/invoices?status=needs_review"
                />
                <StatPill
                  label="Awaiting approval"
                  value={awaitingApproval.length}
                  href="/app/approvals"
                />
                <StatPill
                  label="Exceptions"
                  value={failed.length}
                  href="/app/invoices?status=failed"
                  tone={failed.length > 0 ? "danger" : "default"}
                />
              </div>
            )}

            {/* Work tray — only rows that need action render */}
            <div className="mt-8 border-t border-line">
              {needsReview.length > 0 && (
                <ActionRow
                  icon={Eye}
                  iconClass="text-gold-ink"
                  title={`${needsReview.length} invoice${needsReview.length === 1 ? "" : "s"} need${needsReview.length === 1 ? "s" : ""} review`}
                  subtitle={
                    reviewVendors.length
                      ? reviewVendors.join(" · ")
                      : "Extraction ready for a human check"
                  }
                  href="/app/invoices?status=needs_review"
                  cta="Review"
                />
              )}
              {awaitingApproval.length > 0 && (
                <ActionRow
                  icon={CheckCircle2}
                  iconClass="text-success"
                  title={`${awaitingApproval.length} approval${awaitingApproval.length === 1 ? "" : "s"} waiting — ${formatCurrency(invoiceTotal(awaitingApproval), currency)}`}
                  subtitle="Validated and ready for sign-off"
                  href="/app/approvals"
                  cta="Approve"
                />
              )}
              {failed.length > 0 && (
                <ActionRow
                  icon={AlertTriangle}
                  iconClass="text-danger"
                  title={`${failed.length} posting${failed.length === 1 ? "" : "s"} failed`}
                  subtitle="Open the exceptions filter to retry or fix mappings"
                  href="/app/invoices?status=failed"
                  cta="Fix"
                />
              )}
              <ActionRow
                icon={Upload}
                iconClass="text-ink-muted"
                title="Upload new invoices"
                subtitle="PDFs land in the queue for extraction"
                href="/app/invoices"
                cta="Upload"
              />
            </div>

            {/* Proactive nudge — pattern detection, dismissible */}
            {nudge && !dismissedNudge && (
              <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-dashed border-accent/50 bg-accent-soft/60 px-5 py-4 sm:flex-row sm:items-center">
                <p className="min-w-0 flex-1 text-sm font-bold text-accent-ink">
                  <Sparkles size={15} className="mr-1.5 inline" />
                  {nudge.count} {nudge.vendor} invoices carry the same flag —
                  add the mapping once and every future invoice inherits the
                  fix.
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

            {/* Quiet weekly footer — depth lives one click away in Insights */}
            {invoices.length > 0 && (
              <p className="mt-8 text-sm font-bold text-ink-muted">
                This week: {invoices.length} processed · {extractedPct}%
                auto-extracted · {formatCurrency(postedTotal(invoices), currency)}{" "}
                posted ·{" "}
                <Link
                  href="/app/analytics"
                  className="font-black text-accent dark:text-cyan"
                >
                  View insights <ArrowRight size={13} className="inline" />
                </Link>
              </p>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function StatPill({
  label,
  value,
  href,
  tone = "default",
}: {
  label: string;
  value: number;
  href: string;
  tone?: "default" | "danger";
}) {
  return (
    <Link
      href={href}
      className={
        tone === "danger"
          ? "rounded-2xl border border-danger/25 bg-danger-soft px-4 py-3 transition-shadow hover:shadow-card"
          : "rounded-2xl bg-surface-subtle px-4 py-3 transition-shadow hover:shadow-card"
      }
    >
      <p
        className={
          tone === "danger"
            ? "text-xs font-extrabold text-danger"
            : "text-xs font-extrabold text-ink-muted"
        }
      >
        {label}
      </p>
      <p
        className={
          tone === "danger"
            ? "mt-0.5 font-display text-2xl font-black text-danger"
            : "mt-0.5 font-display text-2xl font-black text-ink"
        }
      >
        {value}
      </p>
    </Link>
  );
}

function ActionRow({
  icon: Icon,
  iconClass,
  title,
  subtitle,
  href,
  cta,
}: {
  icon: LucideIcon;
  iconClass: string;
  title: string;
  subtitle: string;
  href: string;
  cta: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center justify-between gap-4 border-b border-line px-1 py-4 transition-colors hover:bg-surface-subtle"
    >
      <span className="flex min-w-0 items-center gap-3.5">
        <Icon size={19} className={iconClass} />
        <span className="min-w-0">
          <span className="block truncate text-[15px] font-black text-ink">
            {title}
          </span>
          <span className="block truncate text-xs font-semibold text-ink-secondary">
            {subtitle}
          </span>
        </span>
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 text-sm font-black text-accent">
        {cta}
        <ArrowRight
          size={14}
          className="transition-transform group-hover:translate-x-0.5"
        />
      </span>
    </Link>
  );
}
