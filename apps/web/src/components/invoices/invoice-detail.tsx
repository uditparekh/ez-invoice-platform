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

import { ResizableSplit } from "@/components/review/resizable-split";
import { StatusBadge } from "@/components/status-badge";
import {
  PdfEvidenceViewer,
  hasLocatedEvidence,
} from "@/components/invoices/pdf-evidence-viewer";
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

  async function saveInvoiceCorrections(
    options: { learnVendor: boolean } = { learnVendor: true },
  ) {
    setSavingReview(true);
    setWorkflowError("");
    setReviewNotice("");
    try {
      const patch = invoicePatchFromReviewDraft(invoice, reviewDraft);
      const response = await fetch(`/api/invoices/${invoice.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...patch,
          learn_vendor_memory: options.learnVendor,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          apiErrorMessage(payload as ApiErrorPayload, "Could not save corrections."),
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
      <article className="mx-auto w-full max-w-[1480px] px-4 py-5 sm:px-6 lg:px-8">
        <div className="mb-4 flex flex-col gap-4 border-b border-line pb-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-black text-ink-secondary">
              <button
                type="button"
                onClick={onCloseReview}
                className="text-ink-muted transition-colors hover:text-accent"
              >
                Invoices
              </button>{" "}
              /{" "}
              <span className="text-ink">
                {invoice.supplier.name || "Supplier pending"} ·{" "}
                {invoice.invoice_number || "Number pending"}
              </span>
            </p>
            <h2 className="mt-2 text-2xl font-black leading-tight text-ink sm:text-3xl">
              Review Workspace
            </h2>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2 xl:justify-end">
            <StatusBadge status={invoice.status} />
            {confidence != null && (
              <span className="inline-flex h-9 items-center rounded-full border border-line-strong bg-canvas px-3 text-xs font-extrabold text-ink-secondary">
                {confidence}% confidence
              </span>
            )}
            <button
              type="button"
              disabled={!canValidate || validating}
              onClick={() => void validateInvoice()}
              className={cn(
                "inline-flex h-10 items-center justify-center gap-2 rounded-xl border px-3 text-sm font-black transition-colors",
                canValidate
                  ? "border-line-strong bg-canvas text-ink hover:border-accent hover:bg-accent-soft"
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
                "inline-flex h-10 items-center justify-center gap-2 rounded-xl border px-3 text-sm font-black transition-colors",
                canApprove
                  ? "border-success/30 bg-success-soft text-success hover:border-success"
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
              disabled={!canPost || posting}
              onClick={() => void postInvoice()}
              className={cn(
                "inline-flex h-10 items-center justify-center gap-2 rounded-xl border px-3 text-sm font-black transition-colors",
                canPost
                  ? "border-accent bg-accent text-white shadow-sm shadow-accent/20 hover:bg-accent-strong"
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
              {posting ? "Posting" : `Post to ${targetSystem}`}
            </button>
            <button
              type="button"
              onClick={onCloseReview}
              className="inline-flex h-10 items-center justify-center rounded-xl border border-line-strong bg-canvas px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
            >
              Back to invoice
            </button>
          </div>
        </div>

        {(workflowError || postingError) && (
          <div className="mb-4 flex gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <span>{workflowError || postingError}</span>
          </div>
        )}

        {isPreviewOnly && (
          <div className="mb-4 flex gap-3 rounded-xl border border-cyan/25 bg-cyan-soft px-4 py-3 text-sm font-semibold text-cyan">
            <FileSearch size={18} className="mt-0.5 shrink-0" />
            <span>
              Preview only. This invoice was parsed for demo review and was not
              saved to the backend queue.
            </span>
          </div>
        )}

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
          onSave={(options) => void saveInvoiceCorrections(options)}
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

      <section className="mt-8 rounded-2xl border border-line bg-surface px-4 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              Line items
            </p>
            <h3 className="mt-1 text-xl font-black text-ink">
              {invoice.lines.length} extracted for review and mapping
            </h3>
            <p className="mt-1 max-w-3xl text-sm font-semibold leading-5 text-ink-secondary">
              Review quantities, tax treatment, ledger mapping, and evidence in
              the dedicated workspace before posting.
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenReview}
            className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl border border-line-strong bg-canvas px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
          >
            <FileSearch size={16} />
            Open review workspace
          </button>
        </div>
      </section>
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
  lines: InvoiceLine[];
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
    lines: invoice.lines.map((line) => ({ ...line })),
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
    lines: draft.lines.map((line, index) => ({
      ...line,
      line_number: index + 1,
    })),
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
  onSave: (options: { learnVendor: boolean }) => void;
}) {
  function updateDraft<Key extends keyof ReviewDraft>(
    key: Key,
    value: ReviewDraft[Key],
  ) {
    onDraftChange({ ...draft, [key]: value });
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

  const [learnVendor, setLearnVendor] = useState(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem("siftentry.review.learnVendor");
    return stored == null ? true : stored !== "false";
  });
  function toggleLearnVendor(next: boolean) {
    setLearnVendor(next);
    window.localStorage.setItem("siftentry.review.learnVendor", String(next));
  }
  const vendorShort =
    (invoice.supplier.name || "This vendor").split(/\s+/)[0] || "Vendor";

  const fieldReviewMap = useMemo(
    () => new Map(reviewFields.map((field) => [field.field_path, field])),
    [reviewFields],
  );
  const activeField =
    reviewFields.find((field) => field.field_path === activeFieldPath) ??
    reviewFields.find((field) => field.severity !== "ok") ??
    reviewFields[0] ??
    null;
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
  const needsAttention = review?.needs_attention ?? 0;
  const suggestedCount = Object.keys(review?.suggested_patch ?? {}).length;

  return (
    <section className="space-y-4">
      <div className="rounded-2xl border border-line bg-surface px-4 py-3 shadow-sm shadow-black/[0.03]">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              <PencilLine size={15} className="text-accent dark:text-cyan" />
              Extraction review
            </div>
            <p className="mt-1 max-w-3xl text-sm font-semibold leading-5 text-ink-secondary">
              Click any field to focus the source evidence, apply suggested
              fixes, then save corrections before validation and posting.
            </p>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-2 xl:justify-end">
            <ReviewCommandPill
              label="Score"
              value={reviewLoading && reviewScore == null ? "Checking" : reviewScore == null ? "Pending" : `${reviewScore}%`}
            />
            <ReviewCommandPill
              label="Attention"
              value={needsAttention ? `${needsAttention} fields` : "Clean"}
              tone={needsAttention ? "warning" : "success"}
            />
            <ReviewCommandPill
              label="Profile"
              value={selectedProfileLabel}
              wide
            />
            <ReviewCommandPill
              label="Fixes"
              value={suggestedCount ? `${suggestedCount} suggested` : "None"}
              tone={suggestedCount ? "warning" : "default"}
            />
          </div>
        </div>
      </div>

      <ResizableSplit
        storageKey="siftentry.review.split"
        defaultLeftPct={38}
        minLeftPct={24}
        maxLeftPct={58}
      >
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
            <div className="relative overflow-hidden rounded-xl">
              {review && hasLocatedEvidence(review.fields) ? (
                <PdfEvidenceViewer
                  url={pdfUrl}
                  fields={review?.fields ?? []}
                  activeFieldPath={activeField?.field_path ?? null}
                  fallback={
                    <object
                      data={pdfUrl}
                      type="application/pdf"
                      className="h-[620px] w-full rounded-xl border border-line bg-surface"
                    >
                      <div className="grid h-[620px] place-items-center rounded-xl border border-dashed border-line-strong bg-surface-subtle px-6 text-center">
                        <p className="text-sm font-black text-ink">
                          Use Open PDF to review the source document.
                        </p>
                      </div>
                    </object>
                  }
                />
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
              {activeField && (
                <span
                  key={`scan-${activeField.field_path}`}
                  aria-hidden
                  className="animate-scanline"
                  style={{ animationIterationCount: 1 }}
                />
              )}
              {activeField && (
                <div
                  key={`beacon-${activeField.field_path}`}
                  className="pointer-events-none absolute inset-x-3 bottom-3"
                >
                  <div className="flex items-center gap-2.5 rounded-xl border border-cyan/60 bg-surface/95 px-3 py-2 shadow-pop backdrop-blur">
                    <span className="relative flex size-2.5 shrink-0">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan opacity-60" />
                      <span className="relative inline-flex size-2.5 rounded-full bg-cyan" />
                    </span>
                    <p className="min-w-0 truncate text-xs font-bold text-ink">
                      Evidence · p.{activePage}
                      {activeField.evidence[0]?.snippet ? (
                        <span className="font-semibold text-ink-secondary">
                          {" "}
                          · “{activeField.evidence[0].snippet}”
                        </span>
                      ) : null}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-black/[0.03]">
            <ReviewIntelligencePanel
              review={review}
              loading={reviewLoading}
              activeFieldPath={activeField?.field_path ?? ""}
              onFieldSelect={selectActiveFieldPath}
              onApplySuggestedPatch={applySuggestedPatch}
            />
          </div>

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

            <div className="mt-4 grid gap-3 2xl:grid-cols-2">
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

            <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex max-w-xl cursor-pointer items-start gap-2.5 text-sm font-semibold text-ink-secondary">
                <input
                  type="checkbox"
                  checked={learnVendor}
                  onChange={(event) => toggleLearnVendor(event.target.checked)}
                  className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                />
                <span>
                  Save corrections to vendor memory —{" "}
                  <span className="font-black text-ink">{vendorShort}</span>{" "}
                  learns these fixes for future invoices.
                </span>
              </label>
              <button
                type="button"
                disabled={saving || previewOnly}
                onClick={() => onSave({ learnVendor })}
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

          <ReviewLineItemsPanel
            invoice={invoice}
            lines={draft.lines}
            fieldReview={fieldReviewMap.get("lines")}
            clientProfile={clientProfile}
            editable={!saving && !previewOnly}
            onLinesChange={(lines) => updateDraft("lines", lines)}
          />
        </div>
      </ResizableSplit>
    </section>
  );
}

function ReviewCommandPill({
  label,
  value,
  tone = "default",
  wide = false,
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning";
  wide?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-10 min-w-0 items-center gap-2 rounded-full border px-3 text-xs font-black",
        wide ? "max-w-[320px]" : "max-w-[190px]",
        tone === "success"
          ? "border-success/25 bg-success-soft text-success"
          : tone === "warning"
            ? "border-gold/25 bg-gold-soft text-gold"
            : "border-line bg-canvas text-ink-secondary",
      )}
    >
      <span className="shrink-0 text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </span>
      <span className="truncate text-ink">{value}</span>
    </span>
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
      {fieldReview?.issue && (
        <p className="mt-2 rounded-lg border border-gold/20 bg-gold-soft px-2.5 py-2 text-[11px] font-bold leading-4 text-gold">
          Why review: {fieldReview.issue}
        </p>
      )}
    </label>
  );
}

function ReviewLineItemsPanel({
  invoice,
  lines,
  fieldReview,
  clientProfile,
  editable,
  onLinesChange,
}: {
  invoice: Invoice;
  lines: InvoiceLine[];
  fieldReview?: InvoiceReviewField;
  clientProfile: ClientProfile | null;
  editable: boolean;
  onLinesChange: (lines: InvoiceLine[]) => void;
}) {
  const lineTotal = lines.reduce(
    (sum, line) => sum + (line.net_amount ?? line.total_amount ?? 0),
    0,
  );
  const variance = invoice.total ? invoice.total - lineTotal : 0;
  const suspiciousLines = lines.filter((line) =>
    /iban|acct|sort code|customer card|tel:|email|street|suite|invoice|due date/i.test(
      line.description,
    ),
  );
  const hasVariance = Math.abs(variance) > Math.max(1, invoice.total * 0.03);
  const reviewState =
    fieldReview?.severity === "error" || hasVariance
      ? "error"
      : fieldReview?.severity === "review" || suspiciousLines.length
        ? "review"
        : "ok";

  function updateLine(index: number, patch: Partial<InvoiceLine>) {
    onLinesChange(
      lines.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    );
  }

  function removeLine(index: number) {
    onLinesChange(
      lines
        .filter((_, i) => i !== index)
        .map((line, i) => ({ ...line, line_number: i + 1 })),
    );
  }

  function addLine() {
    onLinesChange([
      ...lines,
      {
        line_number: lines.length + 1,
        description: "",
        quantity: 0,
        uom: "",
        unit_price: 0,
        net_amount: 0,
        tax_amount: 0,
        total_amount: 0,
        hsn_sac: "",
        category: "",
        gl_code: "",
        confidence: null,
      },
    ]);
  }

  return (
    <section className="rounded-2xl border border-line bg-surface shadow-card">
      <div className="flex flex-col gap-3 border-b border-line px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              Line items
            </p>
            <h3 className="mt-1 text-lg font-black text-ink">
              {lines.length} line{lines.length === 1 ? "" : "s"}
              <span className="ml-2 text-sm font-bold text-ink-muted">
                edit inline · rows save with corrections
              </span>
            </h3>
            <p className="mt-1 max-w-2xl text-xs font-semibold leading-5 text-ink-secondary">
              Keep billable goods/services, then confirm each row&apos;s
              profile mapping before posting.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={cn(
                "inline-flex h-8 items-center rounded-full px-3 text-xs font-black",
                reviewState === "ok"
                  ? "bg-success-soft text-success"
                  : reviewState === "error"
                    ? "bg-danger-soft text-danger"
                    : "bg-gold-soft text-gold-ink",
              )}
            >
              {reviewState === "ok"
                ? "Rows look clean"
                : reviewState === "error"
                  ? "Needs correction"
                  : "Review rows"}
            </span>
            {editable && (
              <button
                type="button"
                onClick={addLine}
                className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line-strong bg-canvas px-3 text-xs font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
              >
                <Plus size={14} />
                Add row
              </button>
            )}
          </div>
        </div>
        <div className="grid w-full min-w-0 gap-2 sm:grid-cols-3">
          <ReviewLineMetric
            label="Line total"
            value={formatCurrency(lineTotal, invoice.currency)}
          />
          <ReviewLineMetric
            label="Invoice total"
            value={formatCurrency(invoice.total, invoice.currency)}
          />
          <ReviewLineMetric
            label="Variance"
            value={formatCurrency(variance, invoice.currency)}
            tone={hasVariance ? "warning" : "default"}
          />
        </div>
      </div>

      {(fieldReview?.issue || suspiciousLines.length > 0 || hasVariance) && (
        <div className="border-b border-line bg-gold-soft px-5 py-3 text-sm font-bold leading-6 text-gold-ink">
          {fieldReview?.issue ||
            (suspiciousLines.length
              ? `${suspiciousLines.length} line item(s) may be non-billable text.`
              : "")}
          {hasVariance &&
            ` Line total differs from invoice total by ${formatCurrency(variance, invoice.currency)}.`}
        </div>
      )}

      {/* Mobile: line item cards with the same editable fields */}
      <div className="md:hidden">
        {lines.length ? (
          lines.map((line, index) => {
            const noisy = suspiciousLines.some(
              (candidate) => candidate === line,
            );
            const mapping = lineMappingChip(line);
            return (
              <article
                key={line.id ?? `card-${index}`}
                className="border-b border-line px-4 py-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
                    Line {index + 1}
                  </span>
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span
                      className={cn(
                        "inline-flex max-w-[180px] truncate rounded-full px-2.5 py-1 text-[11px] font-black",
                        mapping.className,
                      )}
                    >
                      {mapping.label}
                    </span>
                    {editable && (
                      <button
                        type="button"
                        onClick={() => removeLine(index)}
                        className="rounded-lg p-2.5 text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
                        aria-label={`Remove line ${index + 1}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </span>
                </div>
                <div className="mt-2">
                  <LineCellInput
                    value={line.description}
                    editable={editable}
                    placeholder="Description"
                    className="text-sm font-black leading-5 text-ink"
                    onCommit={(value) =>
                      updateLine(index, { description: value })
                    }
                  />
                  <span
                    className={cn(
                      "mt-1.5 inline-flex rounded-full px-2.5 py-1 text-[11px] font-black",
                      noisy || reviewState === "error"
                        ? "bg-gold-soft text-gold-ink"
                        : "bg-success-soft text-success",
                    )}
                  >
                    {noisy ? "Check row" : "Looks billable"}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <MobileLineField label="Qty">
                    <LineCellInput
                      value={line.quantity ? String(line.quantity) : ""}
                      editable={editable}
                      placeholder="0"
                      className="font-mono text-sm text-ink"
                      onCommit={(value) =>
                        updateLine(index, {
                          quantity: parseLineAmount(value),
                        })
                      }
                    />
                  </MobileLineField>
                  <MobileLineField label="UOM">
                    <LineCellInput
                      value={line.uom}
                      editable={editable}
                      placeholder="—"
                      className="text-sm font-bold text-ink-secondary"
                      onCommit={(value) => updateLine(index, { uom: value })}
                    />
                  </MobileLineField>
                  <MobileLineField label="Unit price">
                    <LineCellInput
                      value={line.unit_price ? String(line.unit_price) : ""}
                      editable={editable}
                      placeholder="0.00"
                      className="font-mono text-sm text-ink"
                      onCommit={(value) =>
                        updateLine(index, {
                          unit_price: parseLineAmount(value),
                        })
                      }
                    />
                  </MobileLineField>
                  <MobileLineField label="Amount">
                    <LineCellInput
                      value={
                        (line.net_amount ?? line.total_amount)
                          ? String(line.net_amount ?? line.total_amount)
                          : ""
                      }
                      editable={editable}
                      placeholder="0.00"
                      className="font-mono text-sm font-black text-ink"
                      onCommit={(value) => {
                        const amount = parseLineAmount(value);
                        updateLine(index, {
                          net_amount: amount,
                          total_amount: amount + (line.tax_amount ?? 0),
                        });
                      }}
                    />
                  </MobileLineField>
                </div>
              </article>
            );
          })
        ) : (
          <p className="px-5 py-12 text-center text-sm font-semibold text-ink-muted">
            No line items were extracted. Add at least one billable line before
            validation and posting.
          </p>
        )}
      </div>

      <div data-scroll-region="true" className="hidden overflow-x-auto md:block">
        <table className="w-full table-fixed border-collapse text-left">
          <thead className="bg-surface-subtle">
            <tr className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
              <th className="w-[30%] px-3 py-3">Description</th>
              <th className="w-[9%] px-3 py-3 text-right">Qty</th>
              <th className="w-[8%] px-3 py-3">UOM</th>
              <th className="w-[14%] px-3 py-3 text-right">Unit price</th>
              <th className="w-[17%] px-3 py-3 text-right">Amount</th>
              <th className="w-[16%] px-3 py-3">Mapping</th>
              <th className="w-[6%] px-3 py-3" />
            </tr>
          </thead>
          <tbody>
            {lines.length ? (
              lines.map((line, index) => {
                const noisy = suspiciousLines.some(
                  (candidate) => candidate === line,
                );
                const mapping = lineMappingChip(line);
                return (
                  <tr
                    key={line.id ?? `row-${index}`}
                    className="border-t border-line align-top"
                  >
                    <td className="px-2 py-2.5">
                      <LineCellInput
                        value={line.description}
                        editable={editable}
                        placeholder="Description"
                        className="text-sm font-black leading-5 text-ink"
                        onCommit={(value) =>
                          updateLine(index, { description: value })
                        }
                      />
                      <span
                        className={cn(
                          "ml-2 mt-1.5 inline-flex rounded-full px-2.5 py-1 text-[11px] font-black",
                          noisy || reviewState === "error"
                            ? "bg-gold-soft text-gold-ink"
                            : "bg-success-soft text-success",
                        )}
                      >
                        {noisy ? "Check row" : "Looks billable"}
                      </span>
                    </td>
                    <td className="px-2 py-2.5">
                      <LineCellInput
                        value={line.quantity ? String(line.quantity) : ""}
                        editable={editable}
                        placeholder="0"
                        align="right"
                        className="font-mono text-sm text-ink"
                        onCommit={(value) =>
                          updateLine(index, { quantity: parseLineAmount(value) })
                        }
                      />
                    </td>
                    <td className="px-2 py-2.5">
                      <LineCellInput
                        value={line.uom}
                        editable={editable}
                        placeholder="—"
                        className="text-sm font-bold text-ink-secondary"
                        onCommit={(value) => updateLine(index, { uom: value })}
                      />
                    </td>
                    <td className="px-2 py-2.5">
                      <LineCellInput
                        value={line.unit_price ? String(line.unit_price) : ""}
                        editable={editable}
                        placeholder="0.00"
                        align="right"
                        className="font-mono text-sm text-ink"
                        onCommit={(value) =>
                          updateLine(index, {
                            unit_price: parseLineAmount(value),
                          })
                        }
                      />
                    </td>
                    <td className="px-2 py-2.5">
                      <LineCellInput
                        value={
                          (line.net_amount ?? line.total_amount)
                            ? String(line.net_amount ?? line.total_amount)
                            : ""
                        }
                        editable={editable}
                        placeholder="0.00"
                        align="right"
                        className="font-mono text-sm font-black text-ink"
                        onCommit={(value) => {
                          const amount = parseLineAmount(value);
                          updateLine(index, {
                            net_amount: amount,
                            total_amount: amount + (line.tax_amount ?? 0),
                          });
                        }}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex max-w-full truncate rounded-full px-2.5 py-1 text-[11px] font-black",
                          mapping.className,
                        )}
                        title={
                          clientProfile
                            ? `Mapped via ${clientProfile.name} profile`
                            : "Heuristic mapping — confirm in Rules & mapping"
                        }
                      >
                        {mapping.label}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-right">
                      {editable && (
                        <button
                          type="button"
                          onClick={() => removeLine(index)}
                          className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
                          title="Remove row"
                          aria-label={`Remove line ${index + 1}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan={7}
                  className="px-5 py-12 text-center text-sm font-semibold text-ink-muted"
                >
                  No line items were extracted. Add at least one billable line
                  before validation and posting.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MobileLineField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block rounded-xl border border-line bg-surface-subtle px-3 py-2">
      <span className="block text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </span>
      <span className="mt-1 block">{children}</span>
    </label>
  );
}

function lineMappingChip(line: InvoiceLine): {
  label: string;
  className: string;
} {
  if (line.gl_code) {
    return {
      label: line.gl_code,
      className: "bg-accent-soft text-accent-ink",
    };
  }
  const description = (line.description || "").toLowerCase();
  if (/igst|cgst|sgst|\bgst\b|\btax\b|tcs|tds|\bvat\b|cess/.test(description)) {
    return { label: "Tax ledger", className: "bg-accent-soft text-accent-ink" };
  }
  if (line.quantity > 0 && (line.uom || "").trim()) {
    return { label: "Stock item", className: "bg-cyan-soft text-cyan-ink" };
  }
  if (/freight|transport|courier|shipping|round.?off|discount|charge|insurance/.test(description)) {
    return {
      label: "Expense ledger",
      className: "bg-surface-strong text-ink-secondary",
    };
  }
  return { label: "Ledger", className: "bg-surface-strong text-ink-secondary" };
}

function parseLineAmount(value: string) {
  const parsed = Number(value.replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function LineCellInput({
  value,
  editable,
  placeholder,
  align = "left",
  className,
  onCommit,
}: {
  value: string;
  editable: boolean;
  placeholder: string;
  align?: "left" | "right";
  className?: string;
  onCommit: (value: string) => void;
}) {
  if (!editable) {
    return (
      <p
        className={cn(
          "min-h-9 break-words px-2 py-1.5",
          align === "right" && "text-right",
          className,
        )}
      >
        {value || placeholder}
      </p>
    );
  }
  return (
    <input
      value={value}
      placeholder={placeholder}
      onChange={(event) => onCommit(event.target.value)}
      className={cn(
        "w-full rounded-lg border border-transparent bg-transparent px-2 py-1.5 outline-none transition-colors placeholder:text-ink-muted hover:border-line focus:border-accent focus:bg-canvas",
        align === "right" && "text-right",
        className,
      )}
    />
  );
}

function ReviewLineMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "warning";
}) {
  return (
    <div
      className={cn(
        "min-w-[150px] rounded-xl border bg-canvas px-3 py-2",
        tone === "warning" ? "border-gold/30 bg-gold-soft" : "border-line",
      )}
    >
      <p className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </p>
      <p className="mt-1 truncate font-mono text-sm font-black text-ink">
        {value}
      </p>
    </div>
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
