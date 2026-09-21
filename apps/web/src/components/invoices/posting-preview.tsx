"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle,
  FileCheck2,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
} from "lucide-react";
import { apiErrorMessage, formatCurrency } from "@/lib/utils";

type Ledger = { ledger: string; amount: string; side: string; party: boolean };
type Allocation = {
  item: string;
  quantity: string;
  billed_quantity: string;
  rate: string;
  amount: string;
  godowns: string[];
  accounting: Ledger[];
};
export type ApprovalChoice = {
  invoiceId: string;
  client_profile_id?: string;
  preview_hash?: string;
  ready: boolean;
  tally: boolean;
};
type Preview = {
  supported: boolean;
  message?: string;
  state?: string;
  requires_reapproval?: boolean;
  plan?: {
    version?: number;
    preview_hash: string;
    client_profile_id: string;
    client_profile_name: string;
    company: string;
    voucher_type: string;
    voucher_date: string;
    posting_mode: string;
    currency: string;
    invoice_number: string;
    total: number;
    ledgers: Ledger[];
    inventory: Allocation[];
    blocking_issues: string[];
    warnings: string[];
    xml: string;
    approved_at?: string;
  };
};

export function PostingPreview({
  invoiceId,
  profileId,
  onChange,
}: {
  invoiceId: string;
  profileId?: string;
  onChange: (choice: ApprovalChoice) => void;
}) {
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setError("");
      setConfirmed(false);
      onChange({ invoiceId, ready: false, tally: true });
      try {
        const response = await fetch(
          `/api/invoices/${invoiceId}/posting-preview`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_profile_id: profileId }),
            signal: controller.signal,
          },
        );
        const result = await response.json();
        if (!response.ok)
          throw new Error(
            apiErrorMessage(result, "Could not load the proposed entry."),
          );
        if (controller.signal.aborted) return;
        setData(result);
        if (!result.supported)
          onChange({ invoiceId, ready: true, tally: false });
      } catch (caught) {
        if (!controller.signal.aborted) {
          setData(null);
          setError((caught as Error).message);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [invoiceId, profileId, revision, onChange]);

  const plan = data?.plan;
  const frozen = data?.state === "approved";
  return (
    <section
      aria-label="Proposed accounting entry"
      className="my-5 min-w-0 overflow-hidden rounded-2xl border border-line bg-surface"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line p-4 sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          {frozen ? (
            <LockKeyhole size={20} className="mt-0.5 shrink-0 text-success" />
          ) : (
            <FileCheck2 size={20} className="mt-0.5 shrink-0 text-accent-ink" />
          )}
          <div>
            <h3 className="font-semibold text-ink">
              {frozen
                ? `Approved entry · version ${plan?.version}`
                : "Proposed accounting entry"}
            </h3>
            <p className="mt-1 text-sm text-ink-muted">
              {frozen
                ? "The connector receives this saved entry unchanged."
                : "Review the entry before you approve it. Nothing is posted by this preview."}
            </p>
          </div>
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={() => setRevision((value) => value + 1)}
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line px-3 text-sm text-ink-secondary hover:bg-surface-subtle disabled:opacity-50"
        >
          <RefreshCw size={14} /> Reload
        </button>
      </div>
      <div className="space-y-4 p-4 sm:p-5" aria-live="polite">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-ink-muted">
            <LoaderCircle size={16} className="animate-spin" /> Building
            accounting preview…
          </p>
        ) : error ? (
          <p role="alert" className="flex gap-2 text-sm text-danger">
            <AlertCircle size={18} className="shrink-0" />
            {error}
          </p>
        ) : !data?.supported ? (
          <p className="text-sm text-ink-muted">
            {data?.message} Other destinations retain their existing approval
            workflow.
          </p>
        ) : (
          plan && (
            <>
              {data.requires_reapproval && (
                <p className="rounded-xl bg-gold-soft p-3 text-sm text-gold-ink">
                  This entry needs a new approval. Validate the current invoice,
                  review this preview, then approve again.
                </p>
              )}
              <dl className="grid min-w-0 gap-4 sm:grid-cols-2">
                {[
                  ["Tally company", plan.company],
                  ["Profile", plan.client_profile_name],
                  ["Voucher", `${plan.voucher_type} · ${plan.invoice_number}`],
                  ["Posting mode", plan.posting_mode],
                  ["Voucher date", plan.voucher_date],
                  ["Invoice total", formatCurrency(plan.total, plan.currency)],
                ].map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <dt className="text-xs text-ink-muted">{label}</dt>
                    <dd className="mt-1 break-words font-medium text-ink [overflow-wrap:anywhere]">
                      {value || "Not set"}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="rounded-xl border border-line">
                <div className="border-b border-line bg-surface-subtle px-3 py-2 text-xs font-semibold text-ink-muted">
                  Ledger entries · amounts in {plan.currency}
                </div>
                {plan.ledgers.map((entry, index) => (
                  <div
                    key={index}
                    className="grid min-w-0 gap-2 border-b border-line p-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto]"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-sm font-medium text-ink [overflow-wrap:anywhere]">
                        {entry.ledger}
                      </p>
                      <p className="mt-1 text-xs text-ink-muted">
                        {entry.party
                          ? "Supplier ledger · invoice"
                          : "Accounting mapping · profile / line"}
                      </p>
                    </div>
                    <p className="max-w-full break-all text-left font-mono text-sm tabular-nums text-ink sm:text-right">
                      {entry.side === "debit" ? "Dr" : "Cr"}{" "}
                      {formatCurrency(Number(entry.amount), plan.currency)}
                    </p>
                  </div>
                ))}
              </div>
              {plan.inventory.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-ink">
                    Stock allocations
                  </h4>
                  {plan.inventory.map((item, index) => (
                    <div
                      key={index}
                      className="min-w-0 rounded-xl border border-line p-3 text-sm"
                    >
                      <p className="break-words font-medium text-ink [overflow-wrap:anywhere]">
                        {item.item}
                      </p>
                      <p className="mt-1 break-words text-ink-secondary">
                        Actual: {item.quantity || "Not set"} · Billed:{" "}
                        {item.billed_quantity || "Not set"}
                      </p>
                      <p className="mt-1 break-words text-ink-secondary">
                        Rate: {item.rate || "Not set"} · Amount: {item.amount}
                      </p>
                      <p className="mt-1 break-words text-ink-muted">
                        Godown:{" "}
                        {item.godowns.filter(Boolean).join(", ") ||
                          "Not specified in XML"}
                      </p>
                      {item.accounting.map((entry, i) => (
                        <p
                          key={i}
                          className="mt-1 break-words text-ink-secondary"
                        >
                          {entry.ledger} · {entry.side}{" "}
                          {formatCurrency(Number(entry.amount), plan.currency)}
                        </p>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              {plan.blocking_issues.map((issue) => (
                <p
                  key={issue}
                  role="alert"
                  className="rounded-xl bg-danger-soft p-3 text-sm text-danger"
                >
                  {issue}
                </p>
              ))}
              {plan.warnings.map((warning) => (
                <p key={warning} className="text-xs leading-5 text-ink-muted">
                  {warning}
                </p>
              ))}
              <details className="min-w-0 text-sm text-ink-secondary">
                <summary className="cursor-pointer py-2 font-medium">
                  Exact Tally XML
                </summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-surface-subtle p-3 text-xs">
                  {plan.xml}
                </pre>
              </details>
              {!frozen && plan.blocking_issues.length === 0 && (
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-accent/25 bg-accent-soft p-3 text-sm font-medium text-ink">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => {
                      setConfirmed(event.target.checked);
                      onChange({
                        invoiceId,
                        ready: event.target.checked,
                        tally: true,
                        client_profile_id: plan.client_profile_id,
                        preview_hash: plan.preview_hash,
                      });
                    }}
                    className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                  />
                  I reviewed the company, ledger entries and allocations shown
                  above.
                </label>
              )}
              {frozen && (
                <p className="text-xs text-ink-muted">
                  Approved{" "}
                  {plan.approved_at
                    ? new Date(plan.approved_at).toLocaleString()
                    : ""}
                  . Pending entries require reapproval if accounting values or
                  posting rules change. Keep the Windows connector running to
                  collect this entry.
                </p>
              )}
            </>
          )
        )}
      </div>
    </section>
  );
}
