"use client";

import {
  ArrowRight,
  CheckCircle2,
  FileSearch,
  LoaderCircle,
  PartyPopper,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { useAuth } from "@/components/auth-provider";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type { ApiErrorPayload, Invoice } from "@/lib/types";
import { apiErrorMessage, formatCurrency, formatDate } from "@/lib/utils";

function isSiftableInvoice(invoice: Invoice) {
  return (
    invoice.status === "extracted" ||
    invoice.status === "needs_review" ||
    invoice.status === "validated" ||
    invoice.status === "failed" ||
    invoice.validation_issues.length > 0
  );
}

/**
 * Sift mode — UI Spec §7.
 * Full-screen, always-dark triage cockpit: one flagged decision per invoice,
 * one keypress per decision. A approve · E edit (escalates to Review
 * Workspace) · S skip · J/K next/prev · Esc exit.
 */
export default function SiftModePage() {
  const router = useRouter();
  const { activeOrganizationId } = useAuth();
  const { invoices, loading, error } = useWorkspaceInvoices();

  const [queue, setQueue] = useState<Invoice[]>([]);
  const [initialTotal, setInitialTotal] = useState(0);
  const [approvedCount, setApprovedCount] = useState(0);
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [scanKey, setScanKey] = useState(0);
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (!activeOrganizationId || seeded || loading) return;
    const pending = invoices.filter(isSiftableInvoice);
    const timer = window.setTimeout(() => {
      setSeeded(true);
      setQueue(pending);
      setInitialTotal(pending.length);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeOrganizationId, invoices, loading, seeded]);

  const active = queue[0] ?? null;
  const flag = useMemo(() => (active ? flaggedFieldFor(active) : null), [active]);
  const position = Math.min(initialTotal, approvedCount + 1);
  const progressPct = initialTotal
    ? Math.round((approvedCount / initialTotal) * 100)
    : 0;
  const previewOnly =
    !!active && (!active.source_path || active.id.startsWith("preview-"));
  const pdfUrl =
    active && !previewOnly
      ? `/api/invoices/${active.id}/document#page=1&zoom=page-width`
      : "";

  const advance = useCallback(() => {
    setActionError("");
    setScanKey((key) => key + 1);
  }, []);

  const approveCurrent = useCallback(async () => {
    if (!active || busy) return;
    if (previewOnly) {
      setActionError("Preview-only invoice — process a saved upload to approve.");
      return;
    }
    setBusy(true);
    setActionError("");
    try {
      let response = await fetch(`/api/invoices/${active.id}/approve`, {
        method: "POST",
      });
      if (!response.ok) {
        // Some invoices need validation first — run the chain, then retry.
        await fetch(`/api/invoices/${active.id}/validate`, { method: "POST" });
        response = await fetch(`/api/invoices/${active.id}/approve`, {
          method: "POST",
        });
      }
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        throw new Error(
          apiErrorMessage(
            payload,
            "Could not approve — press E to fix it in the Review Workspace.",
          ),
        );
      }
      setApprovedCount((count) => count + 1);
      setQueue((current) => current.slice(1));
      advance();
    } catch (approveError) {
      setActionError((approveError as Error).message);
    } finally {
      setBusy(false);
    }
  }, [active, busy, previewOnly, advance]);

  const skipCurrent = useCallback(() => {
    if (!active || busy || queue.length < 2) {
      if (active && queue.length < 2)
        setActionError("Last invoice in the queue — approve it or press E.");
      return;
    }
    setSkippedIds((ids) => new Set(ids).add(active.id));
    setQueue((current) => [...current.slice(1), current[0]]);
    advance();
  }, [active, busy, queue.length, advance]);

  const rotate = useCallback(
    (direction: 1 | -1) => {
      if (busy || queue.length < 2) return;
      setQueue((current) =>
        direction === 1
          ? [...current.slice(1), current[0]]
          : [
              current[current.length - 1],
              ...current.slice(0, current.length - 1),
            ],
      );
      advance();
    },
    [busy, queue.length, advance],
  );

  const escalateCurrent = useCallback(() => {
    if (!active) return;
    router.push(`/app/invoices?invoice=${active.id}&mode=review`);
  }, [active, router]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const targetTag = (event.target as HTMLElement)?.tagName;
      if (targetTag === "INPUT" || targetTag === "TEXTAREA") return;
      switch (event.key.toLowerCase()) {
        case "a":
        case "enter":
          event.preventDefault();
          void approveCurrent();
          break;
        case "e":
          event.preventDefault();
          escalateCurrent();
          break;
        case "s":
          event.preventDefault();
          skipCurrent();
          break;
        case "j":
          event.preventDefault();
          rotate(1);
          break;
        case "k":
          event.preventDefault();
          rotate(-1);
          break;
        case "escape":
          event.preventDefault();
          router.push("/app/invoices");
          break;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [approveCurrent, escalateCurrent, skipCurrent, rotate, router]);

  const cleared = seeded && !loading && queue.length === 0;

  return (
    <div className="dark min-h-[calc(100vh-64px)] bg-canvas text-ink">
      <main className="mx-auto max-w-[1280px] px-4 py-5 sm:px-6 lg:px-8">
        {/* chrome: mode label · progress · exit */}
        <div className="flex items-center justify-between gap-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan/20 bg-cyan/10 px-3 py-1.5 text-xs font-black uppercase tracking-[0.14em] text-cyan">
            <Sparkles size={14} />
            Sift mode
            <span className="hidden font-bold normal-case tracking-normal text-ink-secondary sm:inline">
              · clearing the review queue
            </span>
          </div>
          <div className="flex items-center gap-3">
            {initialTotal > 0 && !cleared && (
              <span className="font-mono text-sm font-black text-ink-secondary">
                {position} of {initialTotal}
              </span>
            )}
            <Link
              href="/app/invoices"
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 text-sm font-black text-white transition-colors hover:bg-white/10"
              title="Exit Sift mode (Esc)"
            >
              Exit
              <X size={15} />
            </Link>
          </div>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-strong">
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent to-cyan transition-all duration-500"
            style={{ width: `${cleared ? 100 : progressPct}%` }}
          />
        </div>

        {loading ? (
          <div className="mt-6 rounded-3xl border border-line bg-surface p-6">
            <LoadingState label="Preparing sift queue" />
          </div>
        ) : cleared ? (
          <div className="mt-6 grid min-h-[480px] place-items-center rounded-3xl border border-line bg-surface px-6 py-14 text-center shadow-2xl shadow-black/30">
            <div>
              <PartyPopper className="mx-auto text-cyan" size={40} />
              <h1 className="mt-5 text-3xl font-black sm:text-4xl">
                {initialTotal
                  ? "Queue cleared"
                  : "Nothing needs sifting"}
              </h1>
              <p className="mx-auto mt-3 max-w-md text-sm font-semibold leading-6 text-ink-secondary">
                {initialTotal
                  ? `${approvedCount} approved${skippedIds.size ? ` · ${skippedIds.size} skipped into the queue` : ""}. Ready invoices can now be posted from the queue.`
                  : error ||
                    "Upload invoices first — anything flagged for review lands here for fast keyboard triage."}
              </p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
                <Link
                  href="/app/invoices"
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-gradient-to-r from-accent to-cyan px-5 text-sm font-black text-white shadow-lg shadow-indigo-950/40"
                >
                  Back to Invoices
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          </div>
        ) : active && flag ? (
          <div className="mt-6 overflow-hidden rounded-3xl border border-line bg-surface shadow-2xl shadow-black/30">
            <div className="grid gap-0 xl:grid-cols-[minmax(360px,1.05fr)_minmax(420px,0.95fr)]">
              {/* PDF stage */}
              <div className="relative border-b border-line bg-shell p-5 xl:border-b-0 xl:border-r">
                <div className="relative h-[540px] overflow-hidden rounded-2xl border border-line bg-surface">
                  {pdfUrl ? (
                    <object
                      key={pdfUrl}
                      data={pdfUrl}
                      type="application/pdf"
                      className="h-full w-full"
                    >
                      <SiftPdfPlaceholder />
                    </object>
                  ) : (
                    <SiftPdfPlaceholder />
                  )}
                  <span
                    key={`scan-${scanKey}-${active.id}`}
                    aria-hidden
                    className="animate-scanline"
                    style={{ animationIterationCount: 1 }}
                  />
                </div>
                <p className="mt-3 text-center text-[11px] font-bold text-ink-muted">
                  {active.source_file || "Source document"} · page 1
                </p>
              </div>

              {/* decision column */}
              <div className="flex flex-col p-5">
                <div className="rounded-2xl border border-line bg-surface-strong p-5">
                  <p className="text-[11px] font-black uppercase tracking-[0.16em] text-ink-muted">
                    {active.supplier.name || "Supplier pending"} ·{" "}
                    {formatDate(active.invoice_date)}
                  </p>
                  <h1 className="mt-1.5 break-words font-mono text-3xl font-black tracking-tight sm:text-4xl">
                    {formatCurrency(active.total, active.currency)}
                  </h1>
                  <p className="mt-1.5 text-sm font-bold text-ink-secondary">
                    #{active.invoice_number || "Number pending"} ·{" "}
                    {active.lines.length} line
                    {active.lines.length === 1 ? "" : "s"}
                  </p>
                </div>

                <div
                  className={`mt-4 rounded-2xl border p-4 ${
                    flag.tone === "warning"
                      ? "border-gold/30 bg-gold-soft"
                      : "border-cyan/30 bg-cyan/10"
                  }`}
                >
                  <p
                    className={`text-[11px] font-black uppercase tracking-[0.16em] ${
                      flag.tone === "warning" ? "text-gold" : "text-cyan"
                    }`}
                  >
                    {flag.label}
                  </p>
                  <p className="mt-2 break-words text-xl font-black leading-6">
                    {flag.value}
                  </p>
                  <p
                    className={`mt-2.5 text-sm font-semibold leading-6 ${
                      flag.tone === "warning" ? "text-gold" : "text-ink-secondary"
                    }`}
                  >
                    {flag.note}
                  </p>
                </div>

                {actionError && (
                  <div className="mt-3 rounded-xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
                    {actionError}
                  </div>
                )}

                <div className="mt-4 grid gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void approveCurrent()}
                    className="inline-flex h-[52px] items-center justify-center gap-2.5 rounded-xl bg-gradient-to-r from-accent to-cyan text-base font-black text-white shadow-lg shadow-indigo-950/40 transition-transform hover:scale-[1.01] disabled:opacity-60"
                  >
                    {busy ? (
                      <LoaderCircle size={18} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={18} />
                    )}
                    Approve &amp; next
                    <KeyChip>A</KeyChip>
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={escalateCurrent}
                      className="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 text-sm font-black text-white transition-colors hover:bg-white/10"
                    >
                      Edit in Workspace
                      <KeyChip>E</KeyChip>
                    </button>
                    <button
                      type="button"
                      onClick={skipCurrent}
                      className="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 text-sm font-black text-white transition-colors hover:bg-white/10"
                    >
                      Skip
                      <KeyChip>S</KeyChip>
                    </button>
                  </div>
                </div>

                <div className="mt-auto flex flex-wrap items-center justify-center gap-x-5 gap-y-2 pt-6 text-[11px] font-bold text-ink-muted">
                  <span>
                    <KeyChip>A</KeyChip> approve
                  </span>
                  <span>
                    <KeyChip>E</KeyChip> edit
                  </span>
                  <span>
                    <KeyChip>S</KeyChip> skip
                  </span>
                  <span>
                    <KeyChip>J</KeyChip>
                    <KeyChip>K</KeyChip> next / prev
                  </span>
                  <span>
                    <KeyChip>Esc</KeyChip> exit
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-6 rounded-3xl border border-line bg-surface p-6">
            <EmptyState
              icon={FileSearch}
              title="No invoices ready for Sift mode"
              description={
                error ||
                "Upload invoices first, then use Sift mode for fast field triage."
              }
            />
          </div>
        )}
      </main>
    </div>
  );
}

function flaggedFieldFor(invoice: Invoice): {
  label: string;
  value: string;
  note: string;
  tone: "warning" | "clean";
} {
  if (invoice.validation_issues.length) {
    return {
      label: "Validation flag",
      value: invoice.validation_issues[0],
      note: "Fix it in the Workspace (E), or approve if the source PDF confirms the value.",
      tone: "warning",
    };
  }
  const reconciled =
    Math.abs(invoice.subtotal + invoice.tax_total - invoice.total) <= 1;
  if (!reconciled && invoice.total > 0) {
    return {
      label: "Tax reconciliation",
      value: `${formatCurrency(invoice.subtotal, invoice.currency)} + ${formatCurrency(invoice.tax_total, invoice.currency)} ≠ ${formatCurrency(invoice.total, invoice.currency)}`,
      note: "Subtotal + tax doesn't match the invoice total — verify against the PDF.",
      tone: "warning",
    };
  }
  return {
    label: "Total",
    value: formatCurrency(invoice.total, invoice.currency),
    note: "Reconciles ✓ — press A (or Enter) to approve and move on.",
    tone: "clean",
  };
}

function SiftPdfPlaceholder() {
  return (
    <div className="grid h-full place-items-center bg-[radial-gradient(circle_at_50%_20%,rgba(103,232,249,0.14),transparent_36%),linear-gradient(180deg,var(--surface-strong),var(--surface))] p-6 text-center">
      <div>
        <FileSearch className="mx-auto text-ink-muted" size={30} />
        <p className="mt-3 text-sm font-black text-ink">
          PDF preview unavailable
        </p>
        <p className="mt-1 text-xs font-semibold text-ink-muted">
          Preview-only upload or unsupported browser — decide from the
          extracted values, or press E for the full Workspace.
        </p>
      </div>
    </div>
  );
}

function KeyChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="mx-0.5 inline-grid min-w-6 place-items-center rounded-md bg-white/10 px-1.5 py-0.5 font-mono text-[11px] font-black text-cyan">
      {children}
    </span>
  );
}
