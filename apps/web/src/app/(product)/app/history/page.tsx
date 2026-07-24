"use client";

import {
  ArrowUpRight,
  CheckCircle2,
  FileClock,
  FileDown,
  Lock,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  UploadCloud,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { Invoice, PostingResult } from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";

/** History — UI Spec §10. Append-only audit surface:
 *  Activity (event feed from live invoices) · Posting log & retry (real posting
 *  attempts with raw responses, ↻ Retry via /api/postings/{id}/retry). */

type HistoryTab = "activity" | "postings";
type ActivityFilter = "all" | "postings" | "approvals" | "flags";

export default function HistoryPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const [tab, setTab] = useState<HistoryTab>("activity");
  const [filter, setFilter] = useState<ActivityFilter>("all");

  const events = useMemo(() => buildEvents(invoices), [invoices]);
  const filtered = events.filter((event) =>
    filter === "all" ? true : event.kind === filter,
  );
  const failedCount = invoices.filter(
    (invoice) => invoice.status === "failed",
  ).length;

  function exportAudit() {
    const header = "timestamp,invoice,supplier,event,detail,amount,currency";
    const rows = events.map((event) =>
      [
        event.at,
        event.invoiceNumber,
        event.supplier.replaceAll(",", " "),
        event.kind,
        event.title.replaceAll(",", " "),
        event.amount,
        event.currency,
      ].join(","),
    );
    const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "siftentry_audit_log.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="History"
        section="Audit trail"
        description="Every extraction, approval, posting attempt, and correction — recorded, never overwritten."
        action={
          <div className="flex w-full flex-col gap-2.5 sm:w-auto sm:flex-row sm:items-center sm:gap-2">
            <span className="inline-flex h-8 items-center gap-1.5 self-start rounded-full bg-success-soft px-3 text-[11px] font-black text-success sm:h-9 sm:px-3.5 sm:text-xs">
              <Lock size={13} />
              APPEND-ONLY · AUDIT-GRADE
            </span>
            <button
              type="button"
              onClick={exportAudit}
              className="inline-flex h-11 items-center gap-2 self-start rounded-xl bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover"
            >
              <FileDown size={16} />
              Export audit log
            </button>
          </div>
        }
      />

      <div className="border-b border-line bg-shell/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] gap-1 px-4 sm:px-6 lg:px-8">
          <TabButton active={tab === "activity"} onClick={() => setTab("activity")}>
            Activity
          </TabButton>
          <TabButton active={tab === "postings"} onClick={() => setTab("postings")}>
            Posting log &amp; retry
            {failedCount > 0 && (
              <span className="ml-1.5 rounded-full bg-danger-soft px-2 py-0.5 font-mono text-[11px] font-black text-danger">
                {failedCount}
              </span>
            )}
          </TabButton>
        </div>
      </div>

      <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading audit trail" />
        ) : error ? (
          <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
            {error}
          </div>
        ) : !invoices.length ? (
          <EmptyState
            icon={FileClock}
            title="Every action will be recorded here"
            description="Uploads, extractions, corrections, approvals, and posting attempts — audit-grade, append-only."
          />
        ) : tab === "activity" ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {(
                [
                  ["all", "All"],
                  ["postings", "Postings"],
                  ["approvals", "Approvals"],
                  ["flags", "Flags"],
                ] as [ActivityFilter, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilter(value)}
                  className={cn(
                    "inline-flex h-9 items-center rounded-full border px-3.5 text-xs font-black transition-colors",
                    filter === value
                      ? "border-accent bg-accent-soft text-accent-ink"
                      : "border-line bg-surface text-ink-secondary hover:border-accent hover:text-accent",
                  )}
                >
                  {label}
                </button>
              ))}
              <span className="ml-auto inline-flex items-center gap-1.5 text-xs font-black text-success">
                <span className="size-2 animate-pulse rounded-full bg-success" />
                LIVE
              </span>
            </div>
            <section className="rounded-2xl border border-line bg-surface shadow-card">
              {filtered.length ? (
                <div className="divide-y divide-line">
                  {filtered.slice(0, 30).map((event) => (
                    <div
                      key={event.id}
                      className="flex items-start gap-3 px-4 py-4 sm:gap-4 sm:px-5"
                    >
                      <span
                        className={cn(
                          "grid size-9 shrink-0 place-items-center rounded-xl",
                          event.kind === "postings"
                            ? "bg-cyan-soft text-cyan-ink"
                            : event.kind === "approvals"
                              ? "bg-success-soft text-success"
                              : event.kind === "flags"
                                ? "bg-gold-soft text-gold-ink"
                                : "bg-surface-strong text-ink-secondary",
                        )}
                      >
                        {event.icon}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-black text-ink">
                          <span>{event.title}</span>
                          <StatusBadge status={event.status} />
                        </div>
                        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold text-ink-secondary">
                          <span className="min-w-0 break-words">
                            {event.supplier}
                          </span>
                          <span aria-hidden="true" className="text-ink-muted">
                            ·
                          </span>
                          <span className="break-all font-mono">
                            {event.invoiceNumber}
                          </span>
                          <span aria-hidden="true" className="text-ink-muted">
                            ·
                          </span>
                          <span className="whitespace-nowrap font-mono">
                            {formatCurrency(event.amount, event.currency)}
                          </span>
                        </div>
                      </div>
                      <span className="shrink-0 whitespace-nowrap pt-0.5 text-xs font-bold text-ink-muted">
                        {timeAgo(event.at)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="px-5 py-10 text-center text-sm font-semibold text-ink-muted">
                  No {filter} events yet.
                </p>
              )}
            </section>
          </>
        ) : (
          <PostingLog invoices={invoices} />
        )}
      </main>
    </div>
  );
}

/* ================= posting log & retry ================= */

function PostingLog({ invoices }: { invoices: Invoice[] }) {
  const targets = useMemo(
    () =>
      invoices
        .filter((invoice) =>
          ["posted", "failed", "approved"].includes(invoice.status),
        )
        .slice(0, 12),
    [invoices],
  );
  const [postings, setPostings] = useState<PostingResult[] | null>(null);
  const [retrying, setRetrying] = useState<string>("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const results = await Promise.all(
        targets.map(async (invoice) => {
          try {
            const response = await fetch(`/api/invoices/${invoice.id}/postings`);
            if (!response.ok) return [] as PostingResult[];
            const payload = (await response.json()) as unknown;
            return (Array.isArray(payload) ? payload : []) as PostingResult[];
          } catch {
            return [] as PostingResult[];
          }
        }),
      );
      if (!cancelled)
        setPostings(
          results
            .flat()
            .sort(
              (a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
            ),
        );
    })();
    return () => {
      cancelled = true;
    };
  }, [targets]);

  async function retry(posting: PostingResult) {
    setRetrying(posting.id);
    setNotice("");
    try {
      const response = await fetch(`/api/postings/${posting.id}/retry`, {
        method: "POST",
      });
      const payload = (await response.json().catch(() => null)) as
        | PostingResult
        | { detail?: string }
        | null;
      if (!response.ok)
        throw new Error(
          (payload as { detail?: string })?.detail ?? "Retry failed.",
        );
      setNotice(
        `Retry submitted for ${posting.invoice_id.slice(0, 8)} — result recorded below.`,
      );
      if (payload && "id" in (payload as PostingResult))
        setPostings((current) => [payload as PostingResult, ...(current ?? [])]);
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setRetrying("");
    }
  }

  if (postings === null) return <LoadingState label="Loading posting attempts" />;
  if (!postings.length)
    return (
      <EmptyState
        icon={UploadCloud}
        title="No posting attempts yet"
        description="Every attempt lands here with the raw system response — successes and failures alike, nothing overwritten."
      />
    );

  const invoiceById = new Map(invoices.map((invoice) => [invoice.id, invoice]));

  return (
    <section className="rounded-2xl border border-line bg-surface shadow-card">
      {notice && (
        <p className="border-b border-line bg-accent-soft px-5 py-3 text-sm font-bold text-accent-ink">
          {notice}
        </p>
      )}
      {/* Mobile: posting cards */}
      <div className="md:hidden">
        {postings.slice(0, 25).map((posting) => {
          const invoice = invoiceById.get(posting.invoice_id);
          const failed = !posting.success;
          const mappingIssue = /ledger|account|not found|map/i.test(
            posting.message || "",
          );
          return (
            <article
              key={posting.id}
              className={cn(
                "border-b border-line px-4 py-4",
                failed && "bg-danger-soft/30",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm font-black text-ink">
                    {invoice?.invoice_number || posting.invoice_id.slice(0, 8)}
                  </p>
                  <p className="truncate text-xs font-bold text-ink-secondary">
                    {invoice?.supplier.name || ""}
                  </p>
                </div>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-black",
                    failed
                      ? "bg-danger-soft text-danger"
                      : "bg-success-soft text-success",
                  )}
                >
                  {failed ? <XCircle size={11} /> : <CheckCircle2 size={11} />}
                  {failed ? "FAILED" : "SUCCESS"}
                </span>
              </div>
              <p className="mt-2 text-xs font-bold capitalize text-ink-secondary">
                {posting.target}
                {posting.dry_run ? " · dry run" : ""}
                <span className="text-ink-muted">
                  {" · "}
                  {new Date(posting.created_at).toLocaleString()}
                </span>
              </p>
              <p className="mt-1.5 break-words font-mono text-xs font-semibold text-ink-secondary">
                {posting.message ||
                  (posting.external_id
                    ? `Accepted · ${posting.external_id}`
                    : "Recorded")}
              </p>
              {failed && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={retrying === posting.id}
                    onClick={() => void retry(posting)}
                    className="inline-flex h-11 flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-black text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
                  >
                    {retrying === posting.id ? (
                      <LoaderCircle size={13} className="animate-spin" />
                    ) : (
                      <RotateCcw size={13} />
                    )}
                    Retry
                  </button>
                  {mappingIssue && (
                    <Link
                      href="/app/rules"
                      className="inline-flex h-11 flex-1 items-center justify-center gap-1 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                    >
                      Fix mapping
                      <ArrowUpRight size={12} />
                    </Link>
                  )}
                </div>
              )}
            </article>
          );
        })}
        {!postings.length && (
          <p className="px-4 py-10 text-center text-sm font-semibold text-ink-muted">
            No posting attempts yet.
          </p>
        )}
      </div>

      {/* Desktop: full table */}
      <div className="hidden overflow-x-auto md:block" data-scroll-region="true">
        <table className="w-full min-w-[820px] border-collapse text-left text-sm">
          <thead className="bg-surface-subtle">
            <tr className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Invoice</th>
              <th className="px-4 py-3">Target</th>
              <th className="px-4 py-3">Result · system response</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {postings.slice(0, 25).map((posting) => {
              const invoice = invoiceById.get(posting.invoice_id);
              const failed = !posting.success;
              const mappingIssue = /ledger|account|not found|map/i.test(
                posting.message || "",
              );
              return (
                <tr
                  key={posting.id}
                  className={cn(
                    "border-t border-line align-top",
                    failed && "bg-danger-soft/30",
                  )}
                >
                  <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs font-bold text-ink-muted">
                    {new Date(posting.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3.5">
                    <p className="font-mono text-sm font-black text-ink">
                      {invoice?.invoice_number || posting.invoice_id.slice(0, 8)}
                    </p>
                    <p className="truncate text-xs font-bold text-ink-secondary">
                      {invoice?.supplier.name || ""}
                    </p>
                  </td>
                  <td className="px-4 py-3.5 text-sm font-bold capitalize text-ink-secondary">
                    {posting.target}
                    {posting.dry_run ? " · dry run" : ""}
                  </td>
                  <td className="max-w-[340px] px-4 py-3.5">
                    <span
                      className={cn(
                        "mr-2 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-black",
                        failed
                          ? "bg-danger-soft text-danger"
                          : "bg-success-soft text-success",
                      )}
                    >
                      {failed ? <XCircle size={11} /> : <CheckCircle2 size={11} />}
                      {failed ? "FAILED" : "SUCCESS"}
                    </span>
                    <span className="break-words font-mono text-xs font-semibold text-ink-secondary">
                      {posting.message ||
                        (posting.external_id
                          ? `Accepted · ${posting.external_id}`
                          : "Recorded")}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    {failed && (
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={retrying === posting.id}
                          onClick={() => void retry(posting)}
                          className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-black text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
                        >
                          {retrying === posting.id ? (
                            <LoaderCircle size={13} className="animate-spin" />
                          ) : (
                            <RotateCcw size={13} />
                          )}
                          Retry
                        </button>
                        {mappingIssue && (
                          <Link
                            href="/app/rules"
                            className="inline-flex h-9 items-center gap-1 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                          >
                            Fix mapping
                            <ArrowUpRight size={12} />
                          </Link>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-line bg-surface-subtle px-5 py-3 text-xs font-semibold text-ink-muted">
        Every attempt is recorded with the raw system response — nothing is
        overwritten. Failed postings can be retried manually anytime.
      </p>
    </section>
  );
}

/* ================= helpers ================= */

type AuditEvent = {
  id: string;
  kind: ActivityFilter;
  icon: ReactNode;
  title: string;
  status: Invoice["status"];
  supplier: string;
  invoiceNumber: string;
  amount: number;
  currency: string;
  at: string;
};

function buildEvents(invoices: Invoice[]): AuditEvent[] {
  const events: AuditEvent[] = [];
  for (const invoice of invoices) {
    const base = {
      supplier: invoice.supplier.name || "Supplier pending",
      invoiceNumber: invoice.invoice_number || invoice.id.slice(0, 8),
      amount: invoice.total || 0,
      currency: invoice.currency || "USD",
    };
    if (invoice.status === "posted")
      events.push({
        id: `${invoice.id}-posted`,
        kind: "postings",
        icon: <UploadCloud size={16} />,
        title: "Posted to accounting system",
        status: invoice.status,
        at: invoice.updated_at,
        ...base,
      });
    else if (invoice.status === "failed")
      events.push({
        id: `${invoice.id}-failed`,
        kind: "postings",
        icon: <XCircle size={16} />,
        title: "Posting failed — retry available",
        status: invoice.status,
        at: invoice.updated_at,
        ...base,
      });
    else if (invoice.status === "approved")
      events.push({
        id: `${invoice.id}-approved`,
        kind: "approvals",
        icon: <ShieldCheck size={16} />,
        title: "Approved for posting",
        status: invoice.status,
        at: invoice.updated_at,
        ...base,
      });
    else if (
      invoice.status === "needs_review" ||
      invoice.validation_issues.length
    )
      events.push({
        id: `${invoice.id}-flag`,
        kind: "flags",
        icon: <FileClock size={16} />,
        title: invoice.validation_issues[0] || "Flagged for review",
        status: invoice.status,
        at: invoice.updated_at,
        ...base,
      });
    else
      events.push({
        id: `${invoice.id}-recorded`,
        kind: "all",
        icon: <FileClock size={16} />,
        title: "Invoice recorded",
        status: invoice.status,
        at: invoice.created_at,
        ...base,
      });
  }
  return events.sort(
    (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
  );
}

function timeAgo(value: string) {
  const delta = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(delta) || delta < 0) return "";
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

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
