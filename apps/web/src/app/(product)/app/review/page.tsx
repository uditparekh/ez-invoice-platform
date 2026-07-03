"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, FileSearch, ListChecks } from "lucide-react";
import { Suspense, useMemo } from "react";

import { LoadingState } from "@/components/dashboard/loading-state";
import { InvoiceDetailPanel } from "@/components/invoices/invoice-detail";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";

export default function ReviewPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-[calc(100vh-68px)] bg-canvas px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-[1480px]">
            <LoadingState label="Loading review workspace" />
          </div>
        </main>
      }
    >
      <ReviewPageContent />
    </Suspense>
  );
}

function ReviewPageContent() {
  const searchParams = useSearchParams();
  const { invoices, loading, error, reload } = useWorkspaceInvoices({ limit: 100 });

  const queryInvoiceId = searchParams.get("invoice");
  const targetSystem = searchParams.get("target") || "QuickBooks";

  const selectedInvoice = useMemo(() => {
    if (!invoices.length) return null;
    if (!queryInvoiceId) return invoices[0] ?? null;
    return invoices.find((invoice) => invoice.id === queryInvoiceId) ?? invoices[0] ?? null;
  }, [invoices, queryInvoiceId]);

  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <section className="border-b border-line bg-canvas px-4 py-5 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <Link
              href="/app/invoices"
              className="inline-flex items-center gap-2 text-sm font-black text-ink-secondary transition-colors hover:text-accent"
            >
              <ArrowLeft size={16} />
              Invoices
            </Link>
            <h1 className="mt-3 flex flex-wrap items-baseline gap-x-1 text-3xl font-black leading-tight text-ink">
              <span>Review</span>
              <span className="text-ink-secondary">/</span>
              <span className="text-2xl font-extrabold text-ink-secondary">
                Extraction workspace
              </span>
            </h1>
            <p className="mt-1 text-sm font-semibold text-ink-secondary">
              Verify source evidence, correct fields, and save vendor learning before posting.
            </p>
          </div>

          {invoices.length > 0 && (
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="inline-flex h-10 items-center rounded-full border border-line bg-surface px-3 text-xs font-black text-ink-secondary shadow-card">
                {invoices.length} invoice{invoices.length === 1 ? "" : "s"} in queue
              </span>
              <Link
                href="/app/sift"
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-cyan/25 bg-cyan-soft px-3 text-xs font-black text-cyan transition-colors hover:border-cyan"
              >
                <ListChecks size={15} />
                Open Sift mode
              </Link>
            </div>
          )}
        </div>
      </section>

      {loading ? (
        <main className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
          <LoadingState label="Loading review workspace" />
        </main>
      ) : error ? (
        <main className="mx-auto max-w-[980px] px-4 py-6 sm:px-6 lg:px-8">
          <div className="rounded-[24px] border border-danger/25 bg-danger-soft p-6 text-sm font-bold text-danger">
            {error}
          </div>
        </main>
      ) : selectedInvoice ? (
        <InvoiceDetailPanel
          invoice={selectedInvoice}
          mode="review"
          targetSystem={targetSystem}
          onCloseReview={() => {
            window.location.href = `/app/invoices?invoice=${selectedInvoice.id}`;
          }}
          onPostingComplete={() => void reload()}
          onInvoiceUpdate={() => void reload()}
          onInvoicePatch={() => void reload()}
        />
      ) : (
        <main className="mx-auto max-w-[980px] px-4 py-6 sm:px-6 lg:px-8">
          <div className="grid min-h-[420px] place-items-center rounded-[28px] border border-dashed border-line-strong bg-surface p-8 text-center shadow-card">
            <div>
              <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent-ink">
                <FileSearch size={24} />
              </span>
              <h2 className="mt-5 text-2xl font-black text-ink">
                No invoice selected for review
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-secondary">
                Upload or process a supplier invoice first. The review workspace opens here once extraction is ready.
              </p>
              <Link
                href="/app/invoices"
                className="mt-6 inline-flex h-11 items-center justify-center rounded-xl bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover"
              >
                Go to invoice queue
              </Link>
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
