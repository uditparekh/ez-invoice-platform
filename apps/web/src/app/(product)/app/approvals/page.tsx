"use client";

import {
  ArrowUpRight,
  BadgeCheck,
  CheckCircle2,
  LoaderCircle,
  PartyPopper,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { ApiErrorPayload, Invoice } from "@/lib/types";
import { apiErrorMessage, cn, formatCurrency, formatDate } from "@/lib/utils";

/** Mobile approval view — UI Spec §16.
 *  One job: approve on the go. Big amount, confidence, tax-verified signal,
 *  thumb-sized actions. Works on desktop too; designed for 390px first. */

export default function ApprovalsPage() {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const [decided, setDecided] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");
  const [approvedCount, setApprovedCount] = useState(0);

  const queue = useMemo(
    () =>
      invoices.filter(
        (invoice) =>
          invoice.status === "validated" && !decided.has(invoice.id),
      ),
    [invoices, decided],
  );
  const active = queue[0] ?? null;

  async function approve(invoice: Invoice) {
    setBusyId(invoice.id);
    setActionError("");
    try {
      const response = await fetch(`/api/invoices/${invoice.id}/approve`, {
        method: "POST",
      });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        throw new Error(apiErrorMessage(payload, "Could not approve this invoice."));
      }
      setDecided((current) => new Set(current).add(invoice.id));
      setApprovedCount((count) => count + 1);
    } catch (approveError) {
      setActionError((approveError as Error).message);
    } finally {
      setBusyId("");
    }
  }

  const taxVerified = (invoice: Invoice) =>
    Math.abs(invoice.subtotal + invoice.tax_total - invoice.total) <= 1;

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <div className="mx-auto max-w-[480px] px-4 py-5">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-black text-ink">Approvals</h1>
          <span
            className={cn(
              "inline-flex h-8 items-center rounded-full px-3 text-xs font-black",
              queue.length
                ? "bg-gold-soft text-gold-ink"
                : "bg-success-soft text-success",
            )}
          >
            {queue.length ? `${queue.length} waiting` : "All clear"}
          </span>
        </div>

        {loading ? (
          <div className="mt-5">
            <LoadingState label="Loading approvals" />
          </div>
        ) : error ? (
          <p className="mt-5 rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
            {error}
          </p>
        ) : !active ? (
          <div className="mt-5">
            {approvedCount ? (
              <div className="rounded-3xl border border-line bg-surface px-6 py-12 text-center shadow-card">
                <PartyPopper className="mx-auto text-cyan-ink" size={36} />
                <h2 className="mt-4 text-2xl font-black text-ink">
                  All approvals done
                </h2>
                <p className="mt-2 text-sm font-semibold text-ink-secondary">
                  {approvedCount} approved this session — they&apos;re queued for
                  posting.
                </p>
                <Link
                  href="/app/invoices"
                  className="mt-6 inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-black text-white"
                >
                  Open queue
                  <ArrowUpRight size={15} />
                </Link>
              </div>
            ) : (
              <EmptyState
                icon={BadgeCheck}
                title="Nothing awaiting approval"
                description="Validated invoices routed by an approval rule land here for one-tap sign-off."
              />
            )}
          </div>
        ) : (
          <>
            {/* the one-job card */}
            <article className="mt-5 rounded-3xl border border-line bg-surface p-5 shadow-pop">
              <p className="text-[11px] font-black uppercase tracking-[0.14em] text-ink-muted">
                {active.supplier.name || "Supplier pending"} · #
                {active.invoice_number || "—"}
              </p>
              <p className="mt-2 font-mono text-4xl font-black tracking-tight text-ink">
                {formatCurrency(active.total, active.currency)}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-soft px-3 py-1 text-xs font-black text-cyan-ink">
                  <ShieldCheck size={12} />
                  {active.confidence != null
                    ? `${Math.round(active.confidence <= 1 ? active.confidence * 100 : active.confidence)}% confidence`
                    : "Validated"}
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-black",
                    taxVerified(active)
                      ? "bg-success-soft text-success"
                      : "bg-gold-soft text-gold-ink",
                  )}
                >
                  {taxVerified(active) ? "tax verified ✓" : "tax check pending"}
                </span>
              </div>
              <p className="mt-3 text-sm font-semibold leading-6 text-ink-secondary">
                {formatDate(active.invoice_date)} · {active.lines.length} line
                {active.lines.length === 1 ? "" : "s"} · tax{" "}
                <span className="font-mono">
                  {formatCurrency(active.tax_total, active.currency)}
                </span>
              </p>

              {actionError && (
                <p className="mt-4 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
                  {actionError}
                </p>
              )}

              <div className="mt-5 grid gap-2.5">
                <button
                  type="button"
                  disabled={busyId === active.id}
                  onClick={() => void approve(active)}
                  className="inline-flex h-14 items-center justify-center gap-2.5 rounded-2xl bg-success text-base font-black text-white shadow-lg shadow-success/25 transition-transform hover:scale-[1.01] disabled:opacity-60"
                >
                  {busyId === active.id ? (
                    <LoaderCircle size={19} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={19} />
                  )}
                  Approve
                </button>
                <div className="grid grid-cols-2 gap-2.5">
                  <Link
                    href={`/app/invoices?invoice=${active.id}&mode=review`}
                    className="inline-flex h-12 items-center justify-center rounded-2xl border border-line-strong bg-surface text-sm font-black text-danger transition-colors hover:border-danger hover:bg-danger-soft"
                  >
                    Reject / fix
                  </Link>
                  {!active.id.startsWith("preview-") && active.source_path ? (
                    <a
                      href={`/api/invoices/${active.id}/document`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-12 items-center justify-center gap-1.5 rounded-2xl border border-line-strong bg-surface text-sm font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                    >
                      View PDF
                      <ArrowUpRight size={14} />
                    </a>
                  ) : (
                    <span className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-surface-subtle text-sm font-bold text-ink-muted">
                      PDF unavailable
                    </span>
                  )}
                </div>
              </div>
            </article>

            {/* waiting stack */}
            {queue.length > 1 && (
              <div className="mt-4 space-y-2.5">
                {queue.slice(1, 4).map((invoice) => (
                  <div
                    key={invoice.id}
                    className="flex items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 opacity-70 shadow-card"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-black uppercase tracking-wide text-ink-muted">
                        {invoice.supplier.name || "Supplier"} · #
                        {invoice.invoice_number || "—"}
                      </p>
                      <p className="font-mono text-lg font-black text-ink">
                        {formatCurrency(invoice.total, invoice.currency)}
                      </p>
                    </div>
                    <span className="text-xs font-bold text-ink-muted">
                      waiting
                    </span>
                  </div>
                ))}
                {queue.length > 4 && (
                  <p className="text-center text-xs font-bold text-ink-muted">
                    +{queue.length - 4} more in the queue
                  </p>
                )}
              </div>
            )}

            <p className="mt-5 text-center text-xs font-semibold text-ink-muted">
              Approvals are recorded in History. Rejecting opens the full Review
              Workspace on desktop.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
