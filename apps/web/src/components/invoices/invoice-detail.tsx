"use client";

import {
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  FileSearch,
  Lightbulb,
  LoaderCircle,
  PencilLine,
  Plus,
  RotateCcw,
  Save,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import type {
  ApiErrorPayload,
  ClientProfile,
  Invoice,
  InvoiceLine,
  InvoicePatch,
  InvoiceReviewField,
  InvoiceReviewResult,
  InvoiceReviewSeverity,
  InvoiceStatus,
  PostingResult,
  PostingTarget,
  ValidationResult,
} from "@/lib/types";
import { apiErrorMessage, cn, formatCurrency, formatDate } from "@/lib/utils";

type InvoiceDetailPanelProps = {
  invoice: Invoice | null;
  targetSystem?: string;
  clientProfile?: ClientProfile | null;
  mode?: "detail" | "review";
  onOpenReview?: () => void;
  onCloseReview?: () => void;
  onPostingComplete?: (result: PostingResult) => void;
  onInvoiceUpdate?: (invoice: Invoice) => void;
  onInvoicePatch?: (invoiceId: string, patch: Partial<Invoice>) => void;
};

export function InvoiceDetailPanel({
  invoice,
  targetSystem = "QuickBooks",
  clientProfile = null,
  mode = "detail",
  onOpenReview,
  onCloseReview,
  onPostingComplete,
  onInvoiceUpdate,
  onInvoicePatch,
}: InvoiceDetailPanelProps) {
  return (
    <div className="min-w-0 bg-canvas">
      {invoice ? (
        <InvoiceDetail
          key={[
            invoice.id,
            invoice.updated_at,
            targetSystem,
            clientProfile?.id ?? "no-profile",
            clientProfile?.updated_at ?? "no-profile-update",
            mode,
          ].join(":")}
          invoice={invoice}
          targetSystem={targetSystem}
          clientProfile={clientProfile}
          mode={mode}
          onOpenReview={onOpenReview}
          onCloseReview={onCloseReview}
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
  mode,
  onOpenReview,
  onCloseReview,
  onPostingComplete,
  onInvoiceUpdate,
  onInvoicePatch,
}: {
  invoice: Invoice;
  targetSystem: string;
  clientProfile: ClientProfile | null;
  mode: "detail" | "review";
  onOpenReview?: () => void;
  onCloseReview?: () => void;
  onPostingComplete?: (result: PostingResult) => void;
  onInvoiceUpdate?: (invoice: Invoice) => void;
  onInvoicePatch?: (invoiceId: string, patch: Partial<Invoice>) => void;
}) {
  const confidence =
    invoice.confidence == null ? null : Math.round(invoice.confidence * 100);
  const isPreviewOnly = !invoice.source_path || invoice.id.startsWith("preview-");
  const postingTarget = useMemo(
    () => postingTargetForSystem(targetSystem),
    [targetSystem],
  );
  const resolvedPostingTarget = clientProfile
    ? postingTargetForAccountingSystem(clientProfile.accounting_system)
    : postingTarget;
  const reviewAccountingSystem =
    clientProfile?.accounting_system ??
    accountingSystemForPostingTarget(resolvedPostingTarget);
  const localReview = useMemo(
    () => buildLocalReview(invoice, clientProfile),
    [invoice, clientProfile],
  );
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
  const [review, setReview] = useState<InvoiceReviewResult | null>(() =>
    localReview,
  );
  const [reviewLoading, setReviewLoading] = useState(false);

  useEffect(() => {
    if (isPreviewOnly) return;

    const controller = new AbortController();
    const query = reviewAccountingSystem
      ? `?accounting_system=${encodeURIComponent(reviewAccountingSystem)}`
      : "";

    async function loadReview() {
      setReviewLoading(true);
      try {
        const response = await fetch(`/api/invoices/${invoice.id}/review${query}`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) return;
        setReview((await response.json()) as InvoiceReviewResult);
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setReview(localReview);
        }
      } finally {
        setReviewLoading(false);
      }
    }

    void loadReview();
    return () => controller.abort();
  }, [
    invoice.id,
    isPreviewOnly,
    localReview,
    reviewAccountingSystem,
  ]);

  useEffect(() => {
    if (isPreviewOnly) return;
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
  }, [invoice.id, isPreviewOnly]);

  const canPost =
    !isPreviewOnly &&
    resolvedPostingTarget !== null &&
    ["validated", "approved", "failed"].includes(invoice.status);
  const canValidate =
    !isPreviewOnly && !["posting", "posted"].includes(invoice.status);
  const canApprove = !isPreviewOnly && invoice.status === "validated";

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
          apiErrorMessage(payload as ApiErrorPayload, "Validation failed."),
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
          apiErrorMessage(payload as ApiErrorPayload, "Approval failed."),
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
          apiErrorMessage(payload as ApiErrorPayload, "Posting failed."),
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
          apiErrorMessage(payload as ApiErrorPayload, "Retry failed."),
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
          apiErrorMessage(
            payload as ApiErrorPayload,
            "Could not save corrections.",
          ),
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

  if (mode === "review") {
    return (
      <article className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-8">
        <div className="mb-5 flex flex-col gap-4 rounded-2xl border border-line bg-surface px-5 py-5 shadow-sm shadow-black/[0.03] sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-ink-muted">
              Review workspace
            </p>
            <h2 className="mt-2 break-words text-2xl font-black leading-tight text-ink sm:text-3xl">
              {invoice.invoice_number || "Number pending"}
            </h2>
            <p className="mt-1 max-w-[760px] break-words text-sm font-bold leading-6 text-ink-secondary">
              {invoice.supplier.name || "Supplier pending"}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <StatusBadge status={invoice.status} />
            {confidence != null && (
              <span className="inline-flex h-9 items-center rounded-full border border-line-strong bg-canvas px-3 text-xs font-extrabold text-ink-secondary">
                {confidence}% confidence
              </span>
            )}
            <button
              type="button"
              onClick={onCloseReview}
              className="inline-flex h-10 items-center justify-center rounded-xl border border-line-strong bg-canvas px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
            >
              Back to invoice
            </button>
          </div>
        </div>

        <ReviewWorkspace
          invoice={invoice}
          clientProfile={clientProfile}
          review={review}
          reviewLoading={reviewLoading}
          draft={reviewDraft}
          saving={savingReview}
          notice={reviewNotice}
          previewOnly={isPreviewOnly}
          onDraftChange={setReviewDraft}
          onSave={() => void saveInvoiceCorrections()}
        />
      </article>
    );
  }

  return (
    <article className="mx-auto w-full max-w-[1240px] px-4 py-7 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-5 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-ink-muted">
            Invoice
          </p>
          <h2 className="mt-4 break-words text-3xl font-black leading-tight text-ink sm:text-4xl">
            {invoice.invoice_number || "Number pending"}
          </h2>
          <p className="mt-3 max-w-[760px] break-words text-base font-bold leading-6 text-ink-secondary">
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

      <div className="grid gap-3 border-t border-line pt-6 sm:grid-cols-2 2xl:grid-cols-4">
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

      <ReviewSummaryCard
        review={review}
        reviewLoading={reviewLoading}
        clientProfile={clientProfile}
        onOpenReview={onOpenReview}
      />

      <div className="mt-6 grid gap-3 border-t border-line pt-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        <button
          type="button"
          disabled={!canValidate || validating}
          onClick={() => void validateInvoice()}
          className={cn(
            "inline-flex h-11 min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl border px-4 text-sm font-black transition-colors",
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
            "inline-flex h-11 min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl border px-4 text-sm font-black transition-colors",
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
          className="h-11 min-w-0 whitespace-nowrap rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
        >
          Parsed JSON
        </button>
        <button
          type="button"
          onClick={() => downloadInvoiceJson(invoice, "accounting")}
          className="h-11 min-w-0 whitespace-nowrap rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
        >
          Accounting JSON
        </button>
        <button
          type="button"
          disabled={!canPost || posting}
          onClick={() => void postInvoice()}
          className={cn(
            "inline-flex h-11 min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl border px-4 text-sm font-black transition-colors",
            canPost
              ? "border-accent bg-accent text-white hover:bg-accent-strong"
              : "border-line bg-surface text-ink-muted disabled:cursor-not-allowed disabled:opacity-60",
          )}
          title={
            isPreviewOnly
              ? "Preview-only invoices are not saved to the queue."
              : resolvedPostingTarget
                ? "Invoice must be validated before posting."
                : "Posting is available for QuickBooks, Tally, and Zoho Books."
          }
        >
          {posting ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <SendHorizontal size={16} />
          )}
          <span className="truncate">
            {posting ? "Posting" : `Post to ${targetSystem}`}
          </span>
        </button>
      </div>

      {workflowError && (
        <div className="mt-4 flex gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <span>{workflowError}</span>
        </div>
      )}

      {isPreviewOnly && (
        <div className="mt-4 flex gap-3 rounded-xl border border-cyan/25 bg-cyan-soft px-4 py-3 text-sm font-semibold text-cyan">
          <FileSearch size={18} className="mt-0.5 shrink-0" />
          <span>
            Preview only. This invoice was parsed for demo review and was not
            saved to the queue or backend database.
          </span>
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

      <div className="mt-6 overflow-hidden rounded-xl border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] table-fixed border-collapse text-left">
            <thead className="bg-surface-subtle">
              <tr className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-ink-muted">
                <th className="w-[34%] px-4 py-3">Description</th>
                <th className="w-[12%] px-4 py-3 text-right">Quantity</th>
                <th className="w-[8%] px-4 py-3">UOM</th>
                <th className="w-[16%] px-4 py-3 text-right">Unit price</th>
                <th className="w-[16%] px-4 py-3 text-right">Amount</th>
                <th className="w-[14%] px-4 py-3">Category</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.length ? (
                invoice.lines.map((line) => (
                  <tr
                    key={line.id ?? line.line_number}
                    className="border-t border-line text-sm text-ink"
                  >
                    <td className="px-4 py-4 font-bold leading-5">
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

function ReviewSummaryCard({
  review,
  reviewLoading,
  clientProfile,
  onOpenReview,
}: {
  review: InvoiceReviewResult | null;
  reviewLoading: boolean;
  clientProfile: ClientProfile | null;
  onOpenReview?: () => void;
}) {
  const score = review ? Math.round(review.overall_score * 100) : null;
  const needsAttention = review?.needs_attention ?? 0;
  const profileLabel = clientProfile?.name ?? "No client profile selected";

  return (
    <section className="mt-6 rounded-2xl border border-line bg-surface px-4 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink dark:text-cyan">
            {reviewLoading ? (
              <LoaderCircle size={18} className="animate-spin" />
            ) : (
              <PencilLine size={18} />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-black text-ink">Extraction review</p>
            <p className="mt-1 max-w-3xl text-sm leading-5 text-ink-secondary">
              Use the dedicated review page for PDF comparison, evidence focus,
              field corrections, and profile-aware recommendations.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <ReviewSummaryPill
                label="Score"
                value={score == null ? "Checking" : `${score}/100`}
              />
              <ReviewSummaryPill
                label="Attention"
                value={needsAttention ? `${needsAttention} fields` : "Clean"}
              />
              <ReviewSummaryPill label="Profile" value={profileLabel} />
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenReview}
          className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl border border-accent bg-accent px-4 text-sm font-black text-white transition-colors hover:bg-accent-strong"
        >
          <FileSearch size={16} />
          Review extraction
        </button>
      </div>
    </section>
  );
}

function ReviewSummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-canvas px-3 py-1 text-xs font-bold text-ink-secondary">
      <span className="font-extrabold uppercase tracking-[0.08em] text-ink-muted">
        {label}
      </span>
      <span className="truncate font-black text-ink">{value}</span>
    </span>
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

function accountingSystemForPostingTarget(target: PostingTarget | null) {
  if (target === "tally") return "tally";
  if (target === "zoho_books") return "zoho_books";
  if (target === "quickbooks") return "quickbooks";
  return "";
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
  lines: ReviewLineDraft[];
};

type ReviewLineDraft = {
  key: string;
  line_number: string;
  description: string;
  quantity: string;
  uom: string;
  unit_price: string;
  net_amount: string;
  tax_amount: string;
  total_amount: string;
  hsn_sac: string;
  category: string;
  gl_code: string;
  removed: boolean;
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
    lines: lineDraftsFromInvoice(invoice.lines),
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

function lineDraftsFromInvoice(lines: InvoiceLine[]): ReviewLineDraft[] {
  return lines.map((line, index) => ({
    key: line.id ?? `line-${line.line_number || index + 1}`,
    line_number: String(line.line_number || index + 1),
    description: line.description ?? "",
    quantity: amountDraft(line.quantity),
    uom: line.uom ?? "",
    unit_price: amountDraft(line.unit_price),
    net_amount: amountDraft(line.net_amount),
    tax_amount: amountDraft(line.tax_amount),
    total_amount: amountDraft(line.total_amount),
    hsn_sac: line.hsn_sac ?? "",
    category: line.category ?? "",
    gl_code: line.gl_code ?? "",
    removed: false,
  }));
}

function blankLineDraft(nextLineNumber: number): ReviewLineDraft {
  return {
    key: `new-line-${Date.now()}-${nextLineNumber}`,
    line_number: String(nextLineNumber),
    description: "",
    quantity: "1",
    uom: "",
    unit_price: "0",
    net_amount: "0",
    tax_amount: "0",
    total_amount: "0",
    hsn_sac: "",
    category: "",
    gl_code: "",
    removed: false,
  };
}

function invoicePatchFromReviewDraft(
  invoice: Invoice,
  draft: ReviewDraft,
): InvoicePatch {
  const originalLinesByKey = new Map(
    invoice.lines.map((line, index) => [
      line.id ?? `line-${line.line_number || index + 1}`,
      line,
    ]),
  );
  const lines = draft.lines
    .filter((line) => !line.removed)
    .map((line, index): InvoiceLine => {
      const original = originalLinesByKey.get(line.key);
      return {
        id: original?.id,
        line_number: index + 1,
        description: line.description.trim(),
        quantity: amountFromDraft(line.quantity, original?.quantity ?? 0),
        uom: line.uom.trim(),
        unit_price: amountFromDraft(line.unit_price, original?.unit_price ?? 0),
        net_amount: amountFromDraft(line.net_amount, original?.net_amount ?? 0),
        tax_amount: amountFromDraft(line.tax_amount, original?.tax_amount ?? 0),
        total_amount: amountFromDraft(
          line.total_amount,
          original?.total_amount ?? original?.net_amount ?? 0,
        ),
        hsn_sac: line.hsn_sac.trim(),
        category: line.category.trim(),
        gl_code: line.gl_code.trim(),
        confidence: original?.confidence ?? null,
      };
    });

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
    lines,
  };
}

function defaultReviewFieldPath(reviewFields: InvoiceReviewField[]) {
  return (
    reviewFields.find((field) => field.severity !== "ok")?.field_path ??
    reviewFields[0]?.field_path ??
    ""
  );
}

function ReviewWorkspace({
  invoice,
  clientProfile,
  review,
  reviewLoading,
  draft,
  saving,
  notice,
  previewOnly,
  onDraftChange,
  onSave,
}: {
  invoice: Invoice;
  clientProfile: ClientProfile | null;
  review: InvoiceReviewResult | null;
  reviewLoading: boolean;
  draft: ReviewDraft;
  saving: boolean;
  notice: string;
  previewOnly: boolean;
  onDraftChange: (draft: ReviewDraft) => void;
  onSave: () => void;
}) {
  function updateDraft<Key extends keyof ReviewDraft>(
    key: Key,
    value: ReviewDraft[Key],
  ) {
    onDraftChange({ ...draft, [key]: value });
  }

  function updateLineDraft<Key extends keyof ReviewLineDraft>(
    index: number,
    key: Key,
    value: ReviewLineDraft[Key],
  ) {
    onDraftChange({
      ...draft,
      lines: draft.lines.map((line, lineIndex) =>
        lineIndex === index ? { ...line, [key]: value } : line,
      ),
    });
  }

  function toggleLineRemoved(index: number) {
    onDraftChange({
      ...draft,
      lines: draft.lines.map((line, lineIndex) =>
        lineIndex === index ? { ...line, removed: !line.removed } : line,
      ),
    });
  }

  function addLineDraft() {
    onDraftChange({
      ...draft,
      lines: [...draft.lines, blankLineDraft(draft.lines.length + 1)],
    });
  }

  const reviewFields = useMemo(() => review?.fields ?? [], [review]);
  const reviewFieldSignature = useMemo(
    () =>
      reviewFields
        .map((field) => `${field.field_path}:${field.severity}:${field.value}`)
        .join("|"),
    [reviewFields],
  );
  const [activeFieldState, setActiveFieldState] = useState(() => ({
    signature: reviewFieldSignature,
    path: defaultReviewFieldPath(reviewFields),
  }));
  const activeFieldPath = useMemo(() => {
    if (!reviewFields.length) return "";
    if (
      activeFieldState.signature === reviewFieldSignature &&
      reviewFields.some((field) => field.field_path === activeFieldState.path)
    ) {
      return activeFieldState.path;
    }
    return defaultReviewFieldPath(reviewFields);
  }, [activeFieldState, reviewFieldSignature, reviewFields]);
  const selectActiveFieldPath = (path: string) =>
    setActiveFieldState({ signature: reviewFieldSignature, path });

  const fieldReviewMap = useMemo(
    () => new Map(reviewFields.map((field) => [field.field_path, field])),
    [reviewFields],
  );
  const activeField =
    reviewFields.find((field) => field.field_path === activeFieldPath) ??
    reviewFields.find((field) => field.severity !== "ok") ??
    reviewFields[0] ??
    null;
  const lineFieldReview = fieldReviewMap.get("lines");
  const activePage =
    activeField?.evidence.find((item) => item.page && item.page > 0)?.page ?? 1;
  const pdfUrl =
    !previewOnly && invoice.id
      ? `/api/invoices/${invoice.id}/document#page=${activePage}&zoom=page-width`
      : "";

  function applySuggestedPatch() {
    if (!review?.suggested_patch) return;
    const nextDraft = { ...draft };
    for (const [fieldPath, value] of Object.entries(review.suggested_patch)) {
      const text = String(value ?? "");
      if (fieldPath === "supplier.name") nextDraft.supplier_name = text;
      if (fieldPath === "invoice_number") nextDraft.invoice_number = text;
      if (fieldPath === "invoice_date") nextDraft.invoice_date = text;
      if (fieldPath === "due_date") nextDraft.due_date = text;
      if (fieldPath === "purchase_order") nextDraft.purchase_order = text;
      if (fieldPath === "currency") nextDraft.currency = text.toUpperCase();
      if (fieldPath === "subtotal") nextDraft.subtotal = text;
      if (fieldPath === "tax_total") nextDraft.tax_total = text;
      if (fieldPath === "total") nextDraft.total = text;
      if (fieldPath === "direction") nextDraft.direction = text;
    }
    onDraftChange(nextDraft);
  }

  const selectedProfileLabel = clientProfile
    ? `${clientProfile.name} · ${clientProfile.settings.country_code || "US"} · ${
        clientProfile.settings.default_currency || "USD"
      }`
    : "No client profile selected";
  const reviewScore = review ? Math.round(review.overall_score * 100) : null;
  const attentionCount = review?.needs_attention ?? 0;
  const scoreSeverity: InvoiceReviewSeverity =
    attentionCount === 0 && (reviewScore ?? 0) >= 82
      ? "ok"
      : (reviewScore ?? 0) >= 62
        ? "review"
        : "error";

  return (
    <section className="space-y-5">
      <div className="rounded-3xl border border-line bg-surface px-5 py-4 shadow-sm shadow-black/[0.03]">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-accent-soft text-accent-ink dark:bg-cyan-soft dark:text-cyan">
                <PencilLine size={18} />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-ink-muted">
                  AI invoice review
                </p>
                <h2 className="mt-0.5 text-2xl font-black tracking-tight text-ink">
                  Source, fields, and corrections
                </h2>
              </div>
            </div>
            <p className="mt-3 max-w-4xl text-sm font-semibold leading-6 text-ink-secondary">
              Compare the source PDF with extracted fields, clean line items,
              and save accountant corrections before validation and posting.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 xl:min-w-[520px]">
            <ReviewWorkspaceStat
              label="Review score"
              value={reviewScore == null ? "Pending" : `${reviewScore}/100`}
              tone={scoreSeverity}
            />
            <ReviewWorkspaceStat
              label="Needs attention"
              value={String(attentionCount)}
              tone={attentionCount ? "review" : "ok"}
            />
            <ReviewWorkspaceStat
              label="Profile"
              value={clientProfile?.name ?? "Not selected"}
              tone={clientProfile ? "ok" : "review"}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(330px,0.82fr)_minmax(560px,1.18fr)] 2xl:grid-cols-[minmax(330px,0.72fr)_minmax(560px,1fr)_minmax(300px,0.7fr)]">
        <div className="min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-black/[0.03]">
          <div className="flex items-center justify-between gap-3 pb-4">
            <div className="min-w-0">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                Source document
              </p>
              <p className="mt-1 truncate text-sm font-black text-ink">
                {invoice.source_file}
              </p>
              <p className="mt-0.5 text-xs font-bold text-ink-muted">
                {invoice.parser} · {invoice.extraction_engine} ·{" "}
                {invoice.page_count || 1} page
              </p>
            </div>
            {!previewOnly && (
              <a
                href={`/api/invoices/${invoice.id}/document`}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded-lg border border-line-strong bg-canvas px-3 py-2 text-xs font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
              >
                Open PDF
              </a>
            )}
          </div>
          <ReviewEvidenceFocus field={activeField} page={activePage} />
          {previewOnly ? (
            <div className="grid h-[620px] place-items-center rounded-xl border border-dashed border-line-strong bg-surface-subtle px-6 text-center">
              <div>
                <FileSearch className="mx-auto text-ink-muted" size={28} />
                <p className="mt-3 text-sm font-black text-ink">
                  PDF preview is disabled in demo preview mode.
                </p>
                <p className="mt-1 text-xs font-semibold text-ink-muted">
                  The file was parsed in memory and was not stored on the
                  server.
                </p>
              </div>
            </div>
          ) : (
            <object
              key={pdfUrl}
              data={pdfUrl}
              type="application/pdf"
              className="h-[620px] w-full rounded-xl border border-line bg-surface"
            >
              <div className="grid h-[620px] place-items-center rounded-xl border border-dashed border-line-strong bg-surface-subtle px-6 text-center">
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
          )}
        </div>

        <div className="min-w-0 space-y-5">
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-black/[0.03]">
            <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                  Extracted fields
                </p>
                <p className="mt-1 text-sm font-semibold text-ink-secondary">
                  Click a field to focus the matching evidence.
                </p>
              </div>
              <p className="text-sm font-semibold text-ink-secondary">
                Current total{" "}
                <span className="font-mono font-black text-ink">
                  {formatCurrency(invoice.total, invoice.currency)}
                </span>
              </p>
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <ReviewTextField
                label="Invoice number"
                value={draft.invoice_number}
                fieldReview={fieldReviewMap.get("invoice_number")}
                active={activeFieldPath === "invoice_number"}
                onFocus={() => selectActiveFieldPath("invoice_number")}
                onChange={(value) => updateDraft("invoice_number", value)}
              />
              <ReviewTextField
                label="Supplier"
                value={draft.supplier_name}
                fieldReview={fieldReviewMap.get("supplier.name")}
                active={activeFieldPath === "supplier.name"}
                onFocus={() => selectActiveFieldPath("supplier.name")}
                onChange={(value) => updateDraft("supplier_name", value)}
              />
              <ReviewTextField
                label="Invoice date"
                value={draft.invoice_date}
                fieldReview={fieldReviewMap.get("invoice_date")}
                active={activeFieldPath === "invoice_date"}
                onFocus={() => selectActiveFieldPath("invoice_date")}
                onChange={(value) => updateDraft("invoice_date", value)}
              />
              <ReviewTextField
                label="Due date"
                value={draft.due_date}
                fieldReview={fieldReviewMap.get("due_date")}
                active={activeFieldPath === "due_date"}
                onFocus={() => selectActiveFieldPath("due_date")}
                onChange={(value) => updateDraft("due_date", value)}
              />
              <ReviewTextField
                label="Purchase order"
                value={draft.purchase_order}
                fieldReview={fieldReviewMap.get("purchase_order")}
                active={activeFieldPath === "purchase_order"}
                onFocus={() => selectActiveFieldPath("purchase_order")}
                onChange={(value) => updateDraft("purchase_order", value)}
              />
              <ReviewTextField
                label="Currency"
                value={draft.currency}
                fieldReview={fieldReviewMap.get("currency")}
                active={activeFieldPath === "currency"}
                onFocus={() => selectActiveFieldPath("currency")}
                onChange={(value) =>
                  updateDraft("currency", value.toUpperCase())
                }
              />
              <ReviewTextField
                label="Subtotal"
                value={draft.subtotal}
                active={activeFieldPath === "subtotal"}
                onFocus={() => selectActiveFieldPath("subtotal")}
                onChange={(value) => updateDraft("subtotal", value)}
              />
              <ReviewTextField
                label="Tax total"
                value={draft.tax_total}
                fieldReview={fieldReviewMap.get("tax_total")}
                active={activeFieldPath === "tax_total"}
                onFocus={() => selectActiveFieldPath("tax_total")}
                onChange={(value) => updateDraft("tax_total", value)}
              />
              <ReviewTextField
                label="Total"
                value={draft.total}
                fieldReview={fieldReviewMap.get("total")}
                active={activeFieldPath === "total"}
                onFocus={() => selectActiveFieldPath("total")}
                onChange={(value) => updateDraft("total", value)}
              />
              <ReviewTextField
                label="Direction"
                value={draft.direction}
                active={activeFieldPath === "direction"}
                onFocus={() => selectActiveFieldPath("direction")}
                onChange={(value) => updateDraft("direction", value)}
              />
            </div>
          </div>

          <ReviewLineItemsEditor
            lines={draft.lines}
            currency={draft.currency || invoice.currency}
            fieldReview={lineFieldReview}
            active={activeFieldPath === "lines"}
            onFocus={() => selectActiveFieldPath("lines")}
            onAddLine={addLineDraft}
            onUpdateLine={updateLineDraft}
            onToggleRemoved={toggleLineRemoved}
          />

          <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-black/[0.03]">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm font-semibold text-ink-secondary">
                Save corrected fields to refresh validation and posting payloads.
              </p>
              <button
                type="button"
                disabled={saving || previewOnly}
                onClick={onSave}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-accent bg-accent px-4 text-sm font-black text-white transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
                title={
                  previewOnly
                    ? "Preview-only invoices are not saved to the backend."
                    : "Save corrected extraction fields."
                }
              >
                {saving ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                {previewOnly
                  ? "Preview only"
                  : saving
                    ? "Saving"
                    : "Save corrections"}
              </button>
            </div>

            {notice && (
              <div className="mt-4 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
                {notice}
              </div>
            )}
          </div>
        </div>

        <aside className="min-w-0 space-y-5 xl:col-span-2 2xl:col-span-1">
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-black/[0.03] 2xl:sticky 2xl:top-4">
            <div className="mb-4 rounded-xl border border-line bg-canvas px-4 py-3">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                Posting context
              </p>
              <p className="mt-1 truncate text-sm font-black text-ink">
                {selectedProfileLabel}
              </p>
              <p className="mt-2 text-xs font-bold leading-5 text-ink-secondary">
                Corrections saved here become the source for validation,
                export packages, and ERP posting payloads.
              </p>
            </div>
            <ReviewIntelligencePanel
              review={review}
              loading={reviewLoading}
              activeFieldPath={activeField?.field_path ?? ""}
              onFieldSelect={selectActiveFieldPath}
              onApplySuggestedPatch={applySuggestedPatch}
            />
          </div>
        </aside>
      </div>
    </section>
  );
}

function ReviewWorkspaceStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: InvoiceReviewSeverity;
}) {
  return (
    <div className={cn("min-w-0 rounded-2xl border bg-canvas px-3 py-2.5", severityBorder(tone))}>
      <p className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </p>
      <p className={cn("mt-1 truncate text-sm font-black", severityText(tone))}>
        {value}
      </p>
    </div>
  );
}

function ReviewLineItemsEditor({
  lines,
  currency,
  fieldReview,
  active,
  onFocus,
  onAddLine,
  onUpdateLine,
  onToggleRemoved,
}: {
  lines: ReviewLineDraft[];
  currency: string;
  fieldReview?: InvoiceReviewField;
  active?: boolean;
  onFocus?: () => void;
  onAddLine: () => void;
  onUpdateLine: <Key extends keyof ReviewLineDraft>(
    index: number,
    key: Key,
    value: ReviewLineDraft[Key],
  ) => void;
  onToggleRemoved: (index: number) => void;
}) {
  const activeLines = lines.filter((line) => !line.removed);
  const noisyLines = lines.filter((line) => !line.removed && lineDraftLooksNoisy(line));
  const severity: InvoiceReviewSeverity =
    fieldReview?.severity ?? (noisyLines.length ? "review" : "ok");

  return (
    <div
      className={cn(
        "rounded-2xl border bg-surface p-4 shadow-sm shadow-black/[0.03]",
        active ? "border-accent" : "border-line",
      )}
      onFocus={onFocus}
    >
      <div className="flex flex-col gap-3 border-b border-line pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              Line-item review
            </p>
            <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-black", severityPill(severity))}>
              {activeLines.length} active
            </span>
            {noisyLines.length > 0 && (
              <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-black text-gold">
                {noisyLines.length} need cleanup
              </span>
            )}
          </div>
          <p className="mt-1 text-sm font-semibold leading-6 text-ink-secondary">
            Remove non-item text, correct quantities and taxes, then save the
            cleaned lines into the invoice record.
          </p>
        </div>
        <button
          type="button"
          onClick={onAddLine}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl border border-line-strong bg-canvas px-3 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
        >
          <Plus size={16} />
          Add line
        </button>
      </div>

      {fieldReview?.issue && (
        <div className="mt-4 rounded-xl border border-gold/30 bg-gold-soft px-4 py-3 text-xs font-bold leading-5 text-gold">
          {fieldReview.issue}
          {fieldReview.suggestion ? ` ${fieldReview.suggestion}` : ""}
        </div>
      )}

      <div className="mt-4 overflow-x-auto rounded-xl border border-line">
        <table className="min-w-[1120px] w-full border-collapse text-sm">
          <thead className="bg-surface-subtle text-left">
            <tr className="border-b border-line">
              <th className="px-3 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Description
              </th>
              <th className="w-24 px-3 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Qty
              </th>
              <th className="w-24 px-3 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                UOM
              </th>
              <th className="w-32 px-3 py-3 text-right text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Unit
              </th>
              <th className="w-32 px-3 py-3 text-right text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Net
              </th>
              <th className="w-32 px-3 py-3 text-right text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Tax
              </th>
              <th className="w-32 px-3 py-3 text-right text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Total
              </th>
              <th className="w-36 px-3 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Category
              </th>
              <th className="w-28 px-3 py-3 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line bg-surface">
            {lines.map((line, index) => {
              const noisy = lineDraftLooksNoisy(line);
              return (
                <tr
                  key={line.key}
                  className={cn(
                    "align-top transition-colors",
                    line.removed && "opacity-45",
                    !line.removed && noisy && "bg-gold-soft/35",
                  )}
                >
                  <td className="px-3 py-3">
                    <textarea
                      value={line.description}
                      rows={2}
                      onFocus={onFocus}
                      onChange={(event) =>
                        onUpdateLine(index, "description", event.target.value)
                      }
                      className={cn(
                        "min-h-16 w-full resize-y rounded-lg border bg-canvas px-3 py-2 text-sm font-bold leading-5 text-ink outline-none transition-colors focus:border-accent",
                        noisy ? "border-gold/40" : "border-line-strong",
                      )}
                    />
                    {noisy && !line.removed && (
                      <p className="mt-1 text-[11px] font-bold leading-4 text-gold">
                        Looks like source text, not a purchasable line item.
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.quantity}
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "quantity", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.uom}
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "uom", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.unit_price}
                      align="right"
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "unit_price", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.net_amount}
                      align="right"
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "net_amount", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.tax_amount}
                      align="right"
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "tax_amount", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.total_amount}
                      align="right"
                      onFocus={onFocus}
                      onChange={(value) =>
                        onUpdateLine(index, "total_amount", value)
                      }
                    />
                  </td>
                  <td className="px-3 py-3">
                    <ReviewLineInput
                      value={line.category}
                      onFocus={onFocus}
                      onChange={(value) => onUpdateLine(index, "category", value)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => onToggleRemoved(index)}
                      className={cn(
                        "inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border px-2 text-xs font-black transition-colors",
                        line.removed
                          ? "border-success/30 bg-success-soft text-success hover:bg-canvas"
                          : "border-line-strong bg-canvas text-ink-secondary hover:border-danger hover:text-danger",
                      )}
                    >
                      {line.removed ? (
                        "Restore"
                      ) : (
                        <>
                          <Trash2 size={14} />
                          Remove
                        </>
                      )}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-col gap-2 text-xs font-bold text-ink-muted sm:flex-row sm:items-center sm:justify-between">
        <span>
          {activeLines.length} line{activeLines.length === 1 ? "" : "s"} will be
          saved.
        </span>
        <span>{currency || "USD"} amounts are editable before posting.</span>
      </div>
    </div>
  );
}

function ReviewLineInput({
  value,
  align = "left",
  onFocus,
  onChange,
}: {
  value: string;
  align?: "left" | "right";
  onFocus?: () => void;
  onChange: (value: string) => void;
}) {
  return (
    <input
      value={value}
      onFocus={onFocus}
      onChange={(event) => onChange(event.target.value)}
      className={cn(
        "h-10 w-full rounded-lg border border-line-strong bg-canvas px-2 text-sm font-bold text-ink outline-none transition-colors focus:border-accent",
        align === "right" && "text-right font-mono",
      )}
    />
  );
}

function lineDraftLooksNoisy(line: ReviewLineDraft) {
  return /iban|acct|sort code|customer card|tel:|email|street|suite|invoice|due date|bank|swift|bic|contract|purchase order/i.test(
    line.description,
  );
}

function ReviewIntelligencePanel({
  review,
  loading,
  activeFieldPath,
  onFieldSelect,
  onApplySuggestedPatch,
}: {
  review: InvoiceReviewResult | null;
  loading: boolean;
  activeFieldPath: string;
  onFieldSelect: (fieldPath: string) => void;
  onApplySuggestedPatch: () => void;
}) {
  if (loading && !review) {
    return (
      <div className="grid gap-3 md:grid-cols-[220px_1fr]">
        <div className="h-32 animate-pulse rounded-xl bg-surface-subtle" />
        <div className="h-32 animate-pulse rounded-xl bg-surface-subtle" />
      </div>
    );
  }

  if (!review) {
    return (
      <div className="rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-semibold text-ink-muted">
        Review intelligence will appear after extraction completes.
      </div>
    );
  }

  const score = Math.round(review.overall_score * 100);
  const scoreSeverity: InvoiceReviewSeverity =
    review.needs_attention === 0 && score >= 82
      ? "ok"
      : score >= 62
        ? "review"
        : "error";
  const fieldPreview = [
    ...review.fields.filter((field) => field.severity !== "ok"),
    ...review.fields.filter((field) => field.severity === "ok"),
  ].slice(0, 6);
  const suggestedEntries = Object.entries(review.suggested_patch ?? {});

  return (
    <div className="space-y-3">
      <div className="grid gap-3 2xl:grid-cols-[240px_1fr]">
        <div className="rounded-xl border border-line bg-canvas p-4">
          <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            <Sparkles size={15} className="text-cyan" />
            AI review score
          </div>
          <div className="mt-4 flex items-end gap-2">
            <span className={cn("text-4xl font-black", severityText(scoreSeverity))}>
              {score}
            </span>
            <span className="pb-1 text-sm font-black text-ink-muted">/ 100</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-strong">
            <div
              className={cn("h-full rounded-full", severityBar(scoreSeverity))}
              style={{ width: `${Math.max(4, score)}%` }}
            />
          </div>
          <p className="mt-3 text-xs font-bold leading-5 text-ink-secondary">
            {review.needs_attention
              ? `${review.needs_attention} item${review.needs_attention === 1 ? "" : "s"} need accountant review.`
              : "Core fields look ready for validation."}
          </p>
        </div>

        <div className="grid gap-3 2xl:grid-cols-2">
          <ReviewInsightCard
            title={`${review.detected.country_name} · ${review.detected.currency}`}
            detail={`${review.detected.invoice_format} · ${review.detected.tax_mode}`}
            severity="ok"
            action={
              review.detected.signals.length
                ? review.detected.signals.slice(0, 2).join(" · ")
                : "Format detection is available for profile routing."
            }
          />
          {review.insights.slice(0, 3).map((insight) => (
            <ReviewInsightCard
              key={`${insight.title}-${insight.detail}`}
              title={insight.title}
              detail={insight.detail}
              severity={insight.severity}
              action={insight.action}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-2 2xl:grid-cols-2">
        {fieldPreview.map((field) => (
          <ReviewFieldCard
            key={field.field_path}
            field={field}
            active={activeFieldPath === field.field_path}
            onSelect={() => onFieldSelect(field.field_path)}
          />
        ))}
      </div>

      {suggestedEntries.length > 0 && (
        <div className="rounded-xl border border-cyan/25 bg-cyan-soft px-4 py-3">
          <div className="flex items-start gap-3">
            <Lightbulb className="mt-0.5 shrink-0 text-cyan" size={18} />
            <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-black text-ink">Suggested corrections</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {suggestedEntries.map(([key, value]) => (
                    <span
                      key={key}
                      className="rounded-full border border-cyan/25 bg-surface px-2.5 py-1 text-xs font-black text-ink-secondary"
                    >
                      {key}: {String(value || "blank")}
                    </span>
                  ))}
                </div>
              </div>
              <button
                type="button"
                onClick={onApplySuggestedPatch}
                className="inline-flex h-9 shrink-0 items-center justify-center rounded-lg border border-cyan/30 bg-surface px-3 text-xs font-black text-cyan transition-colors hover:bg-cyan-soft"
              >
                Apply to fields
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewInsightCard({
  title,
  detail,
  severity,
  action,
}: {
  title: string;
  detail: string;
  severity: InvoiceReviewSeverity;
  action: string;
}) {
  return (
    <div className={cn("rounded-xl border bg-canvas p-4", severityBorder(severity))}>
      <div className="flex items-start gap-2">
        <ReviewSeverityIcon severity={severity} />
        <div className="min-w-0">
          <p className="break-words text-sm font-black text-ink">{title}</p>
          <p className="mt-1 break-words text-xs font-bold leading-5 text-ink-secondary">
            {detail}
          </p>
          {action && (
            <p className="mt-2 break-words text-xs font-semibold leading-5 text-ink-muted">
              {action}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewFieldCard({
  field,
  active,
  onSelect,
}: {
  field: InvoiceReviewField;
  active: boolean;
  onSelect: () => void;
}) {
  const confidence =
    field.confidence == null ? "n/a" : `${Math.round(field.confidence * 100)}%`;
  const evidenceSnippet = field.evidence[0]?.snippet || field.evidence[0]?.value || "";
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "rounded-xl border bg-canvas p-3 text-left transition-colors hover:bg-accent-soft",
        severityBorder(field.severity),
        active && "border-accent bg-accent-soft shadow-sm",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
            {field.label}
          </p>
          <p className="mt-1 truncate text-sm font-black text-ink">
            {field.value || "Missing"}
          </p>
        </div>
        <span className={cn("shrink-0 rounded-full px-2 py-1 text-[11px] font-black", severityPill(field.severity))}>
          {confidence}
        </span>
      </div>
      {(field.issue || field.suggestion) && (
        <p className="mt-2 line-clamp-2 text-xs font-semibold leading-5 text-ink-secondary">
          {field.issue || field.suggestion}
        </p>
      )}
      {evidenceSnippet && (
        <p className="mt-2 line-clamp-2 rounded-lg bg-surface-subtle px-2.5 py-2 text-[11px] font-semibold leading-4 text-ink-muted">
          {evidenceSnippet}
        </p>
      )}
    </button>
  );
}

function ReviewSeverityIcon({ severity }: { severity: InvoiceReviewSeverity }) {
  if (severity === "error") {
    return <AlertCircle className="mt-0.5 shrink-0 text-danger" size={17} />;
  }
  if (severity === "review") {
    return <Lightbulb className="mt-0.5 shrink-0 text-gold" size={17} />;
  }
  return <BadgeCheck className="mt-0.5 shrink-0 text-success" size={17} />;
}

function severityText(severity: InvoiceReviewSeverity) {
  if (severity === "error") return "text-danger";
  if (severity === "review") return "text-gold";
  return "text-success";
}

function severityBar(severity: InvoiceReviewSeverity) {
  if (severity === "error") return "bg-danger";
  if (severity === "review") return "bg-gold";
  return "bg-success";
}

function severityBorder(severity: InvoiceReviewSeverity) {
  if (severity === "error") return "border-danger/25";
  if (severity === "review") return "border-gold/30";
  return "border-line";
}

function severityPill(severity: InvoiceReviewSeverity) {
  if (severity === "error") return "bg-danger-soft text-danger";
  if (severity === "review") return "bg-gold-soft text-gold";
  return "bg-success-soft text-success";
}

function ReviewEvidenceFocus({
  field,
  page,
}: {
  field: InvoiceReviewField | null;
  page: number;
}) {
  if (!field) {
    return (
      <div className="mb-3 rounded-xl border border-line bg-surface-subtle px-3 py-3">
        <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-ink-muted">
          Evidence focus
        </p>
        <p className="mt-1 text-sm font-semibold text-ink-secondary">
          Select a review field to see the source evidence.
        </p>
      </div>
    );
  }

  const evidence = field.evidence.slice(0, 3);
  return (
    <div className="mb-3 rounded-xl border border-accent/20 bg-accent-soft px-3 py-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-extrabold uppercase tracking-[0.12em] text-accent-ink">
              Evidence focus
            </span>
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-black", severityPill(field.severity))}>
              {field.severity === "ok" ? "Clean" : field.severity}
            </span>
          </div>
          <p className="mt-1 break-words text-sm font-black text-ink">
            {field.label}: {field.value || "Missing"}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-line-strong bg-canvas px-2.5 py-1 text-xs font-black text-ink-secondary">
          Page {page}
        </span>
      </div>
      {field.issue && (
        <p className="mt-2 text-xs font-bold leading-5 text-ink-secondary">
          {field.issue}
        </p>
      )}
      <div className="mt-3 grid gap-2">
        {evidence.length ? (
          evidence.map((item, index) => (
            <div
              key={`${field.field_path}-${index}-${item.snippet || item.value}`}
              className="rounded-lg border border-line bg-canvas px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-black uppercase tracking-[0.1em] text-ink-muted">
                  Source snippet
                </span>
                <span className="text-[11px] font-black text-ink-muted">
                  {item.confidence == null
                    ? "n/a"
                    : `${Math.round(item.confidence * 100)}%`}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-ink-secondary">
                {item.snippet || item.value}
              </p>
            </div>
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-line-strong bg-canvas px-3 py-2 text-xs font-semibold text-ink-muted">
            No source snippet stored yet. Save a correction to create learning
            evidence for this vendor.
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewTextField({
  label,
  value,
  fieldReview,
  active,
  onFocus,
  onChange,
}: {
  label: string;
  value: string;
  fieldReview?: InvoiceReviewField;
  active?: boolean;
  onFocus?: () => void;
  onChange: (value: string) => void;
}) {
  const severity = fieldReview?.severity ?? "ok";
  const confidence =
    fieldReview?.confidence == null
      ? ""
      : `${Math.round(fieldReview.confidence * 100)}%`;
  return (
    <label
      className={cn(
        "block rounded-xl border p-3 transition-colors",
        active ? "border-accent bg-accent-soft" : "border-line bg-surface",
      )}
    >
      <span className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
          {label}
        </span>
        {fieldReview && (
          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-black", severityPill(severity))}>
            {confidence || (severity === "ok" ? "clean" : severity)}
          </span>
        )}
      </span>
      <input
        value={value}
        onFocus={onFocus}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "mt-2 h-11 w-full rounded-xl border bg-canvas px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent",
          active ? "border-accent" : "border-line-strong",
        )}
      />
      {fieldReview?.suggestion && (
        <p className="mt-2 line-clamp-2 text-[11px] font-semibold leading-4 text-ink-muted">
          {fieldReview.suggestion}
        </p>
      )}
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

function buildLocalReview(
  invoice: Invoice,
  clientProfile: ClientProfile | null,
): InvoiceReviewResult {
  const detected = detectLocalInvoiceProfile(invoice, clientProfile);
  const fields = [
    localField("invoice_number", "Invoice number", invoice.invoice_number, invoice),
    localField("supplier.name", "Supplier", invoice.supplier.name, invoice, {
      suspicious: /tel:|email:|phone:|www\.|@/i,
      issue: "Supplier may include contact text instead of the legal name.",
      suggestion: "Confirm supplier legal name from the invoice header.",
    }),
    localField("invoice_date", "Invoice date", invoice.invoice_date, invoice),
    localField("due_date", "Due date", invoice.due_date, invoice, {
      optional: true,
      issue: "Due date was not found.",
      suggestion: "Use invoice date only for immediate-payment invoices.",
    }),
    localField("currency", "Currency", invoice.currency || "USD", invoice, {
      issue:
        detected.currency !== (invoice.currency || "USD")
          ? `Detected profile suggests ${detected.currency}.`
          : "",
      suggestion:
        detected.currency !== (invoice.currency || "USD")
          ? `Use ${detected.currency} if that is the PDF currency.`
          : "",
    }),
    localAmountField("total", "Total", invoice.total, invoice),
    localAmountField("tax_total", "Tax total", invoice.tax_total, invoice, true),
    localLinesField(invoice),
  ];
  const attention = fields.filter((field) => field.severity !== "ok").length;
  const score = Math.max(
    0,
    Math.min(
      1,
      Math.round(
        ((fields.reduce((sum, field) => sum + (field.confidence ?? 0.5), 0) /
          fields.length) -
          attention * 0.06) *
          100,
      ) / 100,
    ),
  );
  const profileReason = clientProfile
    ? [`Selected profile: ${clientProfile.name}`]
    : ["No profile selected"];

  return {
    invoice_id: invoice.id,
    overall_score: score,
    needs_attention: attention + (clientProfile ? 0 : 1),
    fields,
    insights: [
      {
        title: clientProfile
          ? `Profile selected: ${clientProfile.name}`
          : "No client profile selected",
        detail: clientProfile
          ? `${clientProfile.accounting_system} · ${clientProfile.settings.default_currency}`
          : "Select a client profile before validation and posting.",
        severity: clientProfile ? "ok" : "review",
        action: clientProfile
          ? "Profile settings will control posting rules."
          : "Profiles keep ledgers, taxes, currency, and item mappings consistent.",
      },
      {
        title: attention ? "Review suggested before approval" : "Core fields look ready",
        detail: attention
          ? `${attention} field${attention === 1 ? "" : "s"} need attention.`
          : "No required field issues detected locally.",
        severity: attention ? "review" : "ok",
        action: attention
          ? "Compare the fields with the PDF before validating."
          : "Validate, approve, then post when profile mappings are set.",
      },
    ],
    suggested_patch: suggestedLocalPatch(invoice, detected),
    detected,
    recommended_profile_id: clientProfile?.id ?? null,
    profile_reasons: profileReason,
  };
}

function detectLocalInvoiceProfile(
  invoice: Invoice,
  clientProfile: ClientProfile | null,
) {
  const currency = (invoice.currency || clientProfile?.settings.default_currency || "USD")
    .trim()
    .toUpperCase();
  const hasGst =
    invoice.supplier.tax_id.toUpperCase().includes("GST") ||
    invoice.customer.tax_id.toUpperCase().includes("GST") ||
    invoice.lines.some((line) => line.hsn_sac);
  if (clientProfile) {
    return {
      country_code: clientProfile.settings.country_code || (hasGst ? "IN" : "US"),
      country_name:
        clientProfile.settings.country_name ||
        (hasGst ? "India" : "United States"),
      currency,
      invoice_format: clientProfile.settings.invoice_format || "auto",
      tax_mode: clientProfile.settings.tax_mode || (hasGst ? "gst" : "sales_tax"),
      tax_registration_label: clientProfile.settings.tax_registration_label || "",
      confidence: 0.78,
      signals: ["Client profile selected"],
    };
  }
  return {
    country_code: hasGst || currency === "INR" ? "IN" : "US",
    country_name: hasGst || currency === "INR" ? "India" : "United States",
    currency,
    invoice_format: hasGst ? "gst/e-invoice" : "generic",
    tax_mode: hasGst ? "gst" : "auto",
    tax_registration_label: hasGst ? "GSTIN" : "",
    confidence: hasGst ? 0.7 : 0.45,
    signals: hasGst ? ["GST or HSN/SAC detected"] : ["Generic invoice fallback"],
  };
}

function localField(
  fieldPath: string,
  label: string,
  value: string,
  invoice: Invoice,
  options: {
    optional?: boolean;
    suspicious?: RegExp;
    issue?: string;
    suggestion?: string;
  } = {},
): InvoiceReviewField {
  const clean = value?.trim() ?? "";
  const evidence = (invoice.evidence ?? []).filter(
    (item) => item.field === fieldPath,
  );
  if (!clean && !options.optional) {
    return {
      field_path: fieldPath,
      label,
      value: "",
      confidence: 0.12,
      severity: "error",
      issue: `${label} was not found.`,
      suggestion: `Enter the ${label.toLowerCase()} from the PDF.`,
      evidence,
    };
  }
  if (!clean && options.optional) {
    return {
      field_path: fieldPath,
      label,
      value: "",
      confidence: 0.45,
      severity: "review",
      issue: options.issue ?? `${label} was not found.`,
      suggestion: options.suggestion ?? "Confirm this field against the PDF.",
      evidence,
    };
  }
  const hasSuspiciousValue = options.suspicious?.test(clean) ?? false;
  const hasForcedIssue = Boolean(options.issue && !options.suspicious);
  if (hasSuspiciousValue || hasForcedIssue) {
    return {
      field_path: fieldPath,
      label,
      value: clean,
      confidence: options.issue ? 0.56 : 0.72,
      severity: options.issue ? "review" : "ok",
      issue: options.issue ?? "",
      suggestion: options.suggestion ?? "",
      evidence: evidence.length
        ? evidence
        : localEvidence(fieldPath, clean),
    };
  }
  return {
    field_path: fieldPath,
    label,
    value: clean,
    confidence: evidence[0]?.confidence ?? 0.78,
    severity: "ok",
    issue: "",
    suggestion: "",
    evidence: evidence.length ? evidence : localEvidence(fieldPath, clean),
  };
}

function localAmountField(
  fieldPath: string,
  label: string,
  value: number,
  invoice: Invoice,
  optional = false,
): InvoiceReviewField {
  if (!optional && value <= 0) {
    return {
      field_path: fieldPath,
      label,
      value: formatCurrency(value, invoice.currency),
      confidence: 0.18,
      severity: "error",
      issue: `${label} is missing or zero.`,
      suggestion: "Confirm the payable amount from the invoice totals section.",
      evidence: [],
    };
  }
  return {
    field_path: fieldPath,
    label,
    value: formatCurrency(value, invoice.currency),
    confidence: optional && value === 0 ? 0.58 : 0.78,
    severity: "ok",
    issue: "",
    suggestion: "",
    evidence: localEvidence(fieldPath, formatCurrency(value, invoice.currency)),
  };
}

function localLinesField(invoice: Invoice): InvoiceReviewField {
  const noisy = invoice.lines.filter((line) =>
    /iban|acct|sort code|customer card|tel:|email|street|suite/i.test(
      line.description,
    ),
  );
  return {
    field_path: "lines",
    label: "Line items",
    value: String(invoice.lines.length),
    confidence: noisy.length ? 0.48 : invoice.lines.length ? 0.82 : 0.12,
    severity: !invoice.lines.length ? "error" : noisy.length ? "review" : "ok",
    issue: !invoice.lines.length
      ? "No line items were extracted."
      : noisy.length
        ? `${noisy.length} line item(s) look like non-billable text.`
        : "",
    suggestion: !invoice.lines.length
      ? "Enter line items before posting."
      : noisy.length
        ? "Remove address, bank, date, or footer rows from line items."
        : "",
    evidence: localEvidence("lines", `${invoice.lines.length} extracted`),
  };
}

function localEvidence(field: string, value: string) {
  return [
    {
      field,
      value,
      page: 1,
      snippet: `Parsed value: ${value}`,
      confidence: 0.68,
    },
  ];
}

function suggestedLocalPatch(
  invoice: Invoice,
  detected: ReturnType<typeof detectLocalInvoiceProfile>,
) {
  const patch: Record<string, unknown> = {};
  if ((invoice.currency || "USD").toUpperCase() !== detected.currency) {
    patch.currency = detected.currency;
  }
  if (!invoice.due_date && invoice.invoice_date) patch.due_date = invoice.invoice_date;
  if (!invoice.total && invoice.lines.length) {
    patch.total = invoice.lines.reduce(
      (sum, line) => sum + (line.total_amount || line.net_amount || 0),
      0,
    );
  }
  return patch;
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
    <div className="min-h-[92px] overflow-hidden rounded-xl border border-line bg-surface px-4 py-3.5">
      <p className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
        {label}
      </p>
      <p
        className={cn(
          "mt-3 text-base font-black leading-6 text-ink [overflow-wrap:anywhere]",
          value.length > 28 && "text-sm leading-5",
          mono && "font-mono",
        )}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
