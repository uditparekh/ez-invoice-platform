"use client";

import {
  ArrowUpRight,
  BadgeCheck,
  CheckCircle2,
  FileText,
  LoaderCircle,
  PartyPopper,
  ShieldCheck,
  Undo2,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { ApiErrorPayload, Invoice } from "@/lib/types";
import { apiErrorMessage, cn, formatCurrency, formatDate } from "@/lib/utils";

/** Mobile approval view — UI Spec §16, extended for the full phone workflow:
 *  one-job card (summary), Approve, Reject-with-reason, quick Fix, and an
 *  inline PDF — a real phone-friendly workflow, installable as a PWA. */

type Sheet = "none" | "reject" | "fix" | "pdf";

export default function ApprovalsPage() {
  const { invoices, loading, error, reload } = useWorkspaceInvoices();
  const [decided, setDecided] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [approvedCount, setApprovedCount] = useState(0);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [sheet, setSheet] = useState<Sheet>("none");
  const [reason, setReason] = useState("");
  const [fixNumber, setFixNumber] = useState("");
  const [fixTotal, setFixTotal] = useState("");
  const [fixDate, setFixDate] = useState("");

  const queue = useMemo(
    () =>
      invoices.filter(
        (invoice) => invoice.status === "validated" && !decided.has(invoice.id),
      ),
    [invoices, decided],
  );
  const active = queue[0] ?? null;

  function settle(invoiceId: string) {
    setDecided((current) => new Set(current).add(invoiceId));
    setSheet("none");
    setReason("");
  }

  async function post(path: string, body?: unknown): Promise<void> {
    const response = await fetch(path, {
      method: body === undefined ? "POST" : "POST",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = (await response
        .json()
        .catch(() => null)) as ApiErrorPayload | null;
      throw new Error(
        apiErrorMessage(payload ?? {}, "The action could not be completed."),
      );
    }
  }

  async function approve(invoice: Invoice) {
    setBusy(true);
    setActionError("");
    try {
      await post(`/api/invoices/${invoice.id}/approve`);
      settle(invoice.id);
      setApprovedCount((count) => count + 1);
    } catch (approveError) {
      setActionError((approveError as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reject(invoice: Invoice) {
    if (reason.trim().length < 3) {
      setActionError("Add a short reason so the reviewer knows what to fix.");
      return;
    }
    setBusy(true);
    setActionError("");
    try {
      await fetch(`/api/invoices/${invoice.id}/send-back`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() }),
      }).then(async (response) => {
        if (!response.ok) {
          const payload = (await response
            .json()
            .catch(() => null)) as ApiErrorPayload | null;
          throw new Error(
            apiErrorMessage(payload ?? {}, "Could not send this invoice back."),
          );
        }
      });
      settle(invoice.id);
      setRejectedCount((count) => count + 1);
    } catch (rejectError) {
      setActionError((rejectError as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function applyFix(invoice: Invoice) {
    setBusy(true);
    setActionError("");
    try {
      const patch: Record<string, unknown> = {};
      if (fixNumber.trim() && fixNumber.trim() !== invoice.invoice_number)
        patch.invoice_number = fixNumber.trim();
      if (fixTotal.trim()) {
        const parsed = Number(fixTotal);
        if (!Number.isFinite(parsed))
          throw new Error("Total must be a number.");
        if (parsed !== invoice.total) patch.total = parsed;
      }
      if (fixDate && fixDate !== invoice.invoice_date)
        patch.invoice_date = fixDate;
      if (Object.keys(patch).length) {
        const response = await fetch(`/api/invoices/${invoice.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        if (!response.ok) {
          const payload = (await response
            .json()
            .catch(() => null)) as ApiErrorPayload | null;
          throw new Error(
            apiErrorMessage(payload ?? {}, "Could not save the fix."),
          );
        }
        await post(`/api/invoices/${invoice.id}/validate`);
        reload();
      }
      setSheet("none");
    } catch (fixError) {
      setActionError((fixError as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openFix(invoice: Invoice) {
    setFixNumber(invoice.invoice_number || "");
    setFixTotal(String(invoice.total ?? ""));
    setFixDate(invoice.invoice_date || "");
    setActionError("");
    setSheet("fix");
  }

  const taxVerified = (invoice: Invoice) =>
    Math.abs(invoice.subtotal + invoice.tax_total - invoice.total) <= 1;

  const sessionCount = approvedCount + rejectedCount;

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <div className="mx-auto max-w-[480px] px-4 py-5 pb-10">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-ink">Approvals</h1>
          <span
            className={cn(
              "inline-flex h-8 items-center rounded-full px-3 text-xs font-semibold",
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
          <p className="mt-5 rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
            {error}
          </p>
        ) : !active ? (
          <div className="mt-5">
            {sessionCount ? (
              <div className="rounded-2xl border border-line bg-surface px-6 py-12 text-center shadow-card">
                <PartyPopper className="mx-auto text-cyan-ink" size={36} />
                <h2 className="mt-4 text-2xl font-semibold text-ink">
                  All approvals done
                </h2>
                <p className="mt-2 text-sm font-semibold text-ink-secondary">
                  {approvedCount} approved
                  {rejectedCount
                    ? ` · ${rejectedCount} sent back for review`
                    : ""}{" "}
                  this session.
                </p>
                <Link
                  href="/app/invoices"
                  className="mt-6 inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold text-white"
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
            {/* the one-job card: invoice summary */}
            <article className="mt-5 rounded-2xl border border-line bg-surface p-5 shadow-pop">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
                {active.supplier.name || "Supplier pending"} · #
                {active.invoice_number || "—"}
              </p>
              <p className="mt-2 font-mono text-4xl font-semibold tracking-tight text-ink">
                {formatCurrency(active.total, active.currency)}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-soft px-3 py-1 text-xs font-semibold text-cyan-ink">
                  <ShieldCheck size={12} />
                  {active.confidence != null
                    ? `${Math.round(active.confidence <= 1 ? active.confidence * 100 : active.confidence)}% confidence`
                    : "Validated"}
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
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

              {actionError && sheet === "none" && (
                <p className="mt-4 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
                  {actionError}
                </p>
              )}

              <div className="mt-5 grid gap-2.5">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void approve(active)}
                  className="inline-flex h-14 items-center justify-center gap-2.5 rounded-2xl bg-success text-base font-semibold text-white shadow-lg shadow-success/25 transition-transform hover:scale-[1.01] disabled:opacity-60"
                >
                  {busy && sheet === "none" ? (
                    <LoaderCircle size={19} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={19} />
                  )}
                  Approve
                </button>
                <div className="grid grid-cols-3 gap-2.5">
                  <button
                    type="button"
                    onClick={() => {
                      setActionError("");
                      setSheet("reject");
                    }}
                    className="inline-flex h-12 items-center justify-center gap-1.5 rounded-2xl border border-line-strong bg-surface text-sm font-semibold text-danger transition-colors hover:border-danger hover:bg-danger-soft"
                  >
                    <Undo2 size={14} />
                    Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => openFix(active)}
                    className="inline-flex h-12 items-center justify-center gap-1.5 rounded-2xl border border-line-strong bg-surface text-sm font-semibold text-gold-ink transition-colors hover:border-gold-ink hover:bg-gold-soft"
                  >
                    <Wrench size={14} />
                    Fix
                  </button>
                  {!active.id.startsWith("preview-") && active.source_path ? (
                    <button
                      type="button"
                      onClick={() =>
                        setSheet((current) =>
                          current === "pdf" ? "none" : "pdf",
                        )
                      }
                      className={cn(
                        "inline-flex h-12 items-center justify-center gap-1.5 rounded-2xl border text-sm font-semibold transition-colors",
                        sheet === "pdf"
                          ? "border-accent bg-accent-soft text-accent-ink"
                          : "border-line-strong bg-surface text-accent-ink hover:border-accent hover:bg-accent-soft",
                      )}
                    >
                      <FileText size={14} />
                      PDF
                    </button>
                  ) : (
                    <span className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-surface-subtle text-xs font-medium text-ink-muted">
                      No PDF
                    </span>
                  )}
                </div>
              </div>

              {/* inline PDF */}
              {sheet === "pdf" && (
                <div className="mt-4">
                  <object
                    data={`/api/invoices/${active.id}/document`}
                    type="application/pdf"
                    className="h-[420px] w-full rounded-2xl border border-line bg-surface-subtle"
                  >
                    <div className="grid h-[200px] place-items-center rounded-2xl border border-dashed border-line-strong bg-surface-subtle px-4 text-center">
                      <p className="text-xs font-medium text-ink-muted">
                        Inline preview isn&apos;t supported in this browser.
                      </p>
                    </div>
                  </object>
                  <a
                    href={`/api/invoices/${active.id}/document`}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-accent-ink"
                  >
                    Open full screen
                    <ArrowUpRight size={12} />
                  </a>
                </div>
              )}

              {/* reject sheet */}
              {sheet === "reject" && (
                <div className="mt-4 rounded-2xl border border-danger/30 bg-danger-soft/40 p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-ink">
                      Send back for review
                    </p>
                    <button
                      type="button"
                      aria-label="Close"
                      onClick={() => setSheet("none")}
                      className="rounded-lg p-1 text-ink-muted hover:text-ink"
                    >
                      <X size={16} />
                    </button>
                  </div>
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    rows={2}
                    placeholder="Why is this coming back? e.g. Amount doesn't match the PO"
                    className="mt-3 w-full rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-sm font-semibold text-ink outline-none focus:border-danger"
                  />
                  {actionError && (
                    <p className="mt-2 text-xs font-medium text-danger">
                      {actionError}
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reject(active)}
                    className="mt-3 inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-danger-button text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {busy ? (
                      <LoaderCircle size={16} className="animate-spin" />
                    ) : (
                      <Undo2 size={16} />
                    )}
                    Send back with reason
                  </button>
                  <p className="mt-2 text-xs font-semibold text-ink-muted">
                    The invoice returns to Needs review with your note attached.
                  </p>
                </div>
              )}

              {/* quick-fix sheet */}
              {sheet === "fix" && (
                <div className="mt-4 rounded-2xl border border-gold-ink/30 bg-gold-soft/40 p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-ink">Quick fix</p>
                    <button
                      type="button"
                      aria-label="Close"
                      onClick={() => setSheet("none")}
                      className="rounded-lg p-1 text-ink-muted hover:text-ink"
                    >
                      <X size={16} />
                    </button>
                  </div>
                  <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    Invoice number
                    <input
                      value={fixNumber}
                      onChange={(event) => setFixNumber(event.target.value)}
                      className="mt-1 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink outline-none focus:border-gold-ink"
                    />
                  </label>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Total
                      <input
                        value={fixTotal}
                        onChange={(event) => setFixTotal(event.target.value)}
                        inputMode="decimal"
                        className="mt-1 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 font-mono text-sm font-medium text-ink outline-none focus:border-gold-ink"
                      />
                    </label>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Date
                      <input
                        type="date"
                        value={fixDate}
                        onChange={(event) => setFixDate(event.target.value)}
                        className="mt-1 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink outline-none focus:border-gold-ink"
                      />
                    </label>
                  </div>
                  {actionError && (
                    <p className="mt-2 text-xs font-medium text-danger">
                      {actionError}
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void applyFix(active)}
                    className="mt-3 inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gold-ink text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {busy ? (
                      <LoaderCircle size={16} className="animate-spin" />
                    ) : (
                      <Wrench size={16} />
                    )}
                    Save fix &amp; revalidate
                  </button>
                  <Link
                    href={`/app/invoices?invoice=${active.id}&mode=review`}
                    className="mt-2 block text-center text-xs font-semibold text-accent-ink"
                  >
                    Need more? Open the full Review Workspace →
                  </Link>
                </div>
              )}
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
                      <p className="truncate text-xs font-semibold uppercase tracking-wide text-ink-muted">
                        {invoice.supplier.name || "Supplier"} · #
                        {invoice.invoice_number || "—"}
                      </p>
                      <p className="font-mono text-lg font-semibold text-ink">
                        {formatCurrency(invoice.total, invoice.currency)}
                      </p>
                    </div>
                    <span className="text-xs font-medium text-ink-muted">
                      waiting
                    </span>
                  </div>
                ))}
                {queue.length > 4 && (
                  <p className="text-center text-xs font-medium text-ink-muted">
                    +{queue.length - 4} more in the queue
                  </p>
                )}
              </div>
            )}

            <p className="mt-5 text-center text-xs font-semibold text-ink-muted">
              Every decision is recorded in History. Rejections land in Needs
              review with your reason attached.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
