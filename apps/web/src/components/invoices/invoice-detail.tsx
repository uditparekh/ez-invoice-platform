"use client";

import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  LoaderCircle,
  SendHorizontal,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import type {
  ApiErrorPayload,
  ClientProfile,
  Invoice,
  InvoiceStatus,
  PostingResult,
  PostingTarget,
  ValidationResult,
} from "@/lib/types";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

type InvoiceDetailPanelProps = {
  invoice: Invoice | null;
  targetSystem?: string;
  clientProfile?: ClientProfile | null;
  onPostingComplete?: (result: PostingResult) => void;
  onInvoiceUpdate?: (invoice: Invoice) => void;
  onInvoicePatch?: (invoiceId: string, patch: Partial<Invoice>) => void;
};

export function InvoiceDetailPanel({
  invoice,
  targetSystem = "QuickBooks",
  clientProfile = null,
  onPostingComplete,
  onInvoiceUpdate,
  onInvoicePatch,
}: InvoiceDetailPanelProps) {
  return (
    <div className="min-w-0 bg-canvas">
      {invoice ? (
        <InvoiceDetail
          invoice={invoice}
          targetSystem={targetSystem}
          clientProfile={clientProfile}
          onPostingComplete={onPostingComplete}
          onInvoiceUpdate={onInvoiceUpdate}
          onInvoicePatch={onInvoicePatch}
        />
      ) : (
        <EmptyDetail />
      )}
    </div>
  );
}

function EmptyDetail() {
  return (
    <div className="grid min-h-[560px] place-items-center px-8 text-center">
      <div>
        <FileSearch className="mx-auto text-ink-muted" size={30} />
        <p className="mt-4 text-lg font-black text-ink">Select an invoice</p>
        <p className="mt-2 text-sm text-ink-muted">
          Extracted fields, validation, and line items will appear here.
        </p>
      </div>
    </div>
  );
}

function InvoiceDetail({
  invoice,
  targetSystem,
  clientProfile,
  onPostingComplete,
  onInvoiceUpdate,
  onInvoicePatch,
}: {
  invoice: Invoice;
  targetSystem: string;
  clientProfile: ClientProfile | null;
  onPostingComplete?: (result: PostingResult) => void;
  onInvoiceUpdate?: (invoice: Invoice) => void;
  onInvoicePatch?: (invoiceId: string, patch: Partial<Invoice>) => void;
}) {
  const confidence =
    invoice.confidence == null ? null : Math.round(invoice.confidence * 100);
  const postingTarget = useMemo(
    () => postingTargetForSystem(targetSystem),
    [targetSystem],
  );
  const [postings, setPostings] = useState<PostingResult[]>([]);
  const [validating, setValidating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [postingError, setPostingError] = useState("");
  const [workflowError, setWorkflowError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadPostings() {
      try {
        const response = await fetch(
          `/api/invoices/${invoice.id}/postings?limit=6`,
          {
            signal: controller.signal,
            cache: "no-store",
          },
        );
        if (!response.ok) return;
        setPostings((await response.json()) as PostingResult[]);
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setPostings([]);
        }
      }
    }

    void loadPostings();
    return () => controller.abort();
  }, [invoice.id]);

  const canPost =
    postingTarget !== null &&
    ["validated", "approved", "failed"].includes(invoice.status);
  const canValidate = !["posting", "posted"].includes(invoice.status);
  const canApprove = invoice.status === "validated";

  async function validateInvoice() {
    setValidating(true);
    setWorkflowError("");
    setPostingError("");
    try {
      const response = await fetch(`/api/invoices/${invoice.id}/validate`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          (payload as ApiErrorPayload).detail ?? "Validation failed.",
        );
      }
      const result = payload as ValidationResult;
      onInvoicePatch?.(invoice.id, {
        status: result.status as InvoiceStatus,
        validation_issues: result.issues,
      });
    } catch (error) {
      setWorkflowError((error as Error).message);
    } finally {
      setValidating(false);
    }
  }

  async function approveInvoice() {
    setApproving(true);
    setWorkflowError("");
    setPostingError("");
    try {
      const response = await fetch(`/api/invoices/${invoice.id}/approve`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          (payload as ApiErrorPayload).detail ?? "Approval failed.",
        );
      }
      onInvoiceUpdate?.(payload as Invoice);
    } catch (error) {
      setWorkflowError((error as Error).message);
    } finally {
      setApproving(false);
    }
  }

  async function postInvoice() {
    if (!postingTarget) return;
    setPosting(true);
    setPostingError("");
    try {
      const response = await fetch(`/api/invoices/${invoice.id}/post`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: postingTarget,
          dry_run: false,
          client_profile_id: clientProfile?.id ?? null,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          (payload as ApiErrorPayload).detail ?? "Posting failed.",
        );
      }
      const result = payload as PostingResult;
      setPostings((current) => [
        result,
        ...current.filter((postingAttempt) => postingAttempt.id !== result.id),
      ]);
      onPostingComplete?.(result);
      if (!result.success) {
        onInvoicePatch?.(invoice.id, {
          status: "failed",
          updated_at: result.updated_at,
        });
        setPostingError(result.message);
      }
    } catch (error) {
      setPostingError((error as Error).message);
    } finally {
      setPosting(false);
    }
  }

  return (
    <article className="mx-auto w-full max-w-[1180px] px-4 py-7 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-5 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-ink-muted">
            Invoice
          </p>
          <h2 className="mt-4 break-words text-4xl font-black text-ink">
            {invoice.invoice_number || "Number pending"}
          </h2>
          <p className="mt-3 break-words text-base font-bold text-ink-secondary">
            {invoice.supplier.name || "Supplier pending"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={invoice.status} />
          {confidence != null && (
            <span className="inline-flex h-7 items-center rounded-full border border-line-strong bg-surface px-2.5 text-[11px] font-extrabold text-ink-secondary">
              {confidence}% confidence
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-3 border-t border-line pt-6 sm:grid-cols-2 xl:grid-cols-4">
        <Fact label="Invoice date" value={formatDate(invoice.invoice_date)} />
        <Fact label="Due date" value={formatDate(invoice.due_date)} />
        <Fact label="Currency" value={invoice.currency || "USD"} />
        <Fact
          label="Total"
          value={formatCurrency(invoice.total, invoice.currency)}
          mono
        />
        <Fact
          label="Purchase order"
          value={invoice.purchase_order || "Not provided"}
        />
        <Fact label="Direction" value={invoice.direction || "Inbound"} />
        <Fact label="Line items" value={String(invoice.lines.length)} />
        <Fact label="Source" value={invoice.source_file} />
      </div>

      {invoice.validation_issues.length > 0 && (
        <div className="mt-6 rounded-xl border border-gold/25 bg-gold-soft px-4 py-3">
          <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-gold">
            Review required
          </p>
          <p className="mt-1 text-sm text-ink-secondary">
            {invoice.validation_issues.join(" · ")}
          </p>
        </div>
      )}

      <div className="mt-6 grid gap-3 border-t border-line pt-6 sm:grid-cols-2 xl:grid-cols-5">
        <button
          type="button"
          disabled={!canValidate || validating}
          onClick={() => void validateInvoice()}
          className={cn(
            "inline-flex h-11 items-center justify-center gap-2 rounded-xl border px-4 text-sm font-black transition-colors",
            canValidate
              ? "border-line-strong bg-surface text-ink hover:border-accent hover:bg-accent-soft"
              : "border-line bg-surface text-ink-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {validating ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <CheckCircle2 size={16} />
          )}
          {validating ? "Validating" : "Validate"}
        </button>
        <button
          type="button"
          disabled={!canApprove || approving}
          onClick={() => void approveInvoice()}
          className={cn(
            "inline-flex h-11 items-center justify-center gap-2 rounded-xl border px-4 text-sm font-black transition-colors",
            canApprove
              ? "border-accent/40 bg-accent-soft text-accent-ink hover:border-accent hover:bg-accent/15"
              : "border-line bg-surface text-ink-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
          title="Approve becomes available after validation passes."
        >
          {approving ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <ShieldCheck size={16} />
          )}
          {approving ? "Approving" : "Approve"}
        </button>
        <button
          type="button"
          onClick={() => downloadInvoiceJson(invoice, "parsed")}
          className="h-11 rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
        >
          Parsed JSON
        </button>
        <button
          type="button"
          onClick={() => downloadInvoiceJson(invoice, "accounting")}
          className="h-11 rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
        >
          Accounting JSON
        </button>
        <button
          type="button"
          disabled={!canPost || posting}
          onClick={() => void postInvoice()}
          className={cn(
            "inline-flex h-11 items-center justify-center gap-2 rounded-xl border px-4 text-sm font-black transition-colors",
            canPost
              ? "border-accent bg-accent text-white hover:bg-accent-strong"
              : "border-line bg-surface text-ink-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
          title={
            postingTarget
              ? "Invoice must be validated before posting."
              : "Posting is available for QuickBooks, Tally, and Zoho Books."
          }
        >
          {posting ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <SendHorizontal size={16} />
          )}
          {posting ? "Posting" : `Post to ${targetSystem}`}
        </button>
      </div>

      {workflowError && (
        <div className="mt-4 flex gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <span>{workflowError}</span>
        </div>
      )}

      {postingError && (
        <div className="mt-4 flex gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <span>{postingError}</span>
        </div>
      )}

      {postings.length > 0 && <PostingActivity postings={postings} />}

      <div className="mt-10 flex flex-col gap-3 border-t border-line pt-7 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-2xl font-black text-ink">
            Line items
          </h3>
          <p className="mt-1 text-xs text-ink-muted">
            Extracted purchase detail ready for review and mapping.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-extrabold text-cyan">
          <CheckCircle2 size={16} />
          {invoice.lines.length} extracted
        </div>
      </div>

      <div className="mt-5 overflow-hidden rounded-xl border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead className="bg-surface-subtle">
              <tr className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-ink-muted">
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3 text-right">Quantity</th>
                <th className="px-4 py-3">UOM</th>
                <th className="px-4 py-3 text-right">Unit price</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3">Category</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.length ? (
                invoice.lines.map((line) => (
                  <tr
                    key={line.id ?? line.line_number}
                    className="border-t border-line text-sm text-ink"
                  >
                    <td className="max-w-[360px] px-4 py-4 font-bold">
                      {line.description || "Description pending"}
                    </td>
                    <td className="px-4 py-4 text-right font-mono">
                      {line.quantity.toLocaleString("en-IN")}
                    </td>
                    <td className="px-4 py-4 text-ink-secondary">
                      {line.uom || "—"}
                    </td>
                    <td className="px-4 py-4 text-right font-mono">
                      {formatCurrency(line.unit_price, invoice.currency)}
                    </td>
                    <td className="px-4 py-4 text-right font-mono font-bold">
                      {formatCurrency(
                        line.net_amount ?? line.total_amount,
                        invoice.currency,
                      )}
                    </td>
                    <td className="px-4 py-4 text-ink-secondary">
                      {line.category || "Unmapped"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-sm text-ink-muted"
                  >
                    No line items were extracted.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

function postingTargetForSystem(system: string): PostingTarget | null {
  if (system === "Tally") return "tally";
  if (system === "Zoho Books") return "zoho_books";
  if (system === "QuickBooks") return "quickbooks";
  return null;
}

function PostingActivity({ postings }: { postings: PostingResult[] }) {
  return (
    <section className="mt-6 rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-ink-muted">
            Posting activity
          </p>
          <p className="mt-1 text-sm font-semibold text-ink-secondary">
            Latest ERP attempts and connector responses.
          </p>
        </div>
        <span className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs font-black text-ink-secondary">
          {postings.length}
        </span>
      </div>
      <div className="divide-y divide-line">
        {postings.slice(0, 4).map((posting) => (
          <div
            key={posting.id}
            className="grid gap-2 px-4 py-3 text-sm sm:grid-cols-[160px_1fr_auto] sm:items-center"
          >
            <span
              className={cn(
                "w-fit rounded-full px-2.5 py-1 text-xs font-black capitalize",
                posting.status === "succeeded" &&
                  "bg-success-soft text-success",
                posting.status === "failed" && "bg-danger-soft text-danger",
                posting.status === "started" && "bg-gold-soft text-gold",
              )}
            >
              {posting.dry_run ? "Dry run " : ""}
              {posting.status}
            </span>
            <p className="min-w-0 break-words font-semibold text-ink-secondary">
              {posting.message}
            </p>
            <time className="text-xs font-bold text-ink-muted">
              {formatTimestamp(posting.updated_at)}
            </time>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function downloadInvoiceJson(invoice: Invoice, kind: "parsed" | "accounting") {
  const payload =
    kind === "parsed"
      ? invoice
      : {
          invoice_number: invoice.invoice_number,
          supplier: invoice.supplier,
          invoice_date: invoice.invoice_date,
          due_date: invoice.due_date,
          currency: invoice.currency,
          subtotal: invoice.subtotal,
          tax_total: invoice.tax_total,
          total: invoice.total,
          lines: invoice.lines.map((line) => ({
            description: line.description,
            quantity: line.quantity,
            uom: line.uom,
            unit_price: line.unit_price,
            amount: line.total_amount || line.net_amount,
            category: line.category || "Unmapped",
            gl_code: line.gl_code || "",
          })),
        };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${invoice.invoice_number || "invoice"}_${kind}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Fact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-h-24 rounded-xl border border-line bg-surface px-4 py-3.5">
      <p className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
        {label}
      </p>
      <p
        className={cn(
          "mt-3 break-words text-base font-black text-ink",
          mono && "font-mono",
        )}
      >
        {value}
      </p>
    </div>
  );
}
