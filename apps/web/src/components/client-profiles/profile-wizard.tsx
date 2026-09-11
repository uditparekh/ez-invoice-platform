"use client";

import { CheckCircle2, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { blankProfile } from "@/components/client-profiles-panel";
import type {
  AccountingSystem,
  ClientProfile,
  ClientProfilePayload,
  ProfilePostingMode,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/** Full-screen client onboarding wizard — UI Spec §15.
 *  5 steps · ~4 minutes · saves drafts · submits as "Ready for review"
 *  so an admin approves & activates from Client profiles. */

const DRAFT_KEY = "siftentry.wizard.draft";

const systemOptions: {
  value: AccountingSystem;
  label: string;
  detail: string;
}[] = [
  { value: "tally", label: "Tally", detail: "Local XML · vouchers" },
  { value: "quickbooks", label: "QuickBooks", detail: "OAuth API · bills" },
  { value: "zoho_books", label: "Zoho Books", detail: "API · bills" },
];

const countryOptions = [
  {
    id: "IN",
    flag: "🇮🇳",
    label: "India GST",
    detail: "IGST / CGST+SGST · GSTIN · HSN/SAC · TCS",
    settings: {
      country_code: "IN",
      country_name: "India",
      default_currency: "INR",
      tax_mode: "gst_auto",
      tax_registration_label: "GSTIN",
      invoice_format: "gst_einvoice",
    },
  },
  {
    id: "US",
    flag: "🇺🇸",
    label: "US sales tax",
    detail: "State + local rates · Tax ID",
    settings: {
      country_code: "US",
      country_name: "United States",
      default_currency: "USD",
      tax_mode: "sales_tax",
      tax_registration_label: "Tax ID",
      invoice_format: "auto",
    },
  },
  {
    id: "AUTO",
    flag: "✨",
    label: "Auto-detect",
    detail: "Read country & tax format from each invoice",
    settings: {
      country_code: "US",
      country_name: "Auto-detect",
      default_currency: "USD",
      tax_mode: "auto",
      tax_registration_label: "Tax ID",
      invoice_format: "auto",
    },
  },
] as const;

type Draft = {
  step: number;
  name: string;
  system: AccountingSystem;
  country: (typeof countryOptions)[number]["id"];
  voucherMode: ProfilePostingMode;
  expectations: string;
};

const VOUCHER_MODE_LABELS: Record<string, string> = {
  item_invoice: "Item invoice",
  voucher_with_inventory: "Voucher with stock allocation",
  accounting_voucher: "Accounting voucher",
};

const emptyDraft: Draft = {
  step: 0,
  name: "",
  system: "tally",
  country: "IN",
  voucherMode: "item_invoice",
  expectations: "",
};

export function ProfileWizard({
  open,
  saving,
  onClose,
  onCreate,
  onUploadSample,
}: {
  open: boolean;
  saving: boolean;
  onClose: () => void;
  onCreate: (payload: ClientProfilePayload) => Promise<ClientProfile>;
  onUploadSample: (
    profileId: string,
    file: File,
    notes: string,
  ) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState<Draft>(() => {
    if (typeof window === "undefined") return emptyDraft;
    try {
      const stored = JSON.parse(
        window.localStorage.getItem(DRAFT_KEY) || "null",
      ) as Draft | null;
      if (stored && typeof stored.name === "string") return stored;
    } catch {
      /* fresh wizard */
    }
    return emptyDraft;
  });
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  function patch(next: Partial<Draft>) {
    setDraft((current) => {
      const merged = { ...current, ...next };
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(merged));
      return merged;
    });
  }

  const step = draft.step;
  const country = useMemo(
    () =>
      countryOptions.find((option) => option.id === draft.country) ??
      countryOptions[0],
    [draft.country],
  );
  const isTally = draft.system === "tally";
  const canContinue =
    step === 0 ? draft.name.trim().length >= 2 : step < 4 ? true : !submitting;

  function exit() {
    setError("");
    onClose();
  }

  async function submit() {
    setSubmitting(true);
    setError("");
    try {
      const payload = blankProfile(draft.system);
      payload.name = draft.name.trim();
      payload.description = `${country.label} · onboarded via wizard`;
      payload.settings = {
        ...payload.settings,
        ...country.settings,
        company_name: draft.name.trim(),
        posting_mode: isTally
          ? draft.voucherMode
          : payload.settings.posting_mode,
        training_profile: {
          ...payload.settings.training_profile,
          posting_expectations: draft.expectations.trim(),
          onboarding_status: "ready_for_admin_review",
        },
      };
      const profile = await onCreate(payload);
      for (const file of files) {
        await onUploadSample(
          profile.id,
          file,
          "Uploaded during onboarding wizard",
        );
      }
      window.localStorage.removeItem(DRAFT_KEY);
      setDraft(emptyDraft);
      setFiles([]);
      onClose();
    } catch (submitError) {
      setError((submitError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-canvas">
      {/* chrome */}
      <div className="sticky top-0 z-10 border-b border-line bg-shell/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1100px] items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <BrandMark compact />
            <div>
              <p className="text-sm font-semibold text-ink">
                New client profile
              </p>
              <p className="text-xs font-semibold text-ink-muted">
                takes ~4 minutes
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={exit}
            className="inline-flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-ink-secondary transition-colors hover:bg-surface-strong hover:text-ink"
          >
            Save draft &amp; exit
            <X size={16} />
          </button>
        </div>
        {/* step rail */}
        <div className="flex items-center justify-center gap-2 pb-4">
          {[0, 1, 2, 3, 4].map((index) => (
            <div key={index} className="flex items-center gap-2">
              <span
                className={cn(
                  "grid size-9 place-items-center rounded-full text-sm font-semibold transition-colors",
                  index < step
                    ? "bg-success-button text-white"
                    : index === step
                      ? "bg-accent text-white shadow-card"
                      : "bg-surface-strong text-ink-muted",
                )}
              >
                {index < step ? "✓" : index + 1}
              </span>
              {index < 4 && (
                <span
                  className={cn(
                    "h-0.5 w-8 rounded-full sm:w-12",
                    index < step ? "bg-success" : "bg-line",
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* body */}
      <div className="mx-auto max-w-[720px] px-4 py-10 sm:px-6">
        {step === 0 && (
          <StepShell
            title="Which accounting system does this client use?"
            detail="Client name + target system. Everything else adapts to this choice."
          >
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">
                Client name
              </span>
              <input
                autoFocus
                value={draft.name}
                onChange={(event) => patch({ name: event.target.value })}
                placeholder="e.g. Pratham Fasteners"
                className="mt-2 h-[52px] w-full rounded-xl border border-line-strong bg-surface px-4 text-base font-medium text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
              />
            </label>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {systemOptions.map((option) => (
                <OptionCard
                  key={option.value}
                  active={draft.system === option.value}
                  label={option.label}
                  detail={option.detail}
                  onClick={() => patch({ system: option.value })}
                />
              ))}
            </div>
          </StepShell>
        )}

        {step === 1 && (
          <StepShell
            title="Country & tax format"
            detail="Sets how taxes are read, split, and validated on every invoice."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              {countryOptions.map((option) => (
                <OptionCard
                  key={option.id}
                  active={draft.country === option.id}
                  label={`${option.flag} ${option.label}`}
                  detail={option.detail}
                  onClick={() => patch({ country: option.id })}
                />
              ))}
            </div>
            {draft.country === "IN" && (
              <p className="mt-4 rounded-xl bg-accent-soft px-4 py-3 text-sm font-medium text-accent-ink">
                ✦ India GST selected — SiftEntry will validate GSTIN and
                reconcile IGST vs CGST+SGST automatically.
              </p>
            )}
          </StepShell>
        )}

        {step === 2 && (
          <StepShell
            title="Posting mode & expectations"
            detail={
              isTally
                ? "How entries should land in Tally."
                : "Bills post via the API — add any posting expectations below."
            }
          >
            {isTally ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <OptionCard
                  active={draft.voucherMode === "item_invoice"}
                  label="Item invoice"
                  detail="Invoice-style item grid in Tally · stock updates"
                  onClick={() => patch({ voucherMode: "item_invoice" })}
                />
                <OptionCard
                  active={draft.voucherMode === "voucher_with_inventory"}
                  label="Voucher with stock allocation"
                  detail="Dr/Cr voucher screen, items entered in the allocation sub-screen · stock updates"
                  onClick={() =>
                    patch({ voucherMode: "voucher_with_inventory" })
                  }
                />
                <OptionCard
                  active={draft.voucherMode === "accounting_voucher"}
                  label="Accounting voucher"
                  detail="Ledger-only entries · no stock movement · services & expenses"
                  onClick={() => patch({ voucherMode: "accounting_voucher" })}
                />
              </div>
            ) : (
              <p className="rounded-xl border border-line bg-surface px-4 py-3 text-sm font-medium text-ink-secondary">
                {draft.system === "quickbooks" ? "QuickBooks" : "Zoho Books"}{" "}
                posts supplier bills — voucher mode isn&apos;t needed.
              </p>
            )}
            <label className="mt-4 block">
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">
                Posting expectations · optional
              </span>
              <textarea
                value={draft.expectations}
                onChange={(event) =>
                  patch({ expectations: event.target.value })
                }
                rows={3}
                placeholder='e.g. "Round-off to nearest rupee · freight goes to Freight Inward A/C · never auto-post above ₹5L"'
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3 text-sm font-semibold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
              />
            </label>
          </StepShell>
        )}

        {step === 3 && (
          <StepShell
            title="Upload 2–3 sample invoices"
            detail="The parser pre-trains on this client's real formats before the first live invoice."
          >
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf"
              multiple
              className="hidden"
              onChange={(event) => {
                const picked = Array.from(event.target.files ?? []);
                if (picked.length)
                  setFiles((current) => [...current, ...picked]);
                if (fileInput.current) fileInput.current.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="grid w-full place-items-center rounded-2xl border-2 border-dashed border-accent/40 bg-accent-soft/40 px-6 py-12 text-center transition-colors hover:border-accent hover:bg-accent-soft"
            >
              <UploadCloud size={28} className="text-accent-ink" />
              <span className="mt-3 text-sm font-semibold text-accent-ink">
                Drop PDFs here or click to browse
              </span>
              <span className="mt-1 text-xs font-semibold text-ink-muted">
                Uploaded when you submit · can also be added later
              </span>
            </button>
            {files.length > 0 && (
              <div className="mt-3 space-y-2">
                {files.map((file, index) => (
                  <div
                    key={`${file.name}-${index}`}
                    className="flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-2.5"
                  >
                    <p className="min-w-0 truncate text-sm font-medium text-ink">
                      {file.name}
                      <span className="ml-2 text-xs font-semibold text-success">
                        ✓ ready to sift
                      </span>
                    </p>
                    <button
                      type="button"
                      onClick={() =>
                        setFiles((current) =>
                          current.filter((_, i) => i !== index),
                        )
                      }
                      className="rounded-lg p-1.5 text-ink-muted hover:bg-danger-soft hover:text-danger"
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </StepShell>
        )}

        {step === 4 && (
          <StepShell
            title="Review & submit for approval"
            detail="An admin activates the profile from Client profiles before any live posting."
          >
            <div className="rounded-2xl border border-line bg-surface p-5 text-sm font-semibold leading-8 text-ink-secondary shadow-card">
              <p>
                <span className="font-semibold text-ink">
                  {draft.name || "—"}
                </span>{" "}
                → {systemOptions.find((o) => o.value === draft.system)?.label} ·{" "}
                {country.label}
                {isTally &&
                  ` · ${VOUCHER_MODE_LABELS[draft.voucherMode] ?? "Accounting voucher"}`}
              </p>
              <p>
                Tax handling: {country.settings.tax_registration_label} ·{" "}
                {country.settings.default_currency} · {files.length} sample
                {files.length === 1 ? "" : "s"} to train on
              </p>
              {draft.expectations.trim() && (
                <p>Notes: {draft.expectations.trim()}</p>
              )}
            </div>
            <p className="mt-3 rounded-xl border border-gold-soft bg-gold-soft px-4 py-3 text-sm font-medium text-gold-ink">
              Submits as <b>Ready for review</b> — approve &amp; activate it
              from the Client profiles page.
            </p>
            {error && (
              <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-medium text-danger">
                {error}
              </p>
            )}
          </StepShell>
        )}

        {/* nav */}
        <div className="mt-8 flex items-center justify-between">
          <button
            type="button"
            onClick={() => patch({ step: Math.max(0, step - 1) })}
            className={cn(
              "inline-flex h-12 items-center rounded-xl border border-line-strong bg-surface px-5 text-sm font-semibold text-ink-secondary transition-colors hover:border-accent hover:text-accent-ink",
              step === 0 && "invisible",
            )}
          >
            ← Back
          </button>
          <button
            type="button"
            disabled={!canContinue || saving || submitting}
            onClick={() =>
              step < 4 ? patch({ step: step + 1 }) : void submit()
            }
            className={cn(
              "inline-flex h-12 items-center gap-2 rounded-xl px-6 text-sm font-semibold text-white transition-colors disabled:opacity-50",
              step === 4
                ? "bg-success hover:bg-success-button/90"
                : "bg-accent shadow-sm shadow-accent/25 hover:bg-accent-hover",
            )}
          >
            {submitting ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : step === 4 ? (
              <CheckCircle2 size={16} />
            ) : null}
            {step === 4 ? "Submit for approval" : "Continue →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function StepShell({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-ink sm:text-3xl">{title}</h1>
      <p className="mt-1.5 text-sm font-semibold text-ink-secondary">
        {detail}
      </p>
      <div className="mt-6">{children}</div>
    </div>
  );
}

function OptionCard({
  active,
  label,
  detail,
  onClick,
}: {
  active: boolean;
  label: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-2xl border bg-surface p-4 text-left transition-all",
        active
          ? "border-accent shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]"
          : "border-line hover:border-line-strong",
      )}
    >
      <p className="text-base font-semibold text-ink">{label}</p>
      <p className="mt-1 text-xs font-semibold leading-5 text-ink-muted">
        {detail}
      </p>
    </button>
  );
}
