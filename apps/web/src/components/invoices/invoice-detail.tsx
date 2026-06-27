"use client";

import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  LoaderCircle,
  PencilLine,
  RotateCcw,
  Save,
  SendHorizontal,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import type {
  ApiErrorPayload,
  ClientProfile,
  Invoice,
  InvoicePatch,
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
          key={invoice.id}
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
  const resolvedPostingTarget = clientProfile
    ? postingTargetForAccountingSystem(clientProfile.accounting_system)
    : postingTarget;
  const [postings, setPostings] = useState<PostingResult[]>([]);
  const [validating, setValidating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [postingError, setPostingError] = useState("");
  const [workflowError, setWorkflowError] = useState("");
  const [reviewDraft, setReviewDraft] = useState<ReviewDraft>(() =>
    reviewDraftFromInvoice(invoice),
  );
  const [savingReview, setSavingReview] = useState(false);
  const [reviewNotice, setReviewNotice] = useState("");

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
    resolvedPostingTarget !== null &&
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
    if (!resolvedPostingTarget) return;
    setPosting(true);
    setPostingError("");
    try {
      const response = await fetch(`/api/invoices/${invoice.id}/post`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: clientProfile?.id ? undefined : resolvedPostingTarget,
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

  async function retryPosting(postingId: string) {
    setRetryingId(postingId);
    setPostingError("");
    try {
      const response = await fetch(`/api/postings/${postingId}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          (payload as ApiErrorPayload).detail ?? "Retry failed.",
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
      setRetryingId(null);
    }
  }

  async function saveInvoiceCorrections() {
    setSavingReview(true);
    setWorkflowError("");
    setReviewNotice("");
    try {
      const patch = invoicePatchFromReviewDraft(invoice, reviewDraft);
      const response = await fetch(`/api/invoices/${invoice.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          (payload as ApiErrorPayload).detail ?? "Could not save corrections.",
        );
      }
      onInvoiceUpdate?.(payload as Invoice);
      setReviewNotice("Corrections saved. Re-validate before posting.");
    } catch (error) {
      setWorkflowError((error as Error).message);
    } finally {
      setSavingReview(false);
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

      <ReviewWorkspace
        invoice={invoice}
        clientProfile={clientProfile}
        draft={reviewDraft}
        saving={savingReview}
        notice={reviewNotice}
        onDraftChange={setReviewDraft}
        onSave={() => void saveInvoiceCorrections()}
      />

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
            resolvedPostingTarget
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

      {postings.length > 0 && (
        <PostingActivity
          postings={postings}
          retryingId={retryingId}
          onRetry={(postingId) => void retryPosting(postingId)}
        />
      )}

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

function postingTargetForAccountingSystem(system: string): PostingTarget | null {
  if (system === "tally") return "tally";
  if (system === "zoho_books") return "zoho_books";
  if (system === "quickbooks") return "quickbooks";
  return null;
}

type ReviewDraft = {
  invoice_number: string;
  supplier_name: string;
  invoice_date: string;
  due_date: string;
  purchase_order: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  total: string;
  direction: string;
};

function reviewDraftFromInvoice(invoice: Invoice): ReviewDraft {
  return {
    invoice_number: invoice.invoice_number ?? "",
    supplier_name: invoice.supplier.name ?? "",
    invoice_date: invoice.invoice_date ?? "",
    due_date: invoice.due_date ?? "",
    purchase_order: invoice.purchase_order ?? "",
    currency: invoice.currency || "USD",
    subtotal: amountDraft(invoice.subtotal),
    tax_total: amountDraft(invoice.tax_total),
    total: amountDraft(invoice.total),
    direction: invoice.direction || "inbound",
  };
}

function amountDraft(value: number) {
  return Number.isFinite(value) ? String(value) : "0";
}

function amountFromDraft(value: string, fallback: number) {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized) return fallback;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function invoicePatchFromReviewDraft(
  invoice: Invoice,
  draft: ReviewDraft,
): InvoicePatch {
  return {
    invoice_number: draft.invoice_number.trim(),
    invoice_date: draft.invoice_date.trim(),
    due_date: draft.due_date.trim(),
    purchase_order: draft.purchase_order.trim(),
    currency: draft.currency.trim().toUpperCase() || "USD",
    subtotal: amountFromDraft(draft.subtotal, invoice.subtotal),
    tax_total: amountFromDraft(draft.tax_total, invoice.tax_total),
    total: amountFromDraft(draft.total, invoice.total),
    direction: draft.direction.trim() || invoice.direction || "inbound",
    supplier: {
      ...invoice.supplier,
      name: draft.supplier_name.trim() || invoice.supplier.name,
    },
  };
}

function ReviewWorkspace({
  invoice,
  clientProfile,
  draft,
  saving,
  notice,
  onDraftChange,
  onSave,
}: {
  invoice: Invoice;
  clientProfile: ClientProfile | null;
  draft: ReviewDraft;
  saving: boolean;
  notice: string;
  onDraftChange: (draft: ReviewDraft) => void;
  onSave: () => void;
}) {
  function updateDraft<Key extends keyof ReviewDraft>(
    key: Key,
    value: ReviewDraft[Key],
  ) {
    onDraftChange({ ...draft, [key]: value });
  }

  const selectedProfileLabel = clientProfile
    ? `${clientProfile.name} · ${clientProfile.settings.country_code || "US"} · ${
        clientProfile.settings.default_currency || "USD"
      }`
    : "No client profile selected";

  return (
    <section className="mt-7 rounded-2xl border border-line bg-surface">
      <div className="flex flex-col gap-3 border-b border-line px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            <PencilLine size={15} className="text-accent dark:text-cyan" />
            Invoice review workspace
          </div>
          <p className="mt-1 text-sm font-semibold text-ink-secondary">
            Compare the source PDF with extracted fields, then save corrections
            before validation and posting.
          </p>
        </div>
        <span className="inline-flex max-w-full items-center rounded-full border border-line-strong bg-canvas px-3 py-1 text-xs font-black text-ink-secondary">
          <span className="truncate">{selectedProfileLabel}</span>
        </span>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(320px,0.9fr)_minmax(420px,1.1fr)]">
        <div className="min-w-0 rounded-xl border border-line bg-canvas p-3">
          <div className="flex items-center justify-between gap-3 px-1 pb-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-black text-ink">
                {invoice.source_file}
              </p>
              <p className="mt-0.5 text-xs font-bold text-ink-muted">
                {invoice.parser} · {invoice.extraction_engine} ·{" "}
                {invoice.page_count || 1} page
              </p>
            </div>
            <a
              href={`/api/invoices/${invoice.id}/document`}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
            >
              Open PDF
            </a>
          </div>
          <object
            data={`/api/invoices/${invoice.id}/document`}
            type="application/pdf"
            className="h-[420px] w-full rounded-lg border border-line bg-surface"
          >
            <div className="grid h-[420px] place-items-center rounded-lg border border-dashed border-line-strong bg-surface-subtle px-6 text-center">
              <div>
                <FileSearch className="mx-auto text-ink-muted" size={28} />
                <p className="mt-3 text-sm font-black text-ink">
                  PDF preview is not available in this browser.
                </p>
                <p className="mt-1 text-xs font-semibold text-ink-muted">
                  Use Open PDF to review the source document.
                </p>
              </div>
            </div>
          </object>
        </div>

        <div className="rounded-xl border border-line bg-canvas p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <ReviewTextField
              label="Invoice number"
              value={draft.invoice_number}
              onChange={(value) => updateDraft("invoice_number", value)}
            />
            <ReviewTextField
              label="Supplier"
              value={draft.supplier_name}
              onChange={(value) => updateDraft("supplier_name", value)}
            />
            <ReviewTextField
              label="Invoice date"
              value={draft.invoice_date}
              onChange={(value) => updateDraft("invoice_date", value)}
            />
            <ReviewTextField
              label="Due date"
              value={draft.due_date}
              onChange={(value) => updateDraft("due_date", value)}
            />
            <ReviewTextField
              label="Purchase order"
              value={draft.purchase_order}
              onChange={(value) => updateDraft("purchase_order", value)}
            />
            <ReviewTextField
              label="Currency"
              value={draft.currency}
              onChange={(value) => updateDraft("currency", value.toUpperCase())}
            />
            <ReviewTextField
              label="Subtotal"
              value={draft.subtotal}
              onChange={(value) => updateDraft("subtotal", value)}
            />
            <ReviewTextField
              label="Tax total"
              value={draft.tax_total}
              onChange={(value) => updateDraft("tax_total", value)}
            />
            <ReviewTextField
              label="Total"
              value={draft.total}
              onChange={(value) => updateDraft("total", value)}
            />
            <ReviewTextField
              label="Direction"
              value={draft.direction}
              onChange={(value) => updateDraft("direction", value)}
            />
          </div>

          <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm font-semibold text-ink-secondary">
              Current total:{" "}
              <span className="font-mono font-black text-ink">
                {formatCurrency(invoice.total, invoice.currency)}
              </span>
            </div>
            <button
              type="button"
              disabled={saving}
              onClick={onSave}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-accent bg-accent px-4 text-sm font-black text-white transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? (
                <LoaderCircle size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}
              {saving ? "Saving" : "Save corrections"}
            </button>
          </div>

          {notice && (
            <div className="mt-4 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
              {notice}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ReviewTextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
      />
    </label>
  );
}

function PostingActivity({
  postings,
  retryingId,
  onRetry,
}: {
  postings: PostingResult[];
  retryingId: string | null;
  onRetry: (postingId: string) => void;
}) {
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
        {postings.slice(0, 5).map((posting) => {
          const profileLabel = postingProfileLabel(posting);
          const retryOf = postingRetryOf(posting);
          const isRetrying = retryingId === posting.id;
          return (
            <div
              key={posting.id}
              className="grid gap-3 px-4 py-3 text-sm lg:grid-cols-[minmax(220px,280px)_1fr_auto] lg:items-center"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-full px-2.5 py-1 text-xs font-black capitalize",
                    posting.status === "succeeded" &&
                      "bg-success-soft text-success",
                    posting.status === "failed" && "bg-danger-soft text-danger",
                    posting.status === "started" && "bg-gold-soft text-gold",
                  )}
                >
                  {posting.dry_run ? "Dry run " : ""}
                  {posting.status}
                </span>
                <span className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs font-black text-ink-secondary">
                  {postingTargetLabel(posting.target)}
                </span>
                {profileLabel && (
                  <span className="max-w-full truncate rounded-full bg-accent-soft px-2.5 py-1 text-xs font-black text-accent-ink">
                    {profileLabel}
                  </span>
                )}
                {retryOf && (
                  <span className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs font-black text-ink-muted">
                    Retry
                  </span>
                )}
              </div>
              <div className="min-w-0">
                <p className="break-words font-semibold text-ink-secondary">
                  {posting.message}
                </p>
                <p className="mt-1 text-xs font-bold text-ink-muted">
                  {posting.external_id
                    ? `External ID ${posting.external_id}`
                    : `Attempt ${posting.id.slice(0, 8)}`}
                  {retryOf ? ` · retry of ${retryOf.slice(0, 8)}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2 lg:justify-end">
                <time className="text-xs font-bold text-ink-muted">
                  {formatTimestamp(posting.updated_at)}
                </time>
                {posting.status === "failed" && (
                  <button
                    type="button"
                    disabled={isRetrying}
                    onClick={() => onRetry(posting.id)}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-2.5 text-xs font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isRetrying ? (
                      <LoaderCircle size={14} className="animate-spin" />
                    ) : (
                      <RotateCcw size={14} />
                    )}
                    Retry
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function postingTargetLabel(target: PostingTarget) {
  if (target === "tally") return "Tally";
  if (target === "zoho_books") return "Zoho";
  return "QuickBooks";
}

function postingProfileLabel(posting: PostingResult) {
  const requestPayload = asRecord(posting.request_payload);
  const directName = stringValue(requestPayload?.client_profile_name);
  if (directName) return directName;

  const postingPlan = asRecord(requestPayload?.posting_plan);
  const profile = asRecord(postingPlan?.profile);
  return stringValue(profile?.name);
}

function postingRetryOf(posting: PostingResult) {
  const requestPayload = asRecord(posting.request_payload);
  return stringValue(requestPayload?.retry_of);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
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
