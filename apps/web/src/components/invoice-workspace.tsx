"use client";

import {
  ChevronDown,
  FileArchive,
  FileText,
  LoaderCircle,
  Mail,
  PlayCircle,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";

import { useAuth } from "@/components/auth-provider";
import { InvoiceDetailPanel } from "@/components/invoices/invoice-detail";
import { InvoiceList } from "@/components/invoices/invoice-list";
import { QueueMetrics } from "@/components/invoices/queue-metrics";
import { Button } from "@/components/ui/button";
import { useClientProfiles } from "@/hooks/use-client-profiles";
import {
  clearPreviewInvoices,
  prependPreviewInvoices,
} from "@/lib/preview-invoices";
import type {
  AccountingSystem,
  ApiErrorPayload,
  ClientProfile,
  DetectedInvoiceProfile,
  Invoice,
  InvoiceStatus,
  PostingResult,
  PostingTarget,
  ProfileRecommendationResult,
} from "@/lib/types";
import { apiErrorMessage, cn, formatCurrency } from "@/lib/utils";

const statusOptions: { label: string; status?: InvoiceStatus }[] = [
  { label: "All invoices" },
  { label: "Needs review", status: "needs_review" },
  { label: "Validated", status: "validated" },
  { label: "Approved", status: "approved" },
  { label: "Posted", status: "posted" },
  { label: "Failed", status: "failed" },
];

const parserOptions = [
  { label: "Auto", value: "auto" },
  { label: "AI/OCR assisted", value: "ai_assisted" },
  { label: "GST/e-Invoice adapter", value: "gst_einvoice" },
  { label: "Structured adapter", value: "structured" },
  { label: "Universal extraction", value: "universal" },
];

const previewOnlyUploads =
  process.env.NEXT_PUBLIC_DEMO_PREVIEW_UPLOADS !== "false";

const targetSystems = [
  "QuickBooks",
  "Tally",
  "Zoho Books",
  "Coupa",
  "NetSuite",
  "SAP",
];

function isSiftableInvoice(invoice: Invoice) {
  return (
    invoice.status === "extracted" ||
    invoice.status === "needs_review" ||
    invoice.status === "validated" ||
    invoice.status === "failed" ||
    invoice.validation_issues.length > 0
  );
}

type ExportKind =
  | "quickbooks"
  | "tally"
  | "zoho"
  | "coupa"
  | "netsuite"
  | "sap"
  | "excel"
  | "universal";

type TallyExportProfile = {
  id: string;
  label: string;
  company: string;
  voucherType: string;
  postingMode: "Accounting Voucher" | "Item Invoice";
  purchaseLedger: string;
  taxLedger: string;
  stockItemName: string;
  stockItemHsn: string;
  stockItemUom: string;
  tcsLedger: string;
  roundOffLedger: string;
};

const fallbackTallyProfile: TallyExportProfile = {
  id: "generic",
  label: "Generic / manual setup",
  company: "",
  voucherType: "Purchase",
  postingMode: "Accounting Voucher",
  purchaseLedger: "Purchase Accounts",
  taxLedger: "",
  stockItemName: "",
  stockItemHsn: "",
  stockItemUom: "",
  tcsLedger: "",
  roundOffLedger: "",
};

function accountingSystemForTarget(target: string): AccountingSystem {
  if (target === "Tally") return "tally";
  if (target === "Zoho Books") return "zoho_books";
  if (target === "Coupa") return "coupa";
  if (target === "NetSuite") return "netsuite";
  if (target === "SAP") return "sap";
  return "quickbooks";
}

function postingTargetForSystem(system: string): PostingTarget | null {
  if (system === "QuickBooks") return "quickbooks";
  if (system === "Tally") return "tally";
  if (system === "Zoho Books") return "zoho_books";
  return null;
}

function exportKindForSystem(system: string): { kind: ExportKind; label: string } {
  if (system === "Tally") return { kind: "tally", label: "Tally XML" };
  if (system === "Zoho Books") return { kind: "zoho", label: "Zoho Books JSON" };
  if (system === "Coupa") return { kind: "coupa", label: "Coupa JSON" };
  if (system === "NetSuite") return { kind: "netsuite", label: "NetSuite JSON" };
  if (system === "SAP") return { kind: "sap", label: "SAP JSON" };
  return { kind: "quickbooks", label: "QuickBooks JSON" };
}

function tallyProfileFromClientProfile(
  profile: ClientProfile | null | undefined,
): TallyExportProfile {
  if (!profile) return fallbackTallyProfile;
  const settings = profile.settings;
  return {
    id: profile.id,
    label: profile.name,
    company: settings.company_name,
    voucherType: settings.voucher_type || "Purchase",
    postingMode:
      settings.posting_mode === "item_invoice"
        ? "Item Invoice"
        : "Accounting Voucher",
    purchaseLedger: settings.purchase_ledger || "Purchase Accounts",
    taxLedger: settings.tax_ledger,
    stockItemName:
      settings.stock_item_name ||
      settings.item_mappings[0]?.target_item_name ||
      "",
    stockItemHsn:
      settings.stock_item_hsn || settings.item_mappings[0]?.source_hsn_sac || "",
    stockItemUom:
      settings.stock_item_uom || settings.item_mappings[0]?.target_uom || "",
    tcsLedger: settings.tcs_ledger,
    roundOffLedger: settings.round_off_ledger,
  };
}

export function InvoiceWorkspace() {
  const { activeOrganizationId: organizationId } = useAuth();
  const { profiles: clientProfiles } = useClientProfiles();
  const fileInput = useRef<HTMLInputElement>(null);
  const filterMenuRef = useRef<HTMLDivElement>(null);
  const uploadMenuRef = useRef<HTMLDivElement>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailMode, setDetailMode] = useState<"detail" | "review">("detail");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InvoiceStatus | undefined>();
  const parserMode = "auto";
  const [targetSystem, setTargetSystem] = useState("QuickBooks");
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [manualProfileOverride, setManualProfileOverride] = useState(false);
  const [profileRecommendation, setProfileRecommendation] =
    useState<ProfileRecommendationResult | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState("");

  function changeDetailMode(nextMode: "detail" | "review") {
    setFilterOpen(false);
    setUploadOpen(false);
    setExportOpen(false);
    setDetailMode(nextMode);
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  useEffect(() => {
    if (!filterOpen && !uploadOpen && !exportOpen) return;

    function closeMenusOnOutsideInteraction(
      event: PointerEvent | MouseEvent | TouchEvent,
    ) {
      const target = event.target as Node | null;
      if (
        target &&
        (filterMenuRef.current?.contains(target) ||
          uploadMenuRef.current?.contains(target) ||
          exportMenuRef.current?.contains(target))
      ) {
        return;
      }
      setFilterOpen(false);
      setUploadOpen(false);
      setExportOpen(false);
    }

    function closeMenusOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setFilterOpen(false);
        setUploadOpen(false);
        setExportOpen(false);
      }
    }

    document.addEventListener("pointerdown", closeMenusOnOutsideInteraction, true);
    document.addEventListener("mousedown", closeMenusOnOutsideInteraction, true);
    document.addEventListener("touchstart", closeMenusOnOutsideInteraction, true);
    document.addEventListener("click", closeMenusOnOutsideInteraction, true);
    document.addEventListener("keydown", closeMenusOnEscape);
    return () => {
      document.removeEventListener(
        "pointerdown",
        closeMenusOnOutsideInteraction,
        true,
      );
      document.removeEventListener(
        "mousedown",
        closeMenusOnOutsideInteraction,
        true,
      );
      document.removeEventListener(
        "touchstart",
        closeMenusOnOutsideInteraction,
        true,
      );
      document.removeEventListener("click", closeMenusOnOutsideInteraction, true);
      document.removeEventListener("keydown", closeMenusOnEscape);
    };
  }, [filterOpen, uploadOpen, exportOpen]);

  useEffect(() => {
    if (!organizationId) return;
    const orgId = organizationId;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams({
          organization_id: orgId,
          limit: "100",
        });
        if (status) query.set("status", status);
        const response = await fetch(`/api/invoices?${query}`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Unable to load invoices.");
        const nextInvoices = (await response.json()) as Invoice[];
        setInvoices(nextInvoices);
        setSelectedId((current) =>
          current && nextInvoices.some((invoice) => invoice.id === current)
            ? current
            : (nextInvoices[0]?.id ?? null),
        );
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setError((loadError as Error).message);
        }
      } finally {
        setLoading(false);
      }
    }

    const timer = window.setTimeout(() => {
      void load();
    }, 0);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [organizationId, status]);

  const visibleInvoices = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return invoices;
    return invoices.filter((invoice) =>
      [invoice.invoice_number, invoice.supplier.name, invoice.source_file].some(
        (value) => value.toLowerCase().includes(term),
      ),
    );
  }, [invoices, search]);

  const selected =
    visibleInvoices.find((invoice) => invoice.id === selectedId) ??
    visibleInvoices[0] ??
    null;
  const activeProfileRecommendation =
    selected && profileRecommendation?.invoice_id === selected.id
      ? profileRecommendation
      : null;

  const targetAccountingSystem = accountingSystemForTarget(targetSystem);
  const targetProfiles = useMemo(
    () =>
      clientProfiles.filter(
        (profile) => profile.accounting_system === targetAccountingSystem,
      ),
    [clientProfiles, targetAccountingSystem],
  );
  const effectiveProfileId =
    selectedProfileId &&
    targetProfiles.some((profile) => profile.id === selectedProfileId)
      ? selectedProfileId
      : (targetProfiles.find((profile) => profile.is_default)?.id ??
        targetProfiles[0]?.id ??
        null);
  const selectedClientProfile =
    targetProfiles.find((profile) => profile.id === effectiveProfileId) ??
    null;
  const recommendedProfile =
    activeProfileRecommendation?.recommendations.find(
      (recommendation) =>
        recommendation.profile.id === activeProfileRecommendation.auto_profile_id,
    ) ??
    activeProfileRecommendation?.recommendations[0] ??
    null;
  const selectedTallyProfile = tallyProfileFromClientProfile(
    targetAccountingSystem === "tally" ? selectedClientProfile : null,
  );
  const selectedProfileLabel =
    selectedClientProfile?.name ??
    (targetAccountingSystem === "tally"
      ? fallbackTallyProfile.label
      : "Generic categories");

  const counts = useMemo(
    () => ({
      uploaded: invoices.length,
      extracted: invoices.filter((invoice) => invoice.status !== "uploaded")
        .length,
      validated: invoices.filter((invoice) =>
        ["validated", "approved", "posted"].includes(invoice.status),
      ).length,
      sent: invoices.filter((invoice) => invoice.status === "posted").length,
      exceptions: invoices.filter(
        (invoice) =>
          invoice.status === "needs_review" ||
          invoice.status === "failed" ||
          invoice.validation_issues.length > 0,
      ).length,
    }),
    [invoices],
  );

  const readyInvoices = useMemo(
    () =>
      invoices.filter((invoice) =>
        ["validated", "approved"].includes(invoice.status),
      ),
    [invoices],
  );
  const siftCount = useMemo(
    () => invoices.filter(isSiftableInvoice).length,
    [invoices],
  );

  useEffect(() => {
    if (!selected) {
      return;
    }

    const controller = new AbortController();

    async function loadProfileRecommendation() {
      try {
        const query = new URLSearchParams({
          accounting_system: targetAccountingSystem,
        });
        const response = await fetch(
          `/api/invoices/${selected!.id}/profile-recommendations?${query}`,
          { signal: controller.signal, cache: "no-store" },
        );
        if (!response.ok) return;
        const recommendation =
          (await response.json()) as ProfileRecommendationResult;
        setProfileRecommendation(recommendation);
        if (!manualProfileOverride && recommendation.auto_profile_id) {
          setSelectedProfileId(recommendation.auto_profile_id);
        }
      } catch (recommendationError) {
        if ((recommendationError as Error).name !== "AbortError") {
          setProfileRecommendation(null);
        }
      }
    }

    void loadProfileRecommendation();
    return () => controller.abort();
  }, [manualProfileOverride, selected, targetAccountingSystem]);

  async function uploadFiles(files: File[] = selectedFiles) {
    if (!files.length || !organizationId) return;
    setUploading(true);
    setError("");
    try {
      const uploadedInvoices: Invoice[] = [];
      for (const file of files) {
        const formData = new FormData();
        formData.set("file", file);
        const query = new URLSearchParams({
          organization_id: organizationId,
          parser_mode: parserMode,
          persist: previewOnlyUploads ? "false" : "true",
        });
        if (selectedProfileId) query.set("client_profile_id", selectedProfileId);
        const response = await fetch(`/api/invoices/upload?${query}`, {
          method: "POST",
          body: formData,
        });
        if (!response.ok) {
          const payload = (await response.json()) as ApiErrorPayload;
          throw new Error(apiErrorMessage(payload, `Could not process ${file.name}.`));
        }
        uploadedInvoices.push((await response.json()) as Invoice);
      }

      const newestFirst = [...uploadedInvoices].reverse();
      if (previewOnlyUploads) prependPreviewInvoices(newestFirst);
      setInvoices((current) => [...newestFirst, ...current]);
      setSelectedId(newestFirst[0]?.id ?? null);
      setDetailMode("detail");
      setManualProfileOverride(false);
      setSelectedFiles([]);
      setUploadOpen(false);
    } catch (uploadError) {
      setError((uploadError as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function clearQueue() {
    if (!organizationId) return;
    setClearing(true);
    setError("");
    try {
      const response = await fetch(`/api/organizations/${organizationId}/invoices`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        throw new Error(apiErrorMessage(payload, "Could not clear the invoice queue."));
      }
      setInvoices([]);
      setSelectedId(null);
      setDetailMode("detail");
      setManualProfileOverride(false);
      setProfileRecommendation(null);
      setSelectedFiles([]);
      setUploadOpen(false);
      clearPreviewInvoices();
    } catch (clearError) {
      setError((clearError as Error).message);
    } finally {
      setClearing(false);
    }
  }

  function handlePostingComplete(result: PostingResult) {
    if (result.dry_run) return;
    const nextStatus: InvoiceStatus = result.success ? "posted" : "failed";
    setInvoices((current) =>
      current.map((invoice) =>
        invoice.id === result.invoice_id
          ? {
              ...invoice,
              status: nextStatus,
              updated_at: result.updated_at,
            }
          : invoice,
      ),
    );
  }

  function updateInvoice(nextInvoice: Invoice) {
    setInvoices((current) =>
      current.map((invoice) =>
        invoice.id === nextInvoice.id ? nextInvoice : invoice,
      ),
    );
  }

  function patchInvoice(invoiceId: string, patch: Partial<Invoice>) {
    setInvoices((current) =>
      current.map((invoice) =>
        invoice.id === invoiceId ? { ...invoice, ...patch } : invoice,
      ),
    );
  }

  function addSampleInvoice() {
    const now = new Date().toISOString();
    const sampleId = "sample-neel-gst-2620002662";
    const sampleInvoice: Invoice = {
      id: sampleId,
      organization_id: organizationId ?? "demo-workspace",
      source_file: "sample-india-gst-invoice.pdf",
      source_path: "",
      parser: "demo_sample",
      extraction_engine: "sample",
      page_count: 1,
      status: "validated",
      invoice_number: "2620002662",
      invoice_date: "2026-06-10",
      due_date: "2026-06-10",
      purchase_order: "",
      currency: "INR",
      subtotal: 526680,
      tax_total: 107232,
      total: 633912,
      supplier: {
        name: "MADELIN ENTERPRISES PRIVATE LIMITED",
        tax_id: "24AAPCM0954R1ZR",
        address: ["Gujarat, India"],
        email: "",
        phone: "",
      },
      customer: {
        name: "NEEL ENTERPRISE",
        tax_id: "27AEDPG3704Q1ZC",
        address: ["Maharashtra, India"],
        email: "",
        phone: "",
      },
      direction: "inbound",
      lines: [
        {
          line_number: 1,
          description: "PTA SWEEP",
          quantity: 23940,
          uom: "KG",
          unit_price: 22,
          net_amount: 526680,
          tax_amount: 107232,
          total_amount: 633912,
          hsn_sac: "29173600",
          category: "Materials",
          gl_code: "",
          confidence: 0.96,
        },
      ],
      confidence: 0.97,
      evidence: [
        {
          field: "invoice_number",
          value: "2620002662",
          page: 1,
          snippet: "Supplier Invoice No. & Date: 2620002662 dt. 10-Jun-26",
          confidence: 0.99,
        },
        {
          field: "supplier",
          value: "MADELIN ENTERPRISES PRIVATE LIMITED",
          page: 1,
          snippet: "Supplier (Bill from) MADELIN ENTERPRISES PRIVATE LIMITED",
          confidence: 0.96,
        },
      ],
      validation_issues: [],
      created_at: now,
      updated_at: now,
    };

    prependPreviewInvoices([sampleInvoice]);
    setInvoices((current) => [
      sampleInvoice,
      ...current.filter((invoice) => invoice.id !== sampleId),
    ]);
    setSelectedId(sampleId);
    setDetailMode("detail");
    setUploadOpen(false);
    setError("");
  }

  // Deep link: /app/invoices?invoice={id}&mode=review (used by Sift mode "E" escalation)
  const deepLinkHandled = useRef(false);
  useEffect(() => {
    if (deepLinkHandled.current || loading || !invoices.length) return;
    const params = new URLSearchParams(window.location.search);
    const target = params.get("invoice");
    if (!target) return;
    deepLinkHandled.current = true;
    if (!invoices.some((invoice) => invoice.id === target)) return;
    const shouldOpenReview = params.get("mode") === "review";
    params.delete("invoice");
    params.delete("mode");
    const query = params.toString();
    window.history.replaceState(
      {},
      "",
      window.location.pathname + (query ? `?${query}` : ""),
    );
    const timer = window.setTimeout(() => {
      setSelectedId(target);
      if (shouldOpenReview) changeDetailMode("review");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loading, invoices]);

  if (detailMode === "review" && selected) {
    return (
      <div className="min-h-[calc(100vh-64px)] bg-canvas">
        {error && (
          <div className="border-b border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger sm:px-6 lg:px-8">
            {error}
          </div>
        )}
        <InvoiceDetailPanel
          invoice={selected}
          targetSystem={targetSystem}
          clientProfile={selectedClientProfile}
          mode="review"
          onOpenReview={() => changeDetailMode("review")}
          onCloseReview={() => changeDetailMode("detail")}
          onPostingComplete={handlePostingComplete}
          onInvoiceUpdate={updateInvoice}
          onInvoicePatch={patchInvoice}
        />
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <section className="border-b border-line bg-canvas px-4 py-5 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 2xl:flex-row 2xl:items-center 2xl:justify-between">
          <div className="min-w-0">
            <h1 className="flex flex-wrap items-baseline gap-x-1 text-3xl font-black leading-tight text-ink">
              <span>Invoices</span>
              <span className="text-ink-secondary">/</span>
              <span className="text-2xl font-extrabold text-ink-secondary">
                Queue
              </span>
            </h1>
            <p className="mt-1 text-sm font-semibold text-ink-secondary">
              Review extracted supplier bills before ledger posting.
            </p>
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-center 2xl:max-w-[1080px] 2xl:justify-end">
            <label className="flex h-12 min-w-0 flex-1 items-center gap-2.5 rounded-xl border border-line-strong bg-surface px-3.5 2xl:max-w-[410px]">
              <Search size={17} className="shrink-0 text-ink-muted" />
              <input
                aria-label="Search invoices"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search..."
                className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none placeholder:text-ink-muted"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="text-ink-muted hover:text-ink"
                  aria-label="Clear search"
                >
                  <X size={15} />
                </button>
              )}
            </label>

            <div ref={filterMenuRef} className="relative w-full shrink-0 sm:w-[128px]">
              <ControlButton
                label="Filter"
                icon={<SlidersHorizontal size={15} />}
                open={filterOpen}
                onClick={() => {
                  setFilterOpen((current) => !current);
                  setUploadOpen(false);
                  setExportOpen(false);
                }}
              />
              {filterOpen && (
                <DropdownPanel align="right" width="w-[340px]">
                  <PanelTitle
                    title="Filter queue"
                    detail="Status, target system, and profile routing."
                  />
                  <SectionLabel>Invoice status</SectionLabel>
                  {statusOptions.map((option) => (
                    <RadioRow
                      key={option.label}
                      label={option.label}
                      checked={status === option.status}
                      onClick={() => setStatus(option.status)}
                    />
                  ))}
                  <Divider />
                  <SectionLabel>Primary target system</SectionLabel>
                  {targetSystems.map((system) => (
                    <RadioRow
                      key={system}
                      label={system}
                      checked={targetSystem === system}
                      onClick={() => {
                        setTargetSystem(system);
                        setSelectedProfileId(null);
                        setManualProfileOverride(false);
                      }}
                    />
                  ))}
                  <Divider />
                  <SectionLabel>Client profile</SectionLabel>
                  {activeProfileRecommendation && (
                    <ProfileRecommendationCard
                      detected={activeProfileRecommendation.detected}
                      recommendedProfileName={recommendedProfile?.profile.name}
                      score={recommendedProfile?.score}
                      autoSelected={
                        Boolean(activeProfileRecommendation.auto_profile_id) &&
                        selectedClientProfile?.id === activeProfileRecommendation.auto_profile_id
                      }
                    />
                  )}
                  {targetProfiles.length ? (
                    targetProfiles.map((profile) => (
                      <RadioRow
                        key={profile.id}
                        label={`${profile.name}${profile.is_default ? " (default)" : ""}`}
                        checked={selectedClientProfile?.id === profile.id}
                        onClick={() => {
                          setSelectedProfileId(profile.id);
                          setManualProfileOverride(true);
                        }}
                      />
                    ))
                  ) : targetAccountingSystem === "tally" ? (
                    <RadioRow
                      label="Generic / manual setup"
                      checked
                      onClick={() => {
                        setSelectedProfileId(null);
                        setManualProfileOverride(true);
                      }}
                    />
                  ) : (
                    <p className="mt-2 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-bold text-ink-secondary">
                      No saved profile yet. Add one in{" "}
                      <a
                        href="/app/client-profiles"
                        className="font-black text-accent hover:text-accent-hover"
                      >
                        Client profiles
                      </a>
                      .
                    </p>
                  )}
                </DropdownPanel>
              )}
            </div>

            <ExportPackageMenu
              invoices={readyInvoices}
              targetSystem={targetSystem}
              profileLabel={selectedProfileLabel}
              tallyProfile={selectedTallyProfile}
              clientProfileId={selectedClientProfile?.id ?? null}
              open={exportOpen}
              menuRef={exportMenuRef}
              onPostingComplete={handlePostingComplete}
              onClose={() => setExportOpen(false)}
              onToggle={() => {
                setExportOpen((current) => !current);
                setFilterOpen(false);
                setUploadOpen(false);
              }}
            />

            <div ref={uploadMenuRef} className="relative w-full shrink-0 sm:w-[172px]">
              <ControlButton
                label="Upload PDFs"
                open={uploadOpen}
                variant="primary"
                icon={<Upload size={16} />}
                onClick={() => {
                  setUploadOpen((current) => !current);
                  setFilterOpen(false);
                  setExportOpen(false);
                }}
              />
              {uploadOpen && (
                <DropdownPanel align="right" width="w-[360px]">
                  <PanelTitle
                    title="Upload PDFs"
                    detail={
                      previewOnlyUploads
                        ? "Preview only · not saved to queue"
                        : "200MB per file · PDF"
                    }
                  />
                  <input
                    ref={fileInput}
                    type="file"
                    accept="application/pdf"
                    multiple
                    className="hidden"
                    onChange={(event) =>
                      setSelectedFiles(Array.from(event.target.files ?? []))
                    }
                  />
                  <button
                    className="grid min-h-36 w-full place-items-center rounded-2xl border border-dashed border-line-strong bg-canvas px-4 text-center transition-colors hover:border-accent hover:bg-accent-soft"
                    onClick={() => fileInput.current?.click()}
                  >
                    <span className="grid size-12 place-items-center rounded-xl bg-accent text-white">
                      <Upload size={20} />
                    </span>
                    <span className="mt-3 block text-sm font-black text-ink">
                      {selectedFiles.length
                        ? `${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"} selected`
                        : "Choose invoice PDFs"}
                    </span>
                    <span className="mt-1 block text-xs font-semibold text-ink-muted">
                      Parser: {parserOptions.find((item) => item.value === parserMode)?.label}
                    </span>
                  </button>

                  {selectedFiles.length > 0 && (
                    <div className="mt-3 max-h-32 space-y-2 overflow-y-auto">
                      {selectedFiles.map((file) => (
                        <div
                          key={`${file.name}-${file.size}`}
                          className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2"
                        >
                          <FileText size={16} className="text-ink-muted" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-bold text-ink">
                              {file.name}
                            </span>
                            <span className="text-xs font-semibold text-ink-muted">
                              {formatBytes(file.size)}
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {previewOnlyUploads && (
                    <p className="mt-3 rounded-xl border border-cyan/25 bg-cyan-soft px-3 py-2 text-xs font-bold text-cyan">
                      Demo mode: processed invoices stay local to this browser
                      and are removed by Clear queue.
                    </p>
                  )}

                  <div className="mt-4 grid gap-3">
                    <Button
                      variant="primary"
                      className="h-12 w-full"
                      disabled={!selectedFiles.length || uploading || !organizationId}
                      onClick={() => void uploadFiles()}
                    >
                      {uploading ? (
                        <LoaderCircle size={17} className="animate-spin" />
                      ) : (
                        <Upload size={17} />
                      )}
                      {uploading ? "Processing PDFs" : "Process PDFs"}
                    </Button>
                    <Button
                      className="h-12 w-full"
                      disabled={clearing || (!invoices.length && !selectedFiles.length)}
                      onClick={() => void clearQueue()}
                    >
                      {clearing ? (
                        <LoaderCircle size={17} className="animate-spin" />
                      ) : (
                        <Trash2 size={17} />
                      )}
                      Clear queue
                    </Button>
                  </div>

                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <a
                      href="/app/integrations"
                      className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-3 text-xs font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
                    >
                      <Mail size={15} />
                      Import from email
                    </a>
                    <button
                      type="button"
                      onClick={addSampleInvoice}
                      className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-3 text-xs font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft"
                    >
                      <PlayCircle size={15} />
                      Try sample invoice
                    </button>
                  </div>
                </DropdownPanel>
              )}
            </div>

            <Link
              href="/app/sift"
              className="inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-accent to-cyan px-4 text-sm font-black text-white shadow-glow transition-transform hover:scale-[1.02] sm:w-[124px]"
            >
              <Sparkles size={16} />
              Sift
              {siftCount > 0 && (
                <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-black tabular-nums">
                  {siftCount}
                </span>
              )}
            </Link>
          </div>
        </div>
      </section>

      {detailMode !== "review" && (
        <>
          <QueueMetrics counts={counts} />
          <QueueTabsStrip
            status={status}
            invoices={invoices}
            readyCount={readyInvoices.length}
            onStatusChange={(nextStatus) => setStatus(nextStatus)}
          />
          <QueueReadinessStrip
            readyCount={readyInvoices.length}
            targetSystem={targetSystem}
            profileLabel={selectedProfileLabel}
            detectedProfile={activeProfileRecommendation?.detected ?? null}
          />
        </>
      )}

      {error && (
        <div className="border-b border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger sm:px-6 lg:px-8">
          {error}
        </div>
      )}

      <section
        className={cn(
          "mx-auto grid min-h-[640px] max-w-[1440px]",
          detailMode === "review"
            ? "lg:grid-cols-1"
            : "lg:grid-cols-[minmax(360px,420px)_minmax(0,1fr)]",
        )}
      >
        {detailMode !== "review" && (
          <InvoiceList
            invoices={visibleInvoices}
            selectedId={selected?.id ?? null}
            loading={loading}
            onSelect={(invoiceId) => {
              setSelectedId(invoiceId);
              changeDetailMode("detail");
              setManualProfileOverride(false);
            }}
          />
        )}
        <InvoiceDetailPanel
          invoice={selected}
          targetSystem={targetSystem}
          clientProfile={selectedClientProfile}
          mode={detailMode}
          onOpenReview={() => changeDetailMode("review")}
          onCloseReview={() => changeDetailMode("detail")}
          onPostingComplete={handlePostingComplete}
          onInvoiceUpdate={updateInvoice}
          onInvoicePatch={patchInvoice}
        />
      </section>
    </div>
  );
}

function ExportPackageMenu({
  invoices,
  targetSystem,
  profileLabel,
  tallyProfile,
  clientProfileId,
  open,
  menuRef,
  onPostingComplete,
  onClose,
  onToggle,
}: {
  invoices: Invoice[];
  targetSystem: string;
  profileLabel: string;
  tallyProfile: TallyExportProfile;
  clientProfileId: string | null;
  open: boolean;
  menuRef: RefObject<HTMLDivElement | null>;
  onPostingComplete: (result: PostingResult) => void;
  onClose: () => void;
  onToggle: () => void;
}) {
  const total = invoices.reduce((sum, invoice) => sum + (invoice.total || 0), 0);
  const currency = invoices[0]?.currency || "USD";
  const invoiceCount = invoices.length;
  const noun = invoiceCount === 1 ? "invoice" : "invoices";
  const targetExport = exportKindForSystem(targetSystem);
  const postingTarget = postingTargetForSystem(targetSystem);
  const [bulkPosting, setBulkPosting] = useState(false);
  const [bulkMessage, setBulkMessage] = useState("");
  const [bulkError, setBulkError] = useState("");

  async function postReadyInvoices() {
    if (!postingTarget || !invoices.length) return;
    setBulkPosting(true);
    setBulkMessage("");
    setBulkError("");

    let succeeded = 0;
    let failed = 0;
    try {
      for (const invoice of invoices) {
        const response = await fetch(`/api/invoices/${invoice.id}/post`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target: clientProfileId ? undefined : postingTarget,
            dry_run: false,
            client_profile_id: clientProfileId,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          failed += 1;
          continue;
        }
        const result = payload as PostingResult;
        onPostingComplete(result);
        if (result.success) {
          succeeded += 1;
        } else {
          failed += 1;
        }
      }
      setBulkMessage(`${succeeded} posted · ${failed} failed`);
    } catch (error) {
      setBulkError((error as Error).message);
    } finally {
      setBulkPosting(false);
    }
  }

  return (
    <div ref={menuRef} className="relative w-full shrink-0 sm:w-[132px]">
      <ControlButton
        label="Export"
        open={open}
        icon={<FileArchive size={16} />}
        onClick={onToggle}
      />
      {open && (
        <DropdownPanel align="right" width="w-[min(520px,calc(100vw-32px))]">
          <PanelTitle
            title="Export package"
            detail={`${invoiceCount} ${noun} ready for ${targetSystem}.`}
          />
          <div className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface-subtle">
            <ExportFact label="Package" value={`${invoiceCount} ${noun}`} />
            <ExportFact label="Target" value={targetSystem} />
            <ExportFact
              label="Mapping"
              value={profileLabel || "Generic category mapping"}
            />
            <ExportFact
              label="Total"
              value={
                invoiceCount ? formatCurrency(total, currency) : "No ready invoices"
              }
            />
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <ExportButton
              label={targetExport.label}
              disabled={!invoiceCount}
              onClick={() => {
                downloadExport(targetExport.kind, invoices, tallyProfile);
                onClose();
              }}
            />
            <ExportButton
              label="Excel CSV"
              disabled={!invoiceCount}
              onClick={() => {
                downloadExport("excel", invoices);
                onClose();
              }}
            />
            <ExportButton
              label="Universal JSON"
              disabled={!invoiceCount}
              onClick={() => {
                downloadExport("universal", invoices);
                onClose();
              }}
            />
            {postingTarget && (
              <ExportButton
                label={bulkPosting ? "Posting..." : `Post to ${targetSystem}`}
                disabled={!invoiceCount || bulkPosting}
                onClick={() => void postReadyInvoices()}
              />
            )}
          </div>
          {(bulkMessage || bulkError) && (
            <p
              className={cn(
                "mt-3 rounded-xl border px-3 py-2 text-xs font-extrabold",
                bulkError
                  ? "border-danger/25 bg-danger-soft text-danger"
                  : "border-success/25 bg-success-soft text-success",
              )}
            >
              {bulkError || bulkMessage}
            </p>
          )}
        </DropdownPanel>
      )}
    </div>
  );
}

function QueueTabsStrip({
  status,
  invoices,
  readyCount,
  onStatusChange,
}: {
  status?: InvoiceStatus;
  invoices: Invoice[];
  readyCount: number;
  onStatusChange: (status?: InvoiceStatus) => void;
}) {
  const needsReview = invoices.filter(
    (invoice) =>
      invoice.status === "needs_review" ||
      invoice.status === "failed" ||
      invoice.validation_issues.length > 0,
  ).length;
  const tabs: {
    label: string;
    count: number;
    status?: InvoiceStatus;
    tone?: "default" | "warning" | "danger" | "success";
  }[] = [
    { label: "All", count: invoices.length },
    { label: "Needs review", count: needsReview, status: "needs_review", tone: "warning" },
    { label: "Ready", count: readyCount, status: "validated", tone: "success" },
    {
      label: "Posted",
      count: invoices.filter((invoice) => invoice.status === "posted").length,
      status: "posted",
    },
    {
      label: "Failed",
      count: invoices.filter((invoice) => invoice.status === "failed").length,
      status: "failed",
      tone: "danger",
    },
  ];
  return (
    <section className="border-b border-line bg-canvas px-4 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] min-w-0 gap-2 overflow-x-auto py-4">
        {tabs.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => onStatusChange(tab.status)}
            className={cn(
              "relative h-11 shrink-0 rounded-xl px-3 text-sm font-black text-ink-secondary transition-colors hover:bg-surface hover:text-ink",
              status === tab.status && "bg-accent-soft text-accent-ink",
            )}
          >
            {tab.label}{" "}
            <span
              className={cn(
                "tabular-nums",
                tab.tone === "warning" && "text-gold",
                tab.tone === "danger" && "text-danger",
                tab.tone === "success" && "text-success",
                !tab.tone && "text-accent",
              )}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function QueueReadinessStrip({
  readyCount,
  targetSystem,
  profileLabel,
  detectedProfile,
}: {
  readyCount: number;
  targetSystem: string;
  profileLabel: string;
  detectedProfile: DetectedInvoiceProfile | null;
}) {
  return (
    <section className="border-b border-line bg-canvas px-4 pb-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex min-h-20 flex-col gap-4 rounded-[24px] border border-line bg-surface px-5 py-4 shadow-card xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-black uppercase tracking-[0.18em] text-ink-muted">
              Export readiness
            </p>
            <p className="mt-1 truncate text-xl font-black text-ink">
              {readyCount
                ? `${readyCount} invoice${readyCount === 1 ? "" : "s"} ready for export`
                : "No invoices ready for export"}
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center xl:justify-end">
            <ReadinessInline label="Target" value={targetSystem} />
            <ReadinessInline
              label="Mapping"
              value={profileLabel || "Generic categories"}
            />
            <ReadinessInline
              label="Detected"
              value={
                detectedProfile
                  ? `${detectedProfile.country_code} · ${humanize(detectedProfile.tax_mode)}`
                  : "Auto-detect"
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function ReadinessInline({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex min-w-0 items-center gap-2 rounded-full border border-line bg-canvas px-3 py-2">
      <span className="shrink-0 text-[10px] font-black uppercase tracking-[0.16em] text-ink-muted">
        {label}
      </span>
      <span className="truncate text-sm font-black text-ink">{value}</span>
    </div>
  );
}

function ProfileRecommendationCard({
  detected,
  recommendedProfileName,
  score,
  autoSelected,
}: {
  detected: DetectedInvoiceProfile;
  recommendedProfileName?: string;
  score?: number;
  autoSelected: boolean;
}) {
  return (
    <div className="mt-2 rounded-xl border border-accent/20 bg-accent-soft px-3 py-2 text-xs text-ink-secondary">
      <div className="flex items-center justify-between gap-3">
        <span className="font-black text-ink">
          {detected.country_name} · {detected.currency}
        </span>
        <span className="shrink-0 font-extrabold text-accent-ink">
          {Math.round(detected.confidence * 100)}%
        </span>
      </div>
      <p className="mt-1 font-semibold">
        {humanize(detected.invoice_format)} · {humanize(detected.tax_mode)}
      </p>
      {recommendedProfileName ? (
        <p className="mt-2 font-bold text-ink">
          {autoSelected ? "Auto-selected" : "Recommended"}:{" "}
          {recommendedProfileName}
          {typeof score === "number" ? ` (${Math.round(score * 100)}%)` : ""}
        </p>
      ) : (
        <p className="mt-2 font-bold text-ink">
          No saved matching profile yet.
        </p>
      )}
      {detected.signals.length > 0 && (
        <p className="mt-1 line-clamp-2 text-ink-muted">
          {detected.signals.join(" · ")}
        </p>
      )}
    </div>
  );
}

function ControlButton({
  label,
  icon,
  open,
  onClick,
  variant = "secondary",
}: {
  label: string;
  icon?: ReactNode;
  open: boolean;
  onClick: () => void;
  variant?: "primary" | "secondary";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-12 w-full min-w-0 items-center justify-center gap-2 rounded-xl border px-3.5 text-sm font-black transition-colors",
        variant === "primary"
          ? "border-accent bg-accent text-white shadow-sm shadow-accent/15 hover:bg-accent-hover"
          : "border-line-strong bg-surface text-ink-secondary hover:border-accent hover:text-ink",
      )}
      aria-expanded={open}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      <span className="min-w-0 shrink-0 whitespace-nowrap leading-none">
        {label}
      </span>
      <ChevronDown
        size={16}
        className={cn("shrink-0 transition-transform", open && "rotate-180")}
      />
    </button>
  );
}

function DropdownPanel({
  children,
  align = "left",
  width = "w-[340px]",
}: {
  children: ReactNode;
  align?: "left" | "right";
  width?: string;
}) {
  return (
    <div
      className={cn(
        "absolute top-[calc(100%+10px)] z-50 rounded-2xl border border-line bg-surface p-4 shadow-pop dark:bg-surface-strong",
        width,
        align === "right" ? "right-0" : "left-0",
      )}
    >
      {children}
    </div>
  );
}

function PanelTitle({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-xl bg-surface px-4 py-3">
      <p className="text-base font-black text-ink">{title}</p>
      <p className="mt-1 text-sm leading-5 text-ink-secondary">{detail}</p>
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mt-4 text-[11px] font-extrabold uppercase text-ink-muted">
      {children}
    </p>
  );
}

function Divider() {
  return <div className="mt-4 border-t border-line" />;
}

function RadioRow({
  label,
  checked,
  onClick,
}: {
  label: string;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-2 flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-sm font-bold text-ink-secondary hover:bg-surface"
    >
      <span
        className={cn(
          "grid size-5 place-items-center rounded-full border border-line-strong",
          checked && "border-accent",
        )}
      >
        {checked && <span className="size-2.5 rounded-full bg-accent" />}
      </span>
      {label}
    </button>
  );
}

function ExportFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center border-b border-line px-4 py-3 last:border-b-0">
      <p className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </p>
      <p className="truncate text-right text-sm font-black text-ink">{value}</p>
    </div>
  );
}

function ExportButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="h-12 rounded-xl border border-line-strong bg-surface px-4 text-sm font-black text-ink transition-colors hover:border-accent hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-45"
    >
      {label}
    </button>
  );
}

function formatBytes(size: number) {
  if (size < 1024) return `${size}B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`;
  return `${(size / 1024 / 1024).toFixed(1)}MB`;
}

function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function downloadExport(
  kind: ExportKind,
  invoices: Invoice[],
  tallyProfile = fallbackTallyProfile,
) {
  const now = new Date().toISOString();
  if (kind === "excel") {
    const header = [
      "invoice_number",
      "supplier",
      "invoice_date",
      "currency",
      "total",
      "status",
      "line_description",
      "quantity",
      "uom",
      "amount",
      "category",
    ];
    const rows = invoices.flatMap((invoice) =>
      invoice.lines.length
        ? invoice.lines.map((line) => [
            invoice.invoice_number,
            invoice.supplier.name,
            invoice.invoice_date,
            invoice.currency,
            invoice.total,
            invoice.status,
            line.description,
            line.quantity,
            line.uom,
            line.total_amount || line.net_amount,
            line.category,
          ])
        : [
            [
              invoice.invoice_number,
              invoice.supplier.name,
              invoice.invoice_date,
              invoice.currency,
              invoice.total,
              invoice.status,
              "",
              "",
              "",
              "",
              "",
            ],
          ],
    );
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => csvCell(String(cell ?? ""))).join(","))
      .join("\n");
    downloadBlob(csv, "siftentry_invoices.csv", "text/csv");
    return;
  }

  if (kind === "tally") {
    const xml = buildTallyExport(invoices, now, tallyProfile);
    downloadBlob(xml, "siftentry_tally_export.xml", "application/xml");
    return;
  }

  const payload = {
    target: kind,
    generated_at: now,
    invoices: invoices.map((invoice) => ({
      invoice_number: invoice.invoice_number,
      invoice_date: invoice.invoice_date,
      due_date: invoice.due_date,
      supplier: invoice.supplier,
      customer: invoice.customer,
      currency: invoice.currency,
      subtotal: invoice.subtotal,
      tax_total: invoice.tax_total,
      total: invoice.total,
      status: invoice.status,
      lines: invoice.lines,
    })),
  };
  downloadBlob(
    JSON.stringify(payload, null, 2),
    `siftentry_${kind}_export.json`,
    "application/json",
  );
}

function downloadBlob(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function buildTallyExport(
  invoices: Invoice[],
  generatedAt: string,
  profile: TallyExportProfile,
) {
  const messages = invoices
    .map((invoice) => buildTallyVoucher(invoice, profile))
    .join("\n");
  const companyXml = profile.company
    ? `<SVCURRENTCOMPANY>${escapeXml(profile.company)}</SVCURRENTCOMPANY>`
    : "";
  return `<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        ${companyXml}
      </STATICVARIABLES>
    </DESC>
    <DATA>
      <!-- Generated by SiftEntry at ${escapeXml(generatedAt)} -->
${messages}
    </DATA>
  </BODY>
</ENVELOPE>`;
}

function buildTallyVoucher(invoice: Invoice, profile: TallyExportProfile) {
  const invoiceNumber = invoice.invoice_number || invoice.source_file || "SiftEntry";
  const date = toTallyDate(invoice.invoice_date);
  const total = invoice.total || invoice.subtotal + invoice.tax_total;
  const canBuildItemInvoice = profile.postingMode === "Item Invoice" && invoice.lines.length > 0;

  if (!canBuildItemInvoice) {
    return buildTallyAccountingVoucher(invoice, profile, invoiceNumber, date, total);
  }

  const inventoryEntries = invoice.lines.length
    ? invoice.lines.map((line) => buildTallyInventoryEntry(line, profile)).join("\n")
    : buildTallyInventoryEntry(
      {
        line_number: 1,
        description: profile.stockItemName || "Invoice item",
        quantity: 1,
        uom: "EA",
        unit_price: invoice.subtotal || total,
        net_amount: invoice.subtotal || total,
        tax_amount: invoice.tax_total,
        total_amount: total,
        hsn_sac: profile.stockItemHsn,
        category: "",
        gl_code: "",
        confidence: null,
      },
      profile,
    );
  const netTotal = invoice.lines.reduce((sum, line) => sum + lineNetAmount(line), 0);
  const taxTotal =
    invoice.tax_total || invoice.lines.reduce((sum, line) => sum + (line.tax_amount || 0), 0);
  const roundDelta = roundMoney(total - (netTotal || invoice.subtotal || 0) - taxTotal);
  const roundEntry =
    Math.abs(roundDelta) >= 0.01 && profile.roundOffLedger
      ? ledgerEntry(profile.roundOffLedger, -roundDelta, roundDelta > 0 ? "Yes" : "No")
      : "";
  const taxEntry =
    taxTotal && profile.taxLedger
      ? ledgerEntry(profile.taxLedger, -taxTotal, "Yes")
      : taxTotal
        ? ledgerEntry(profile.purchaseLedger, -taxTotal, "Yes")
        : "";

  return `      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="${escapeXml(profile.voucherType)}" ACTION="Create" OBJVIEW="Invoice Voucher View">
          <DATE>${date}</DATE>
          <EFFECTIVEDATE>${date}</EFFECTIVEDATE>
          <VOUCHERTYPENAME>${escapeXml(profile.voucherType)}</VOUCHERTYPENAME>
          <VOUCHERNUMBER>${escapeXml(invoiceNumber)}</VOUCHERNUMBER>
          <REFERENCE>${escapeXml(invoiceNumber)}</REFERENCE>
          <REFERENCEDATE>${date}</REFERENCEDATE>
          <PARTYLEDGERNAME>${escapeXml(invoice.supplier.name || "Supplier")}</PARTYLEDGERNAME>
          <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
          <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
          <ISINVOICE>Yes</ISINVOICE>
          <NARRATION>Imported by SiftEntry</NARRATION>
${ledgerEntry(invoice.supplier.name || "Supplier", total, "No", true, invoiceNumber)}
${inventoryEntries}
${taxEntry}${roundEntry}
        </VOUCHER>
      </TALLYMESSAGE>`;
}

function buildTallyAccountingVoucher(
  invoice: Invoice,
  profile: TallyExportProfile,
  invoiceNumber: string,
  date: string,
  total: number,
) {
  const netTotal = invoice.subtotal || invoice.lines.reduce((sum, line) => sum + lineNetAmount(line), 0);
  const taxTotal =
    invoice.tax_total || invoice.lines.reduce((sum, line) => sum + (line.tax_amount || 0), 0);
  const purchaseAmount = profile.taxLedger ? netTotal || total - taxTotal : total;
  const taxEntry =
    profile.taxLedger && taxTotal
      ? ledgerEntry(profile.taxLedger, -taxTotal, "Yes")
      : "";

  return `      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="${escapeXml(profile.voucherType)}" ACTION="Create" OBJVIEW="Accounting Voucher View">
          <DATE>${date}</DATE>
          <EFFECTIVEDATE>${date}</EFFECTIVEDATE>
          <VOUCHERTYPENAME>${escapeXml(profile.voucherType)}</VOUCHERTYPENAME>
          <VOUCHERNUMBER>${escapeXml(invoiceNumber)}</VOUCHERNUMBER>
          <REFERENCE>${escapeXml(invoiceNumber)}</REFERENCE>
          <REFERENCEDATE>${date}</REFERENCEDATE>
          <PARTYLEDGERNAME>${escapeXml(invoice.supplier.name || "Supplier")}</PARTYLEDGERNAME>
          <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>
          <ISINVOICE>No</ISINVOICE>
          <NARRATION>Imported by SiftEntry</NARRATION>
${ledgerEntry(invoice.supplier.name || "Supplier", total, "No", true, invoiceNumber)}
${ledgerEntry(profile.purchaseLedger, -purchaseAmount, "Yes")}
${taxEntry}
        </VOUCHER>
      </TALLYMESSAGE>`;
}

function buildTallyInventoryEntry(
  line: Invoice["lines"][number],
  profile: TallyExportProfile,
) {
  const netAmount = lineNetAmount(line);
  const quantity = line.quantity || 1;
  const normalizedUom = (line.uom || "EA").toUpperCase();
  const uom =
    profile.stockItemUom && (normalizedUom === "KG" || normalizedUom === "KGS")
      ? profile.stockItemUom
      : normalizedUom;
  const rate = line.unit_price || (quantity ? netAmount / quantity : netAmount);
  const qtyText = `${formatQty(quantity)} ${uom}`;
  const stockItem = tallyStockItem(line, profile);

  return `      <ALLINVENTORYENTRIES.LIST>
        <STOCKITEMNAME>${escapeXml(stockItem)}</STOCKITEMNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <RATE>${formatMoney(rate)}/${escapeXml(uom)}</RATE>
        <AMOUNT>-${formatMoney(netAmount)}</AMOUNT>
        <ACTUALQTY>${escapeXml(qtyText)}</ACTUALQTY>
        <BILLEDQTY>${escapeXml(qtyText)}</BILLEDQTY>
        <ACCOUNTINGALLOCATIONS.LIST>
          <LEDGERNAME>${escapeXml(profile.purchaseLedger)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-${formatMoney(netAmount)}</AMOUNT>
        </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>`;
}

function ledgerEntry(
  ledger: string,
  amount: number,
  deemedPositive: "Yes" | "No",
  party = false,
  billName = "",
) {
  const billAllocation =
    party && billName
      ? `
        <BILLALLOCATIONS.LIST>
          <NAME>${escapeXml(billName)}</NAME>
          <BILLTYPE>New Ref</BILLTYPE>
          <AMOUNT>${formatMoney(amount)}</AMOUNT>
        </BILLALLOCATIONS.LIST>`
      : "";
  return `      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>${escapeXml(ledger)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>${deemedPositive}</ISDEEMEDPOSITIVE>
        <ISPARTYLEDGER>${party ? "Yes" : "No"}</ISPARTYLEDGER>
        <AMOUNT>${formatMoney(amount)}</AMOUNT>${billAllocation}
      </ALLLEDGERENTRIES.LIST>`;
}

function tallyStockItem(line: Invoice["lines"][number], profile: TallyExportProfile) {
  const hsn = (line.hsn_sac || "").replace(/\D/g, "");
  const description = line.description || "";
  if (profile.stockItemName && profile.stockItemHsn && hsn === profile.stockItemHsn) {
    return profile.stockItemName;
  }
  if (profile.stockItemName && !profile.stockItemHsn) {
    return profile.stockItemName;
  }
  return description || profile.stockItemName || "Invoice item";
}

function lineNetAmount(line: Invoice["lines"][number]) {
  return line.net_amount || Math.max(0, (line.total_amount || 0) - (line.tax_amount || 0));
}

function toTallyDate(value: string) {
  const text = value.trim();
  if (!text) return new Date().toISOString().slice(0, 10).replaceAll("-", "");
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[1]}${iso[2]}${iso[3]}`;
  const monthNames: Record<string, string> = {
    JAN: "01",
    FEB: "02",
    MAR: "03",
    APR: "04",
    MAY: "05",
    JUN: "06",
    JUL: "07",
    AUG: "08",
    SEP: "09",
    OCT: "10",
    NOV: "11",
    DEC: "12",
  };
  const tally = text.toUpperCase().match(/^(\d{1,2})[-\s]([A-Z]{3})[-\s](\d{4})$/);
  if (tally && monthNames[tally[2]]) {
    return `${tally[3]}${monthNames[tally[2]]}${tally[1].padStart(2, "0")}`;
  }
  return new Date().toISOString().slice(0, 10).replaceAll("-", "");
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function formatMoney(value: number) {
  return roundMoney(value).toFixed(2);
}

function formatQty(value: number) {
  if (Math.abs(value - Math.round(value)) < 0.0001) return String(Math.round(value));
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function escapeXml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}
