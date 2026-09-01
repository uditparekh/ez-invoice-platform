"use client";

import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  CircleDashed,
  CopyPlus,
  Download,
  FileText,
  Globe2,
  Landmark,
  Layers3,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import { ContentCard } from "@/components/dashboard/content-card";
import { Button } from "@/components/ui/button";
import { useClientProfiles } from "@/hooks/use-client-profiles";
import type {
  AccountingSystem,
  AiExtractionStatus,
  ClientProfile,
  ClientProfileItemMapping,
  ClientProfilePayload,
  ClientProfileSettings,
  ClientTrainingProfile,
  ProfilePostingMode,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const accountingSystems: { label: string; value: AccountingSystem }[] = [
  { label: "Tally", value: "tally" },
  { label: "QuickBooks", value: "quickbooks" },
  { label: "Zoho Books", value: "zoho_books" },
  { label: "Coupa", value: "coupa" },
  { label: "NetSuite", value: "netsuite" },
  { label: "SAP", value: "sap" },
  { label: "Excel", value: "excel" },
  { label: "Custom", value: "custom" },
];

const LIBRARY_COLLAPSE_KEY = "siftentry.profile-library.collapsed";

function readStoredLibraryPreference(): boolean | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(LIBRARY_COLLAPSE_KEY);
    if (stored === "1") return true;
    if (stored === "0") return false;
  } catch {
    // Storage unavailable (private mode, etc.): fall back to the smart default.
  }
  return null;
}

/** Posting modes that move stock and therefore need stock item settings. */
function isInventoryPostingMode(mode: ProfilePostingMode | string | undefined) {
  return mode === "item_invoice" || mode === "voucher_with_inventory";
}

const postingModes: { label: string; value: ProfilePostingMode }[] = [
  { label: "Accounting voucher", value: "accounting_voucher" },
  { label: "Item invoice", value: "item_invoice" },
  { label: "Voucher with stock allocation", value: "voucher_with_inventory" },
  { label: "Supplier bill", value: "supplier_bill" },
  { label: "Export package", value: "export_package" },
  { label: "Custom", value: "custom" },
];

const parsers = [
  { label: "Auto-detect", value: "auto" },
  { label: "GST/e-Invoice", value: "gst_einvoice" },
  { label: "Structured", value: "structured" },
  { label: "Universal extraction", value: "universal" },
];

type CountryProfileOption = {
  label: string;
  value: string;
  countryName: string;
  currency: string;
  taxMode: string;
  taxLabel: string;
  invoiceFormat: string;
};

const countryProfiles: CountryProfileOption[] = [
  {
    label: "United States",
    value: "US",
    countryName: "United States",
    currency: "USD",
    taxMode: "sales_tax",
    taxLabel: "Tax ID",
    invoiceFormat: "auto",
  },
  {
    label: "India",
    value: "IN",
    countryName: "India",
    currency: "INR",
    taxMode: "gst_auto",
    taxLabel: "GSTIN",
    invoiceFormat: "gst_einvoice",
  },
  {
    label: "Canada",
    value: "CA",
    countryName: "Canada",
    currency: "CAD",
    taxMode: "gst_hst",
    taxLabel: "GST/HST",
    invoiceFormat: "auto",
  },
  {
    label: "United Kingdom",
    value: "GB",
    countryName: "United Kingdom",
    currency: "GBP",
    taxMode: "vat",
    taxLabel: "VAT",
    invoiceFormat: "auto",
  },
  {
    label: "European Union",
    value: "EU",
    countryName: "European Union",
    currency: "EUR",
    taxMode: "vat",
    taxLabel: "VAT",
    invoiceFormat: "auto",
  },
  {
    label: "United Arab Emirates",
    value: "AE",
    countryName: "United Arab Emirates",
    currency: "AED",
    taxMode: "vat",
    taxLabel: "TRN",
    invoiceFormat: "auto",
  },
  {
    label: "Custom",
    value: "CUSTOM",
    countryName: "Custom",
    currency: "USD",
    taxMode: "custom",
    taxLabel: "Tax ID",
    invoiceFormat: "custom",
  },
];

const invoiceFormats = [
  { label: "Auto-detect", value: "auto" },
  { label: "India GST/e-Invoice", value: "gst_einvoice" },
  { label: "Structured PDF", value: "structured_pdf" },
  { label: "Scanned OCR", value: "scanned_ocr" },
  { label: "PEPPOL/e-Invoice", value: "peppol" },
  { label: "Custom template", value: "custom" },
];

const taxModes = [
  { label: "Auto-detect", value: "auto" },
  { label: "No tax", value: "none" },
  { label: "US sales tax", value: "sales_tax" },
  { label: "India GST auto", value: "gst_auto" },
  { label: "India IGST", value: "gst_igst" },
  { label: "India CGST + SGST", value: "gst_cgst_sgst" },
  { label: "VAT", value: "vat" },
  { label: "Reverse charge", value: "reverse_charge" },
  { label: "Custom", value: "custom" },
];

const businessProcesses = [
  { label: "Inbound AP", value: "inbound_ap" },
  { label: "Outbound AR", value: "outbound_ar" },
  { label: "Both AP + AR", value: "both" },
];

const llmPolicies = [
  { label: "Review only", value: "review_only" },
  { label: "Suggest corrections", value: "suggest_corrections" },
  { label: "Auto-fill low-risk fields", value: "autofill_low_risk" },
];

const expectedFieldOptions = [
  { label: "Invoice number", value: "invoice_number" },
  { label: "Supplier", value: "supplier" },
  { label: "Customer", value: "customer" },
  { label: "Invoice date", value: "invoice_date" },
  { label: "Due date", value: "due_date" },
  { label: "Currency", value: "currency" },
  { label: "Subtotal", value: "subtotal" },
  { label: "Tax total", value: "tax_total" },
  { label: "Total", value: "total" },
  { label: "Line items", value: "line_items" },
  { label: "HSN/SAC", value: "hsn_sac" },
  { label: "PO/reference", value: "purchase_order" },
  { label: "GST/VAT IDs", value: "tax_registration" },
];

const emptyMapping: ClientProfileItemMapping = {
  source_description_contains: "",
  source_hsn_sac: "",
  target_item_name: "",
  target_uom: "",
  purchase_ledger: "",
  tax_ledger: "",
  metadata: {},
};

function defaultTrainingProfile(): ClientTrainingProfile {
  return {
    onboarding_status: "draft",
    business_process: "inbound_ap",
    invoice_volume: "",
    expected_fields: [
      "invoice_number",
      "supplier",
      "invoice_date",
      "due_date",
      "currency",
      "subtotal",
      "tax_total",
      "total",
      "line_items",
    ],
    accounting_exports: [],
    sample_invoices: [],
    extraction_instructions: "",
    validation_rules: [],
    posting_expectations: "",
    exception_examples: "",
    llm_ready: false,
    llm_policy: "review_only",
  };
}

function defaultSettings(): ClientProfileSettings {
  return {
    company_name: "",
    environment: "production",
    connection_settings: {},
    country_code: "US",
    country_name: "United States",
    default_currency: "USD",
    invoice_format: "auto",
    tax_mode: "auto",
    tax_registration_label: "Tax ID",
    default_parser: "auto",
    direction: "inbound",
    posting_mode: "accounting_voucher",
    voucher_type: "Purchase",
    purchase_ledger: "",
    tax_ledger: "",
    tcs_ledger: "",
    round_off_ledger: "",
    stock_item_name: "",
    stock_item_hsn: "",
    stock_item_uom: "",
    godown_name: "",
    item_mappings: [],
    tax_settings: {
      igst_ledger: "",
      cgst_ledger: "",
      sgst_ledger: "",
      gst_rate: "",
      tax_mode: "auto",
    },
    training_profile: defaultTrainingProfile(),
    metadata: {},
  };
}

function defaultConnectionSettings(
  accountingSystem: AccountingSystem,
): Record<string, unknown> {
  if (accountingSystem === "tally") {
    return {
      connector_enabled: true,
      connector_url: "http://127.0.0.1:8765",
      workspace_id: "local-workspace",
      connector_token: "",
      tally_url: "http://localhost:9000",
    };
  }
  if (accountingSystem === "quickbooks") {
    return {
      environment: "sandbox",
      redirect_uri: "http://localhost:8000/callback",
      realm_id: "",
      oauth_status: "not_connected",
    };
  }
  if (accountingSystem === "zoho_books") {
    return {
      environment: "sandbox",
      region: "com",
      organization_id: "",
      oauth_status: "not_connected",
    };
  }
  return {
    package_format: "json",
    template_name: "",
  };
}

export function blankProfile(
  accountingSystem: AccountingSystem = "tally",
): ClientProfilePayload {
  const settings = defaultSettings();
  settings.connection_settings = defaultConnectionSettings(accountingSystem);
  if (accountingSystem === "quickbooks") {
    settings.posting_mode = "supplier_bill";
    settings.voucher_type = "Bill";
  }
  if (accountingSystem === "zoho_books") {
    settings.posting_mode = "supplier_bill";
    settings.voucher_type = "Bill";
  }
  if (["coupa", "netsuite", "sap", "excel"].includes(accountingSystem)) {
    settings.posting_mode = "export_package";
    settings.voucher_type = "Export";
  }

  return {
    name: "",
    accounting_system: accountingSystem,
    description: "",
    is_default: false,
    settings,
  };
}

function indiaGstItemInvoiceTemplate(): ClientProfilePayload {
  return {
    name: "India GST item invoice",
    accounting_system: "tally",
    description:
      "Starter profile for Tally Item Invoice posting with GST, optional TCS, and round-off ledgers.",
    is_default: false,
    settings: {
      ...defaultSettings(),
      company_name: "",
      country_code: "IN",
      country_name: "India",
      default_currency: "INR",
      invoice_format: "gst_einvoice",
      tax_mode: "gst_igst",
      tax_registration_label: "GSTIN",
      connection_settings: defaultConnectionSettings("tally"),
      direction: "inbound",
      posting_mode: "item_invoice",
      voucher_type: "Purchase",
      purchase_ledger: "",
      tax_ledger: "",
      tcs_ledger: "",
      round_off_ledger: "",
      stock_item_name: "",
      stock_item_hsn: "",
      stock_item_uom: "",
      item_mappings: [
        {
          ...emptyMapping,
          source_description_contains: "",
          source_hsn_sac: "",
          target_item_name: "",
          target_uom: "",
          purchase_ledger: "",
          tax_ledger: "",
        },
      ],
      tax_settings: {
        country_code: "IN",
        default_currency: "INR",
        gst_mode: "igst",
        gst_rate: 18,
        tax_mode: "gst_igst",
      },
    },
  };
}

function coerceTrainingProfile(value: unknown): ClientTrainingProfile {
  const raw = asRecord(value) ?? {};
  const sampleInvoices = Array.isArray(raw.sample_invoices)
    ? raw.sample_invoices.filter(isRecord).map((sample) => ({
        id: stringValue(sample.id),
        filename: stringValue(sample.filename),
        stored_path: stringValue(sample.stored_path),
        size_bytes:
          typeof sample.size_bytes === "number" ? sample.size_bytes : 0,
        content_type: stringValue(sample.content_type) || "application/pdf",
        sample_type: stringValue(sample.sample_type) || "invoice",
        status: stringValue(sample.status) || "uploaded",
        notes: stringValue(sample.notes),
        uploaded_at: stringValue(sample.uploaded_at),
        fields_confirmed: Boolean(sample.fields_confirmed),
      }))
    : [];
  return {
    ...defaultTrainingProfile(),
    ...(raw as Partial<ClientTrainingProfile>),
    expected_fields: Array.isArray(raw.expected_fields)
      ? raw.expected_fields.map(String).filter(Boolean)
      : defaultTrainingProfile().expected_fields,
    accounting_exports: Array.isArray(raw.accounting_exports)
      ? raw.accounting_exports.map(String).filter(Boolean)
      : [],
    validation_rules: Array.isArray(raw.validation_rules)
      ? raw.validation_rules.map(String).filter(Boolean)
      : [],
    sample_invoices: sampleInvoices,
  };
}

function profileToPayload(profile: ClientProfile): ClientProfilePayload {
  return {
    name: profile.name,
    accounting_system: profile.accounting_system,
    description: profile.description,
    is_default: profile.is_default,
    settings: {
      ...defaultSettings(),
      ...profile.settings,
      item_mappings: profile.settings.item_mappings ?? [],
      connection_settings: profile.settings.connection_settings ?? {},
      tax_settings: profile.settings.tax_settings ?? {},
      training_profile: coerceTrainingProfile(
        profile.settings.training_profile,
      ),
      metadata: profile.settings.metadata ?? {},
    },
  };
}

function optionsWithCurrent(
  options: { label: string; value: string }[],
  value: string,
) {
  if (!value || options.some((option) => option.value === value)) return options;
  return [{ label: `Custom (${value})`, value }, ...options];
}

interface ClientProfilesPanelProps {
  accountingSystem?: AccountingSystem;
  title?: string;
  subtitle?: string;
  showSystemField?: boolean;
}

export function ClientProfilesPanel({
  accountingSystem,
  title = "Client profiles",
  subtitle = "Save each client's exact accounting setup so posting logic is selected by workspace, not hardcoded into the app.",
  showSystemField = true,
}: ClientProfilesPanelProps = {}) {
  const {
    profiles,
    loading,
    saving,
    error,
    createProfile,
    updateProfile,
    setDefaultProfile,
    submitProfileForReview,
    recommendProfileSettings,
    activateProfile,
    deleteProfile,
    uploadTrainingSample,
  } = useClientProfiles({ accountingSystem });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ClientProfilePayload>(() =>
    blankProfile(accountingSystem ?? "tally"),
  );
  const [notice, setNotice] = useState("");
  const [profileSearch, setProfileSearch] = useState("");
  // Library collapse: starts collapsed when there is one profile or none (the
  // overwhelming case — the editor gets the space), expanded when there are
  // several. A manual toggle wins and is remembered for this browser.
  const [libraryPreference, setLibraryPreference] = useState<boolean | null>(
    readStoredLibraryPreference,
  );
  const libraryCollapsed =
    libraryPreference !== null ? libraryPreference : profiles.length <= 1;
  function toggleLibrary() {
    const next = !libraryCollapsed;
    setLibraryPreference(next);
    try {
      window.localStorage.setItem(LIBRARY_COLLAPSE_KEY, next ? "1" : "0");
    } catch {
      // Best effort only.
    }
  }
  const [trainingSampleFile, setTrainingSampleFile] = useState<File | null>(
    null,
  );
  const [trainingSampleNotes, setTrainingSampleNotes] = useState("");
  const [trainingUploading, setTrainingUploading] = useState(false);
  const [aiStatus, setAiStatus] = useState<AiExtractionStatus | null>(null);
  const [aiStatusError, setAiStatusError] = useState("");
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const preserveBlankDraftRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function loadAiStatus() {
      setAiStatusError("");
      try {
        const response = await fetch("/api/system/ai-extraction", {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error("AI extraction status is unavailable.");
        }
        const status = (await response.json()) as AiExtractionStatus;
        if (!cancelled) setAiStatus(status);
      } catch (statusError) {
        if (!cancelled) {
          setAiStatus(null);
          setAiStatusError((statusError as Error).message);
        }
      }
    }

    void loadAiStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedId) ?? null,
    [profiles, selectedId],
  );

  useEffect(() => {
    if (loading || selectedId || preserveBlankDraftRef.current || !profiles.length) {
      return;
    }

    const preferredProfile =
      profiles.find((profile) => profile.is_default) ?? profiles[0];
    const timer = window.setTimeout(() => {
      setSelectedId(preferredProfile.id);
      setDraft(profileToPayload(preferredProfile));
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loading, profiles, selectedId]);

  const filteredProfiles = useMemo(() => {
    const needle = profileSearch.trim().toLowerCase();
    if (!needle) return profiles;
    return profiles.filter((profile) => {
      const haystack = [
        profile.name,
        profile.description,
        systemLabel(profile.accounting_system),
        profile.settings.company_name,
        profile.settings.country_name,
        profile.settings.purchase_ledger,
        profile.settings.stock_item_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [profileSearch, profiles]);
  function updateDraft<Key extends keyof ClientProfilePayload>(
    key: Key,
    value: ClientProfilePayload[Key],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateSettings<Key extends keyof ClientProfileSettings>(
    key: Key,
    value: ClientProfileSettings[Key],
  ) {
    setDraft((current) => ({
      ...current,
      settings: { ...current.settings, [key]: value },
    }));
  }

  function updateConnectionSetting(key: string, value: string | boolean) {
    setDraft((current) => ({
      ...current,
      settings: {
        ...current.settings,
        connection_settings: {
          ...(current.settings.connection_settings ?? {}),
          [key]: value,
        },
      },
    }));
  }

  function updateTaxSetting(key: string, value: string | number | boolean) {
    setDraft((current) => ({
      ...current,
      settings: {
        ...current.settings,
        tax_settings: {
          ...(current.settings.tax_settings ?? {}),
          [key]: value,
        },
      },
    }));
  }

  function updateTrainingProfile(patch: Partial<ClientTrainingProfile>) {
    setDraft((current) => {
      const trainingProfile = coerceTrainingProfile(
        current.settings.training_profile,
      );
      return {
        ...current,
        settings: {
          ...current.settings,
          training_profile: {
            ...trainingProfile,
            ...patch,
          },
        },
      };
    });
  }

  function toggleExpectedTrainingField(field: string) {
    const trainingProfile = coerceTrainingProfile(draft.settings.training_profile);
    const fieldSet = new Set(trainingProfile.expected_fields);
    if (fieldSet.has(field)) {
      fieldSet.delete(field);
    } else {
      fieldSet.add(field);
    }
    updateTrainingProfile({ expected_fields: Array.from(fieldSet) });
  }

  function applyCountryProfile(countryCode: string) {
    const country =
      countryProfiles.find((candidate) => candidate.value === countryCode) ??
      countryProfiles.at(-1)!;

    setDraft((current) => ({
      ...current,
      settings: {
        ...current.settings,
        country_code: country.value,
        country_name: country.countryName,
        default_currency: country.currency,
        invoice_format: country.invoiceFormat,
        tax_mode: country.taxMode,
        tax_registration_label: country.taxLabel,
        tax_settings: {
          ...current.settings.tax_settings,
          country_code: country.value,
          country_name: country.countryName,
          default_currency: country.currency,
          tax_mode: country.taxMode,
        },
      },
    }));
  }

  function newProfile() {
    preserveBlankDraftRef.current = true;
    setSelectedId(null);
    setDraft(blankProfile(accountingSystem ?? "tally"));
    setNotice("");
    setTrainingSampleFile(null);
    setTrainingSampleNotes("");
  }

  function selectProfile(profile: ClientProfile) {
    preserveBlankDraftRef.current = false;
    setSelectedId(profile.id);
    setDraft(profileToPayload(profile));
    setNotice("");
    setTrainingSampleFile(null);
    setTrainingSampleNotes("");
  }

  function useIndiaGstItemTemplate() {
    preserveBlankDraftRef.current = true;
    setSelectedId(null);
    setDraft(indiaGstItemInvoiceTemplate());
    setNotice(
      "India GST item-invoice template loaded. Add the client's exact Tally names before saving.",
    );
  }

  async function saveProfile() {
    setNotice("");
    const payload = {
      ...draft,
      accounting_system: accountingSystem ?? draft.accounting_system,
      name: draft.name.trim(),
      description: draft.description.trim(),
    };
    if (!payload.name) {
      setNotice("Profile name is required.");
      return;
    }

    try {
      const saved = selectedProfile
        ? await updateProfile(selectedProfile.id, payload)
        : await createProfile(payload);
      preserveBlankDraftRef.current = false;
      setSelectedId(saved.id);
      setNotice("Client profile saved.");
    } catch (saveError) {
      setNotice((saveError as Error).message);
    }
  }

  async function uploadTrainingSampleAction() {
    setNotice("");
    if (!selectedProfile) {
      setNotice("Save the client profile before uploading training samples.");
      return;
    }
    if (!trainingSampleFile) {
      setNotice("Choose a sample invoice PDF first.");
      return;
    }
    setTrainingUploading(true);
    try {
      const updated = await uploadTrainingSample(
        selectedProfile.id,
        trainingSampleFile,
        trainingSampleNotes,
      );
      setDraft(profileToPayload(updated));
      setSelectedId(updated.id);
      setTrainingSampleFile(null);
      setTrainingSampleNotes("");
      setNotice("Training sample uploaded.");
    } catch (uploadError) {
      setNotice((uploadError as Error).message);
    } finally {
      setTrainingUploading(false);
    }
  }

  async function importProfile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setNotice("");
    try {
      const imported = normalizeImportedProfile(
        JSON.parse(await file.text()),
        accountingSystem,
      );
      setSelectedId(null);
      setDraft(imported);
      setNotice("Profile imported into a draft. Review it, then save.");
    } catch (importError) {
      setNotice((importError as Error).message);
    } finally {
      event.target.value = "";
    }
  }

  function exportProfile() {
    const payload = selectedProfile ? profileToPayload(selectedProfile) : draft;
    downloadProfileJson(payload, payload.name || "client-profile");
    setNotice("Profile JSON exported.");
  }

  async function makeDefault() {
    if (!selectedProfile) return;
    setNotice("");
    try {
      await setDefaultProfile(selectedProfile.id);
      setNotice("Default profile updated.");
    } catch (defaultError) {
      setNotice((defaultError as Error).message);
    }
  }

  async function submitForReview() {
    if (!selectedProfile) {
      setNotice("Save the client profile before submitting it for admin review.");
      return;
    }
    setNotice("");
    try {
      const updated = await submitProfileForReview(selectedProfile.id);
      setDraft(profileToPayload(updated));
      setSelectedId(updated.id);
      setNotice("Client profile submitted for admin review.");
    } catch (reviewError) {
      setNotice((reviewError as Error).message);
    }
  }

  async function generateRecommendations() {
    if (!selectedProfile) {
      setNotice("Save the client profile before generating recommendations.");
      return;
    }
    setNotice("");
    try {
      const updated = await recommendProfileSettings(selectedProfile.id);
      setDraft(profileToPayload(updated));
      setSelectedId(updated.id);
      setNotice("Client profile recommendations generated.");
    } catch (recommendError) {
      setNotice((recommendError as Error).message);
    }
  }

  async function approveAndActivate() {
    if (!selectedProfile) {
      setNotice("Save the client profile before activating it.");
      return;
    }
    setNotice("");
    try {
      const updated = await activateProfile(selectedProfile.id);
      setDraft(profileToPayload(updated));
      setSelectedId(updated.id);
      setNotice("Client profile activated.");
    } catch (activateError) {
      setNotice((activateError as Error).message);
    }
  }

  async function removeProfile() {
    if (!selectedProfile) return;
    const confirmed = window.confirm(
      `Delete "${selectedProfile.name}" from this workspace?`,
    );
    if (!confirmed) return;
    setNotice("");
    try {
      await deleteProfile(selectedProfile.id);
      preserveBlankDraftRef.current = false;
      setSelectedId(null);
      setDraft(blankProfile(accountingSystem ?? "tally"));
      setNotice("Client profile deleted.");
    } catch (deleteError) {
      setNotice((deleteError as Error).message);
    }
  }

  const countryOptions = optionsWithCurrent(
    countryProfiles.map(({ label, value }) => ({ label, value })),
    draft.settings.country_code,
  );
  const invoiceFormatOptions = optionsWithCurrent(
    invoiceFormats,
    draft.settings.invoice_format,
  );
  const taxModeOptions = optionsWithCurrent(taxModes, draft.settings.tax_mode);
  const draftSystem = accountingSystem ?? draft.accounting_system;
  const trainingProfile = coerceTrainingProfile(draft.settings.training_profile);
  const onboardingChecklist = getOnboardingChecklist(draft, draftSystem);
  const onboardingStatus = trainingProfile.onboarding_status || "draft";

  return (
    <ContentCard
      title={title}
      subtitle={subtitle}
      action={
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={newProfile}>
            <Plus size={14} />
            New profile
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => importInputRef.current?.click()}
          >
            <Upload size={14} />
            Import JSON
          </Button>
          <Button size="sm" variant="secondary" onClick={exportProfile}>
            <Download size={14} />
            Export JSON
          </Button>
          {(!accountingSystem || accountingSystem === "tally") && (
            <Button
              size="sm"
              variant="secondary"
              onClick={useIndiaGstItemTemplate}
            >
              <CopyPlus size={14} />
              India GST template
            </Button>
          )}
        </div>
      }
    >
      <input
        ref={importInputRef}
        type="file"
        accept="application/json"
        className="hidden"
        onChange={(event) => void importProfile(event)}
      />
      <div className="space-y-5">
        <div
          className={cn(
            "grid gap-5 transition-[grid-template-columns] duration-300 ease-in-out",
            libraryCollapsed
              ? "xl:grid-cols-[64px_minmax(0,1fr)]"
              : "xl:grid-cols-[320px_minmax(0,1fr)]",
          )}
        >
          <aside
            className={cn(
              "overflow-hidden rounded-2xl border border-line bg-canvas transition-[padding] duration-300",
              libraryCollapsed ? "p-2 xl:px-2 xl:py-3" : "p-4",
            )}
            aria-label="Profile library"
          >
            {/* Header row: always visible. On desktop it holds the collapse toggle;
                below xl the same toggle collapses the list vertically. */}
            <div
              className={cn(
                "flex items-start gap-3",
                libraryCollapsed ? "justify-between xl:flex-col xl:items-center" : "justify-between",
              )}
            >
              {!libraryCollapsed && (
                <div className="min-w-0">
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                    Profile library
                  </p>
                  <h3 className="mt-1 text-base font-black text-ink">
                    Workspace setups
                  </h3>
                </div>
              )}
              <div
                className={cn(
                  "flex items-center gap-2",
                  libraryCollapsed && "xl:flex-col",
                )}
              >
                <span
                  className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-black text-ink-secondary"
                  title={`${filteredProfiles.length} profile${filteredProfiles.length === 1 ? "" : "s"}`}
                >
                  {filteredProfiles.length}
                </span>
                <button
                  type="button"
                  onClick={() => toggleLibrary()}
                  aria-expanded={!libraryCollapsed}
                  aria-controls="profile-library-list"
                  title={libraryCollapsed ? "Expand profile library" : "Collapse profile library"}
                  className="grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-surface text-ink-secondary transition-colors hover:border-accent hover:text-accent"
                >
                  <span className="hidden xl:block">
                    {libraryCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
                  </span>
                  <span className="xl:hidden">
                    {libraryCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                  </span>
                </button>
              </div>
            </div>

            {libraryCollapsed ? (
              /* Rail: switch profiles without expanding. Hidden below xl, where
                 collapsed simply means "list hidden". */
              <div className="mt-3 hidden flex-col items-center gap-2 xl:flex">
                {filteredProfiles.map((profile) => (
                  <button
                    key={profile.id}
                    type="button"
                    onClick={() => selectProfile(profile)}
                    title={`${profile.name} · ${systemLabel(profile.accounting_system)}`}
                    aria-label={`Open profile ${profile.name}`}
                    aria-current={selectedId === profile.id ? "true" : undefined}
                    className={cn(
                      "grid size-10 place-items-center rounded-xl border text-xs font-black uppercase transition-colors",
                      selectedId === profile.id
                        ? "border-accent bg-accent-soft text-accent-ink"
                        : "border-line bg-surface text-ink-secondary hover:border-accent hover:text-accent",
                    )}
                  >
                    {profile.accounting_system.slice(0, 2)}
                  </button>
                ))}
              </div>
            ) : (
              <div id="profile-library-list">
                <label className="mt-4 flex h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink-secondary">
                  <Search size={16} className="shrink-0 text-ink-muted" />
                  <input
                    value={profileSearch}
                    onChange={(event) => setProfileSearch(event.target.value)}
                    placeholder="Search profiles"
                    className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-muted"
                  />
                </label>

                <div className="mt-4 space-y-3">
                  {loading ? (
                    <div className="rounded-2xl border border-line bg-surface px-4 py-6 text-sm font-bold text-ink-secondary">
                      <LoaderCircle
                        className="mr-2 inline animate-spin"
                        size={16}
                      />
                      Loading profiles
                    </div>
                  ) : filteredProfiles.length ? (
                    filteredProfiles.map((profile) => (
                      <button
                        key={profile.id}
                        type="button"
                        onClick={() => selectProfile(profile)}
                        className={cn(
                          "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                          selectedId === profile.id
                            ? "border-accent bg-accent-soft"
                            : "border-line bg-surface hover:border-accent hover:bg-surface-subtle",
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-xs font-black uppercase text-accent-ink">
                            {profile.accounting_system.slice(0, 2)}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-black text-ink">
                              {profile.name}
                            </span>
                            <span className="mt-1 block truncate text-xs font-bold text-ink-muted">
                              {systemLabel(profile.accounting_system)} /{" "}
                              {profile.settings.company_name || "Company not set"}
                            </span>
                            <span className="mt-2 flex flex-wrap gap-1.5">
                              <MiniChip>
                                {profile.settings.default_currency || "USD"}
                              </MiniChip>
                              <MiniChip>
                                {postingModeLabel(profile.settings.posting_mode)}
                              </MiniChip>
                              {profile.is_default && (
                                <MiniChip tone="accent">Default</MiniChip>
                              )}
                            </span>
                          </span>
                          {profile.is_default && (
                            <Star
                              size={16}
                              className="shrink-0 fill-accent text-accent"
                            />
                          )}
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-4 py-6 text-sm font-semibold leading-6 text-ink-secondary">
                      {profileSearch
                        ? "No profiles match that search."
                        : "No profiles saved yet. Use the India GST template or start with a blank profile."}
                    </div>
                  )}
                </div>
              </div>
            )}
          </aside>

          <section className="overflow-hidden rounded-2xl border border-line bg-canvas">
            <div className="flex flex-col gap-4 border-b border-line bg-surface px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                  {selectedProfile ? "Editing profile" : "New profile"}
                </p>
                <h3 className="mt-1 text-xl font-black text-ink">
                  {draft.name || "Untitled client setup"}
                </h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Pill icon={<ShieldCheck size={13} />}>
                    {onboardingStatusLabel(onboardingStatus)}
                  </Pill>
                  <Pill icon={<Landmark size={13} />}>
                    {systemLabel(draftSystem)}
                  </Pill>
                  <Pill icon={<Globe2 size={13} />}>
                    {draft.settings.country_name || "Country not set"}
                  </Pill>
                  <Pill icon={<Layers3 size={13} />}>
                    {draft.settings.default_currency || "USD"}
                  </Pill>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {selectedProfile && !selectedProfile.is_default && (
                  <Button size="sm" variant="secondary" onClick={makeDefault}>
                    <BadgeCheck size={14} />
                    Set default
                  </Button>
                )}
                {selectedProfile && (
                  <Button size="sm" variant="danger" onClick={removeProfile}>
                    <Trash2 size={14} />
                    Delete
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="primary"
                  onClick={saveProfile}
                  disabled={saving}
                >
                  {saving ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Save size={14} />
                  )}
                  Save profile
                </Button>
              </div>
            </div>

          {(notice || error) && (
            <div
              className={cn(
                "mx-5 mt-5 rounded-xl border px-4 py-3 text-sm font-bold",
                notice === "Client profile saved." ||
                  notice === "Default profile updated." ||
                  notice === "Client profile deleted."
                  ? "border-success/30 bg-success-soft text-success"
                  : "border-gold/30 bg-gold-soft text-gold",
              )}
            >
              {notice || error}
            </div>
          )}

          <div className="space-y-5 p-5">
            <div className="rounded-2xl border border-line bg-surface p-4">
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
                    Core setup
                  </p>
                  <h4 className="mt-1 text-lg font-black text-ink">
                    Client identity
                  </h4>
                </div>
                <span className="w-fit rounded-full border border-line bg-canvas px-3 py-1 text-xs font-black text-ink-secondary">
                  {draft.settings.default_currency || "USD"} /{" "}
                  {draft.settings.country_code || "US"}
                </span>
              </div>
              <FormGrid>
                <TextField
                  label="Profile name"
                  value={draft.name}
                  onChange={(value) => updateDraft("name", value)}
                  placeholder="Client + workflow name"
                />
                {showSystemField && !accountingSystem && (
                  <SelectField
                    label="Accounting system"
                    value={draft.accounting_system}
                    options={accountingSystems}
                    onChange={(value) => {
                      const nextSystem = value as AccountingSystem;
                      const nextDefaults = blankProfile(nextSystem).settings;
                      setDraft((current) => ({
                        ...current,
                        accounting_system: nextSystem,
                        settings: {
                          ...current.settings,
                          connection_settings:
                            nextDefaults.connection_settings,
                          posting_mode: nextDefaults.posting_mode,
                          voucher_type: nextDefaults.voucher_type,
                        },
                      }));
                    }}
                  />
                )}
                <TextField
                  label="Company name"
                  value={draft.settings.company_name}
                  onChange={(value) => updateSettings("company_name", value)}
                  placeholder="Exact Tally or ERP company"
                />
                <TextField
                  label="Description"
                  value={draft.description}
                  onChange={(value) => updateDraft("description", value)}
                  placeholder="When this profile should be used"
                  wide
                />
              </FormGrid>
            </div>

            <SettingsPanel
              title="Market and tax behavior"
              detail="Country, currency, parser, and tax format used while reviewing invoices."
              defaultOpen
            >
              <FormGrid>
                <SelectField
                  label="Country profile"
                  value={draft.settings.country_code}
                  options={countryOptions}
                  onChange={applyCountryProfile}
                />
                <TextField
                  label="Country name"
                  value={draft.settings.country_name}
                  onChange={(value) => updateSettings("country_name", value)}
                  placeholder="United States"
                />
                <TextField
                  label="Default currency"
                  value={draft.settings.default_currency}
                  onChange={(value) =>
                    updateSettings("default_currency", value.toUpperCase())
                  }
                  placeholder="USD"
                />
                <SelectField
                  label="Invoice format"
                  value={draft.settings.invoice_format}
                  options={invoiceFormatOptions}
                  onChange={(value) => updateSettings("invoice_format", value)}
                />
                <SelectField
                  label="Tax mode"
                  value={draft.settings.tax_mode}
                  options={taxModeOptions}
                  onChange={(value) => {
                    setDraft((current) => ({
                      ...current,
                      settings: {
                        ...current.settings,
                        tax_mode: value,
                        tax_settings: {
                          ...current.settings.tax_settings,
                          tax_mode: value,
                        },
                      },
                    }));
                  }}
                />
                <TextField
                  label="Tax ID label"
                  value={draft.settings.tax_registration_label}
                  onChange={(value) =>
                    updateSettings("tax_registration_label", value)
                  }
                  placeholder="GSTIN, VAT, TRN"
                />
              </FormGrid>
            </SettingsPanel>

            <SettingsPanel
              title="Posting behavior"
              detail="Profile-owned ERP mode, voucher type, and connector metadata."
              defaultOpen
            >
              <FormGrid>
                <TextField
                  label="Environment"
                  value={draft.settings.environment}
                  onChange={(value) => updateSettings("environment", value)}
                  placeholder="production or sandbox"
                />
                <SelectField
                  label="Default parser"
                  value={draft.settings.default_parser}
                  options={parsers}
                  onChange={(value) => updateSettings("default_parser", value)}
                />
                <TextField
                  label="Direction"
                  value={draft.settings.direction}
                  onChange={(value) => updateSettings("direction", value)}
                  placeholder="inbound"
                />
                <SelectField
                  label="Posting mode"
                  value={draft.settings.posting_mode}
                  options={postingModes}
                  onChange={(value) =>
                    updateSettings("posting_mode", value as ProfilePostingMode)
                  }
                />
                <TextField
                  label="Voucher type"
                  value={draft.settings.voucher_type}
                  onChange={(value) => updateSettings("voucher_type", value)}
                  placeholder="Purchase"
                />
              </FormGrid>
              <div className="mt-4">
                {renderConnectionFields(
                  draftSystem,
                  draft.settings.connection_settings ?? {},
                  updateConnectionSetting,
                )}
              </div>
            </SettingsPanel>

            <SettingsPanel
              title="Ledgers and stock items"
              detail="The exact names from this client's books. Postings fail if a name here differs from the accounting system by even one character — copy names, don't type them."
            >
              <div className="space-y-4">
                <FieldGroup
                  title="Where purchases post"
                  detail="Every invoice debits the purchase ledger and credits the supplier. Tax is split out to its own ledgers."
                >
                  <TextField
                    label="Purchase ledger"
                    value={draft.settings.purchase_ledger}
                    onChange={(value) => updateSettings("purchase_ledger", value)}
                    hint="Copy the exact ledger name from the accounting system."
                  />
                  <TextField
                    label="Tax ledger"
                    value={draft.settings.tax_ledger}
                    onChange={(value) => updateSettings("tax_ledger", value)}
                    hint="Used when tax is posted as one line, or as the IGST fallback."
                  />
                  <TextField
                    label="Input IGST ledger"
                    value={String(draft.settings.tax_settings.igst_ledger ?? "")}
                    onChange={(value) => updateTaxSetting("igst_ledger", value)}
                    hint="Interstate GST. Leave blank to use the tax ledger."
                  />
                  <TextField
                    label="Input CGST ledger"
                    value={String(draft.settings.tax_settings.cgst_ledger ?? "")}
                    onChange={(value) => updateTaxSetting("cgst_ledger", value)}
                    hint="Central half of intrastate GST."
                  />
                  <TextField
                    label="Input SGST ledger"
                    value={String(draft.settings.tax_settings.sgst_ledger ?? "")}
                    onChange={(value) => updateTaxSetting("sgst_ledger", value)}
                    hint="State half of intrastate GST."
                  />
                  <TextField
                    label="TCS ledger"
                    optional
                    value={draft.settings.tcs_ledger}
                    onChange={(value) => updateSettings("tcs_ledger", value)}
                    hint="Only if suppliers charge TCS on invoices."
                  />
                  <TextField
                    label="Round-off ledger"
                    optional
                    value={draft.settings.round_off_ledger}
                    onChange={(value) =>
                      updateSettings("round_off_ledger", value)
                    }
                    hint="Absorbs paise differences between line totals and the invoice total."
                  />
                </FieldGroup>

                {isInventoryPostingMode(draft.settings.posting_mode) ? (
                  <FieldGroup
                    title="Default stock item"
                    detail="Used for any invoice line that no item mapping matches. Stock moves in the accounting system under this item."
                  >
                    <TextField
                      label="Stock item"
                      value={draft.settings.stock_item_name}
                      onChange={(value) => updateSettings("stock_item_name", value)}
                      hint="Exact stock item name as it appears in the accounting system."
                    />
                    <TextField
                      label="Unit (UOM)"
                      value={draft.settings.stock_item_uom}
                      onChange={(value) => updateSettings("stock_item_uom", value)}
                      hint="The unit symbol that stock item uses — for example Nos or KGS."
                    />
                    <TextField
                      label="HSN/SAC"
                      optional
                      value={draft.settings.stock_item_hsn}
                      onChange={(value) => updateSettings("stock_item_hsn", value)}
                      hint="Recommended for GST validation on India profiles."
                    />
                    <TextField
                      label="Godown / location"
                      optional
                      value={draft.settings.godown_name}
                      onChange={(value) => updateSettings("godown_name", value)}
                      hint="Only if the accounting system prompts for a godown during entry."
                    />
                  </FieldGroup>
                ) : (
                  <div className="rounded-2xl border border-dashed border-line-strong bg-canvas px-4 py-3 text-xs font-semibold leading-5 text-ink-secondary">
                    Stock item settings are hidden because this profile posts
                    ledger-only accounting vouchers. Switch the posting mode to
                    an inventory-backed mode to configure stock items.
                  </div>
                )}

                <div className="flex flex-col gap-3 rounded-2xl border border-line bg-canvas p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-black text-ink">Item mapping rules</p>
                    <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
                      {draft.settings.item_mappings.length
                        ? `${draft.settings.item_mappings.length} rule${draft.settings.item_mappings.length === 1 ? "" : "s"} override the default stock item for matching invoice lines.`
                        : "No rules yet. Rules override the default stock item for specific invoice lines and are built from real invoice data."}
                    </p>
                  </div>
                  <Link
                    href="/app/rules"
                    className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl border border-line bg-surface px-4 text-sm font-black text-accent transition-colors hover:border-accent"
                  >
                    Manage in Rules &amp; mapping
                    <ArrowRight size={14} />
                  </Link>
                </div>
              </div>
            </SettingsPanel>

            <SettingsPanel
              title="AI extraction and parser training"
              detail="Upload real invoices and describe how they are laid out. Everything here is sent to the AI with every extraction for this client."
            >
              <div className="mb-5">
                <AiReadinessPanel
                  aiStatus={aiStatus}
                  aiStatusError={aiStatusError}
                  profileName={draft.name || "Untitled client setup"}
                  accountingSystem={draftSystem}
                  countryCode={draft.settings.country_code}
                  currency={draft.settings.default_currency || "USD"}
                  trainingProfile={trainingProfile}
                />
              </div>
              <TrainingProfileSection
                selectedProfile={selectedProfile}
                trainingProfile={trainingProfile}
                sampleFile={trainingSampleFile}
                sampleNotes={trainingSampleNotes}
                uploading={trainingUploading}
                onUpdate={updateTrainingProfile}
                onToggleField={toggleExpectedTrainingField}
                onFileChange={setTrainingSampleFile}
                onNotesChange={setTrainingSampleNotes}
                onUpload={() => void uploadTrainingSampleAction()}
              />
            </SettingsPanel>

            <OnboardingApprovalPanel
              selectedProfile={selectedProfile}
              status={onboardingStatus}
              checklist={onboardingChecklist}
              saving={saving}
              onRecommend={() => void generateRecommendations()}
              onSubmitReview={() => void submitForReview()}
              onActivate={() => void approveAndActivate()}
            />

            {draft.is_default && (
              <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
                <CheckCircle2 size={16} />
                This profile will become the default for{" "}
                {systemLabel(draftSystem)}.
              </div>
            )}

            <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-bold text-ink-secondary">
              <input
                type="checkbox"
                checked={draft.is_default}
                onChange={(event) =>
                  updateDraft("is_default", event.target.checked)
                }
                className="size-4 accent-[var(--accent)]"
              />
              Use as default for this accounting system
            </label>
          </div>
        </section>
      </div>
    </div>
    </ContentCard>
  );
}

function postingModeLabel(mode: ProfilePostingMode) {
  return (
    postingModes.find((candidate) => candidate.value === mode)?.label ?? mode
  );
}

function onboardingStatusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: "Draft",
    samples_added: "Samples added",
    ready_for_admin_review: "Ready for review",
    active: "Active",
  };
  return labels[status] ?? humanizeToken(status || "draft");
}

function getOnboardingChecklist(
  profile: ClientProfilePayload,
  system: AccountingSystem,
): OnboardingChecklistItem[] {
  const settings = profile.settings;
  const trainingProfile = coerceTrainingProfile(settings.training_profile);
  const taxSettings = settings.tax_settings ?? {};
  const taxMode = (settings.tax_mode || "").toLowerCase();
  const isTally = system === "tally";
  const isItemInvoice = isInventoryPostingMode(settings.posting_mode);
  const expectedText = [
    trainingProfile.extraction_instructions,
    trainingProfile.posting_expectations,
    trainingProfile.validation_rules.join(" "),
  ]
    .join(" ")
    .toLowerCase();
  const usesTcs = expectedText.includes("tcs");
  const usesRoundOff =
    expectedText.includes("round off") ||
    expectedText.includes("round-off") ||
    expectedText.includes("roundoff");
  const usesGodown = expectedText.includes("godown");
  const taxLedgerReady =
    Boolean(settings.tax_ledger) ||
    Boolean(taxSettings.igst_ledger) ||
    (Boolean(taxSettings.cgst_ledger) && Boolean(taxSettings.sgst_ledger));

  const items: OnboardingChecklistItem[] = [
    {
      label: "Accounting system",
      detail: systemLabel(system),
      ready: Boolean(system),
      required: true,
    },
    {
      label: "Country and currency",
      detail: `${settings.country_code || "Country"} / ${settings.default_currency || "Currency"}`,
      ready: Boolean(settings.country_code && settings.default_currency),
      required: true,
    },
    {
      label: "Sample invoices",
      detail: `${trainingProfile.sample_invoices.length} uploaded`,
      ready: trainingProfile.sample_invoices.length > 0,
      required: false,
    },
    {
      label: "Parser instructions",
      detail: trainingProfile.extraction_instructions ? "Configured" : "Recommended",
      ready: Boolean(trainingProfile.extraction_instructions),
      required: false,
    },
  ];

  if (isTally) {
    items.push(
      {
        label: "Tally company",
        detail: settings.company_name || "Exact company name",
        ready: Boolean(settings.company_name),
        required: true,
      },
      {
        label: "Voucher setup",
        detail: `${settings.voucher_type || "Voucher"} / ${postingModeLabel(settings.posting_mode)}`,
        ready: Boolean(settings.voucher_type && settings.posting_mode),
        required: true,
      },
      {
        label: "Purchase ledger",
        detail: settings.purchase_ledger || "Exact ledger",
        ready: Boolean(settings.purchase_ledger),
        required: true,
      },
      {
        label: "Tax ledgers",
        detail: taxMode.includes("gst") ? "GST ledger mapping" : "Tax ledger mapping",
        ready: taxMode.includes("gst") ? taxLedgerReady : true,
        required: taxMode.includes("gst"),
      },
    );
    if (isItemInvoice) {
      items.push(
        {
          label: "Stock item",
          detail: settings.stock_item_name || "Exact Tally stock item",
          ready: Boolean(settings.stock_item_name || settings.item_mappings.length),
          required: true,
        },
        {
          label: "Stock UOM",
          detail: settings.stock_item_uom || "Exact Tally unit",
          ready: Boolean(settings.stock_item_uom),
          required: true,
        },
        {
          label: "HSN/SAC",
          detail: settings.stock_item_hsn || "Recommended for GST",
          ready: Boolean(settings.stock_item_hsn),
          required: false,
        },
      );
    }
    if (usesTcs) {
      items.push({
        label: "TCS ledger",
        detail: settings.tcs_ledger || "Exact TCS ledger",
        ready: Boolean(settings.tcs_ledger),
        required: true,
      });
    }
    if (usesRoundOff) {
      items.push({
        label: "Round-off ledger",
        detail: settings.round_off_ledger || "Exact round-off ledger",
        ready: Boolean(settings.round_off_ledger),
        required: true,
      });
    }
    if (usesGodown) {
      items.push({
        label: "Godown/location",
        detail: settings.godown_name || "Optional unless client uses godowns",
        ready: Boolean(settings.godown_name),
        required: false,
      });
    }
  }

  return items;
}

type ReadinessItem = {
  label: string;
  detail: string;
  ready: boolean;
  required: boolean;
};

type OnboardingChecklistItem = {
  label: string;
  detail: string;
  ready: boolean;
  required: boolean;
};

function OnboardingApprovalPanel({
  selectedProfile,
  status,
  checklist,
  saving,
  onRecommend,
  onSubmitReview,
  onActivate,
}: {
  selectedProfile: ClientProfile | null;
  status: string;
  checklist: OnboardingChecklistItem[];
  saving: boolean;
  onRecommend: () => void;
  onSubmitReview: () => void;
  onActivate: () => void;
}) {
  const blockers = checklist.filter((item) => item.required && !item.ready);
  const warnings = checklist.filter((item) => !item.required && !item.ready);
  const active = status === "active";

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex flex-col gap-4 border-b border-line px-4 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            Client onboarding
          </p>
          <h4 className="mt-1 text-lg font-black text-ink">
            Setup review and activation
          </h4>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-secondary">
            Confirm accounting setup, sample invoices, and posting rules before
            this profile is used for live recommendations or posting.
          </p>
        </div>
        <span
          className={cn(
            "inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-black",
            active
              ? "border-success/30 bg-success-soft text-success"
              : blockers.length
                ? "border-gold/30 bg-gold-soft text-gold"
                : "border-accent/30 bg-accent-soft text-accent-ink",
          )}
        >
          {active ? <ShieldCheck size={14} /> : <CircleDashed size={14} />}
          {onboardingStatusLabel(status)}
        </span>
      </div>

      <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
        {checklist.map((item) => (
          <div
            key={item.label}
            className="flex min-w-0 items-start gap-3 rounded-xl border border-line bg-canvas px-3 py-3"
          >
            <span
              className={cn(
                "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full",
                item.ready
                  ? "bg-success-soft text-success"
                  : item.required
                    ? "bg-gold-soft text-gold"
                    : "bg-surface-subtle text-ink-muted",
              )}
            >
              {item.ready ? <CheckCircle2 size={14} /> : <CircleDashed size={14} />}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-black text-ink">
                {item.label}
              </span>
              <span className="mt-0.5 block text-xs font-semibold leading-5 text-ink-secondary">
                {item.detail}
              </span>
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 border-t border-line bg-canvas px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <p className="text-sm font-semibold leading-6 text-ink-secondary">
          {blockers.length
            ? `${blockers.length} required setup item${blockers.length === 1 ? "" : "s"} missing.`
            : warnings.length
              ? `${warnings.length} optional improvement${warnings.length === 1 ? "" : "s"} remaining.`
              : "This profile is ready for live use."}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!selectedProfile || saving}
            onClick={onRecommend}
          >
            <Sparkles size={14} />
            Generate recommendations
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!selectedProfile || saving}
            onClick={onSubmitReview}
          >
            <BadgeCheck size={14} />
            Submit review
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={!selectedProfile || saving || blockers.length > 0}
            onClick={onActivate}
          >
            <ShieldCheck size={14} />
            Approve & activate
          </Button>
        </div>
      </div>
    </div>
  );
}

function AiReadinessPanel({
  aiStatus,
  aiStatusError,
  profileName,
  accountingSystem,
  countryCode,
  currency,
  trainingProfile,
}: {
  aiStatus: AiExtractionStatus | null;
  aiStatusError: string;
  profileName: string;
  accountingSystem: AccountingSystem;
  countryCode: string;
  currency: string;
  trainingProfile: ClientTrainingProfile;
}) {
  const readiness = getAiReadiness(
    aiStatus,
    trainingProfile,
    accountingSystem,
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex flex-col gap-4 border-b border-line px-4 py-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="flex min-w-0 gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent-ink">
            <Sparkles size={20} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              AI/OCR readiness
            </p>
            <h4 className="mt-1 truncate text-lg font-black text-ink">
              {profileName}
            </h4>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-secondary">
              Check whether this client profile has enough instructions,
              examples, and live-provider configuration for reliable AI
              extraction.
            </p>
          </div>
        </div>
        <span
          className={cn(
            "inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-black",
            readiness.blockers.length
              ? "border-gold/30 bg-gold-soft text-gold"
              : "border-success/30 bg-success-soft text-success",
          )}
        >
          {readiness.blockers.length ? (
            <AlertTriangle size={14} />
          ) : (
            <ShieldCheck size={14} />
          )}
          {readiness.statusLabel}
        </span>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_310px]">
        <div className="rounded-2xl border border-line bg-canvas p-4">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            Where this profile stands
          </p>
          <p className="mt-2 text-base font-black leading-7 text-ink">
            {readiness.headline}
          </p>
          <p className="mt-2 max-w-2xl text-sm font-semibold leading-6 text-ink-secondary">
            {readiness.summary}
          </p>

          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {readiness.items.map((item) => (
              <ReadinessChecklistItem key={item.label} item={item} />
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          <ReadinessMetric
            label="Provider"
            value={readiness.providerLabel}
            detail={readiness.providerDetail}
            tone={aiStatus?.configured ? "success" : "warning"}
          />
          <ReadinessMetric
            label="Training samples"
            value={`${trainingProfile.sample_invoices.length}`}
            detail="2 or more is recommended"
            tone={trainingProfile.sample_invoices.length >= 2 ? "success" : "default"}
          />
          <ReadinessMetric
            label="Fields"
            value={`${trainingProfile.expected_fields.length}`}
            detail={`${countryCode || "US"} / ${currency || "USD"} / ${systemLabel(accountingSystem)}`}
          />
          <ReadinessMetric
            label="AI policy"
            value={humanizeToken(trainingProfile.llm_policy || "review_only")}
            detail={trainingProfile.llm_ready ? "Approved for live use" : "Review before live use"}
            tone={trainingProfile.llm_ready ? "success" : "default"}
          />
        </div>
      </div>

      {(aiStatusError || readiness.blockers.length > 0) && (
        <div className="border-t border-line bg-canvas px-4 py-3">
          <p className="flex items-start gap-2 text-sm font-bold leading-6 text-ink-secondary">
            <AlertTriangle className="mt-0.5 shrink-0 text-gold" size={15} />
            <span>
              {aiStatusError
                ? aiStatusError
                : `Before live AI extraction: ${readiness.blockers.join(", ")}.`}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}

function ReadinessChecklistItem({ item }: { item: ReadinessItem }) {
  return (
    <div className="flex min-w-0 items-start gap-3 rounded-xl border border-line bg-surface px-3 py-3">
      <span
        className={cn(
          "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full",
          item.ready
            ? "bg-success-soft text-success"
            : item.required
              ? "bg-gold-soft text-gold"
              : "bg-canvas text-ink-muted",
        )}
      >
        {item.ready ? <CheckCircle2 size={14} /> : <CircleDashed size={14} />}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-black leading-5 text-ink">
          {item.label}
        </span>
        <span className="mt-0.5 block text-xs font-semibold leading-5 text-ink-secondary">
          {item.detail}
        </span>
      </span>
    </div>
  );
}

function ReadinessMetric({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "success" | "warning";
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border bg-canvas px-4 py-3",
        tone === "success" && "border-success/30 bg-success-soft",
        tone === "warning" && "border-gold/30 bg-gold-soft",
        tone === "default" && "border-line",
      )}
    >
      <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </p>
      <p className="mt-1 truncate text-base font-black text-ink">{value}</p>
      <p className="mt-1 truncate text-xs font-bold text-ink-secondary">
        {detail}
      </p>
    </div>
  );
}

function getAiReadiness(
  aiStatus: AiExtractionStatus | null,
  trainingProfile: ClientTrainingProfile,
  accountingSystem: AccountingSystem,
) {
  const samples = trainingProfile.sample_invoices ?? [];
  const hasInstructions =
    trainingProfile.extraction_instructions.trim().length > 0;
  const hasValidationRules = trainingProfile.validation_rules.length > 0;
  const hasPostingExpectations =
    trainingProfile.posting_expectations.trim().length > 0;
  const providerConfigured = Boolean(aiStatus?.configured);

  const items: ReadinessItem[] = [
    {
      label: "AI/OCR provider",
      detail: providerConfigured
        ? `${formatProvider(aiStatus?.provider)} configured`
        : "Configure webhook or provider credentials",
      ready: providerConfigured,
      required: true,
    },
    {
      label: "Sample invoices",
      detail:
        samples.length >= 2
          ? `${samples.length} samples uploaded`
          : "Upload at least 2 real samples",
      ready: samples.length >= 2,
      required: true,
    },
    {
      label: "Expected fields",
      detail:
        trainingProfile.expected_fields.length >= 7
          ? `${trainingProfile.expected_fields.length} fields selected`
          : "Select core header and line fields",
      ready: trainingProfile.expected_fields.length >= 7,
      required: true,
    },
    {
      label: "Extraction guidance",
      detail: hasInstructions
        ? "Client-specific parsing notes saved"
        : "Add where fields appear on this client's invoices",
      ready: hasInstructions,
      required: false,
    },
    {
      label: "Validation rules",
      detail: hasValidationRules
        ? `${trainingProfile.validation_rules.length} rules saved`
        : "Add total, tax, item, or vendor checks",
      ready: hasValidationRules,
      required: false,
    },
    {
      label: "Posting expectations",
      detail: hasPostingExpectations
        ? "ERP behavior is documented"
        : `Define ${systemLabel(accountingSystem)} posting expectations`,
      ready: hasPostingExpectations,
      required: false,
    },
    {
      label: "Policy approval",
      detail: trainingProfile.llm_ready
        ? "Approved for live AI use"
        : "Keep in review mode until approved",
      ready: trainingProfile.llm_ready,
      required: false,
    },
  ];

  const readyItems = items.filter((item) => item.ready).length;
  const score = Math.round((readyItems / items.length) * 100);
  const blockers = items
    .filter((item) => item.required && !item.ready)
    .map((item) => item.label.toLowerCase());
  // Recommended items improve accuracy but never block AI use. They are
  // surfaced as plain suggestions rather than folded into a percentage.
  const recommendations = items
    .filter((item) => !item.required && !item.ready && item.label !== "Policy approval")
    .map((item) => item.label.toLowerCase());

  const providerLabel = aiStatus
    ? formatProvider(aiStatus.provider)
    : "Checking status";
  const providerDetail = aiStatus
    ? aiStatus.live_provider
      ? `${humanizeToken(aiStatus.policy)} / live`
      : `${humanizeToken(aiStatus.mode)} mode`
    : "Waiting for backend";

  const headline = blockers.length
    ? `AI extraction is not ready yet — ${joinNaturally(blockers)} ${blockers.length === 1 ? "is" : "are"} still missing.`
    : recommendations.length
      ? `AI extraction is ready for testing. ${recommendations.length} optional item${recommendations.length === 1 ? "" : "s"} would improve accuracy: ${joinNaturally(recommendations)}.`
      : trainingProfile.llm_ready
        ? "AI extraction is fully set up and approved for live use."
        : "AI extraction is fully set up. Keep it in review until you have approved a few extractions, then switch the policy to live.";

  return {
    items,
    score,
    blockers,
    recommendations,
    providerLabel,
    providerDetail,
    statusLabel: blockers.length
      ? "Needs setup"
      : recommendations.length
        ? "Ready for testing"
        : "Ready for live AI",
    headline,
    summary: blockers.length
      ? "Deterministic parsing still works. Live AI extraction stays in review until the missing setup is complete."
      : "Every extraction for this client is sent with these instructions and samples as context.",
  };
}

function joinNaturally(parts: string[]) {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

function formatProvider(provider?: string) {
  if (!provider || provider === "disabled") return "Disabled";
  if (provider === "profile_context") return "Profile context";
  if (provider === "webhook") return "External webhook";
  return humanizeToken(provider);
}

function humanizeToken(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function Pill({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-canvas px-2.5 py-1 text-xs font-black text-ink-secondary">
      <span className="shrink-0 text-accent dark:text-cyan">{icon}</span>
      <span className="truncate">{children}</span>
    </span>
  );
}

function MiniChip({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "accent";
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.08em]",
        tone === "accent"
          ? "border-accent/30 bg-accent-soft text-accent-ink"
          : "border-line bg-canvas text-ink-muted",
      )}
    >
      <span className="truncate">{children}</span>
    </span>
  );
}

function connectionText(
  settings: Record<string, unknown>,
  key: string,
  fallback = "",
) {
  const value = settings[key];
  return typeof value === "string" ? value : fallback;
}

function connectionBool(
  settings: Record<string, unknown>,
  key: string,
  fallback = false,
) {
  const value = settings[key];
  return typeof value === "boolean" ? value : fallback;
}

function renderConnectionFields(
  system: AccountingSystem,
  settings: Record<string, unknown>,
  onChange: (key: string, value: string | boolean) => void,
) {
  if (system === "tally") {
    return (
      <div className="space-y-4">
        <FormGrid>
          <TextField
            label="Connector URL"
            value={connectionText(
              settings,
              "connector_url",
              "http://127.0.0.1:8765",
            )}
            onChange={(value) => onChange("connector_url", value)}
            placeholder="http://127.0.0.1:8765"
          />
          <TextField
            label="Workspace ID"
            value={connectionText(settings, "workspace_id", "local-workspace")}
            onChange={(value) => onChange("workspace_id", value)}
            placeholder="local-workspace"
          />
          <TextField
            label="Connector token"
            value={connectionText(settings, "connector_token")}
            onChange={(value) => onChange("connector_token", value)}
            placeholder="Local test token"
          />
          <TextField
            label="Tally URL"
            value={connectionText(settings, "tally_url", "http://localhost:9000")}
            onChange={(value) => onChange("tally_url", value)}
            placeholder="http://localhost:9000"
          />
        </FormGrid>
        <CheckboxField
          label="Use local connector for posting"
          checked={connectionBool(settings, "connector_enabled", true)}
          onChange={(value) => onChange("connector_enabled", value)}
        />
      </div>
    );
  }

  if (system === "quickbooks") {
    return (
      <FormGrid>
        <TextField
          label="Environment"
          value={connectionText(settings, "environment", "sandbox")}
          onChange={(value) => onChange("environment", value)}
          placeholder="sandbox"
        />
        <TextField
          label="Redirect URI"
          value={connectionText(
            settings,
            "redirect_uri",
            "http://localhost:8000/callback",
          )}
          onChange={(value) => onChange("redirect_uri", value)}
          placeholder="http://localhost:8000/callback"
        />
        <TextField
          label="Realm ID"
          value={connectionText(settings, "realm_id")}
          onChange={(value) => onChange("realm_id", value)}
          placeholder="Filled after OAuth"
        />
        <TextField
          label="OAuth status"
          value={connectionText(settings, "oauth_status", "not_connected")}
          onChange={(value) => onChange("oauth_status", value)}
          placeholder="not_connected"
        />
      </FormGrid>
    );
  }

  if (system === "zoho_books") {
    return (
      <FormGrid>
        <TextField
          label="Environment"
          value={connectionText(settings, "environment", "sandbox")}
          onChange={(value) => onChange("environment", value)}
          placeholder="sandbox"
        />
        <TextField
          label="Region"
          value={connectionText(settings, "region", "com")}
          onChange={(value) => onChange("region", value)}
          placeholder="com, in, eu"
        />
        <TextField
          label="Organization ID"
          value={connectionText(settings, "organization_id")}
          onChange={(value) => onChange("organization_id", value)}
          placeholder="Zoho Books organization"
        />
        <TextField
          label="OAuth status"
          value={connectionText(settings, "oauth_status", "not_connected")}
          onChange={(value) => onChange("oauth_status", value)}
          placeholder="not_connected"
        />
      </FormGrid>
    );
  }

  return (
    <FormGrid>
      <TextField
        label="Package format"
        value={connectionText(settings, "package_format", "json")}
        onChange={(value) => onChange("package_format", value)}
        placeholder="json, csv, xml"
      />
      <TextField
        label="Template name"
        value={connectionText(settings, "template_name")}
        onChange={(value) => onChange("template_name", value)}
        placeholder="Client import template"
      />
    </FormGrid>
  );
}

function systemLabel(system: AccountingSystem) {
  return (
    accountingSystems.find((candidate) => candidate.value === system)?.label ??
    system
  );
}

function normalizeImportedProfile(
  imported: unknown,
  lockedSystem?: AccountingSystem,
): ClientProfilePayload {
  const rawContainer = asRecord(imported);
  const raw = asRecord(rawContainer?.profile) ?? rawContainer;
  if (!raw) throw new Error("The selected file is not a client profile JSON.");

  const rawSystem = stringValue(raw.accounting_system);
  const accountingSystem = lockedSystem ?? rawSystem;
  if (!isAccountingSystem(accountingSystem)) {
    throw new Error("Imported profile is missing a supported accounting system.");
  }
  if (lockedSystem && rawSystem && rawSystem !== lockedSystem) {
    throw new Error(
      `This page only accepts ${systemLabel(lockedSystem)} profiles.`,
    );
  }

  const settings = asRecord(raw.settings) ?? {};
  const itemMappings = Array.isArray(settings.item_mappings)
    ? settings.item_mappings.filter(isRecord)
    : [];

  return {
    name: stringValue(raw.name) || "Imported client profile",
    accounting_system: accountingSystem,
    description: stringValue(raw.description),
    is_default: false,
    settings: {
      ...defaultSettings(),
      ...(settings as Partial<ClientProfileSettings>),
      connection_settings: asRecord(settings.connection_settings) ?? {},
      tax_settings: asRecord(settings.tax_settings) ?? {},
      training_profile: coerceTrainingProfile(settings.training_profile),
      metadata: asRecord(settings.metadata) ?? {},
      item_mappings: itemMappings.map((mapping) => ({
        ...emptyMapping,
        ...mapping,
      })) as ClientProfileItemMapping[],
    },
  };
}

function downloadProfileJson(profile: ClientProfilePayload, name: string) {
  const payload = {
    exported_at: new Date().toISOString(),
    schema: "siftentry.client_profile.v1",
    profile: {
      ...profile,
      is_default: false,
    },
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugify(name)}.client-profile.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function isAccountingSystem(value: string): value is AccountingSystem {
  return accountingSystems.some((system) => system.value === value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(asRecord(value));
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function slugify(value: string) {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  return slug || "client-profile";
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 KB";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-bold text-ink-secondary">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 accent-[var(--accent)]"
      />
      {label}
    </label>
  );
}

function FormGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{children}</div>;
}

function SettingsPanel({
  title,
  detail,
  children,
  defaultOpen = false,
}: {
  title: string;
  detail: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="group overflow-hidden rounded-2xl border border-line bg-surface"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 transition-colors hover:bg-surface-subtle">
        <span className="min-w-0">
          <span className="block text-sm font-black text-ink">{title}</span>
          <span className="mt-1 block text-sm leading-5 text-ink-secondary">
            {detail}
          </span>
        </span>
        <span className="grid size-9 shrink-0 place-items-center rounded-full border border-line bg-canvas text-ink-secondary transition-transform group-open:rotate-180">
          <ChevronDown size={16} />
        </span>
      </summary>
      <div className="border-t border-line p-4">{children}</div>
    </details>
  );
}

function TrainingProfileSection({
  selectedProfile,
  trainingProfile,
  sampleFile,
  sampleNotes,
  uploading,
  onUpdate,
  onToggleField,
  onFileChange,
  onNotesChange,
  onUpload,
}: {
  selectedProfile: ClientProfile | null;
  trainingProfile: ClientTrainingProfile;
  sampleFile: File | null;
  sampleNotes: string;
  uploading: boolean;
  onUpdate: (patch: Partial<ClientTrainingProfile>) => void;
  onToggleField: (field: string) => void;
  onFileChange: (file: File | null) => void;
  onNotesChange: (value: string) => void;
  onUpload: () => void;
}) {
  const samples = trainingProfile.sample_invoices ?? [];
  const readiness = [
    {
      label: "Setup",
      ready: Boolean(trainingProfile.business_process),
      detail: "Process selected",
    },
    {
      label: "Samples",
      ready: samples.length > 0,
      detail: `${samples.length} uploaded`,
    },
    {
      label: "Rules",
      ready:
        trainingProfile.extraction_instructions.trim().length > 0 ||
        trainingProfile.validation_rules.length > 0,
      detail: "Parser guidance",
    },
    {
      label: "LLM",
      ready: trainingProfile.llm_ready,
      detail: trainingProfile.llm_ready ? "Ready" : "Needs review",
    },
  ];
  const sampleInputId = `training-sample-${selectedProfile?.id ?? "new"}`;

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex flex-col gap-4 border-b border-line px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            <BrainCircuit size={15} className="text-accent dark:text-cyan" />
            Client learning context
          </div>
          <h4 className="mt-2 text-lg font-black text-ink">
            Onboarding profile
          </h4>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-secondary">
            Capture the client format, sample invoices, and posting rules the
            parser should use when recommending extraction and ERP payloads.
          </p>
        </div>
        <span className="inline-flex w-fit items-center rounded-full border border-line bg-canvas px-3 py-1.5 text-xs font-black text-ink-secondary">
          {trainingProfile.onboarding_status || "draft"}
        </span>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-line px-4 py-3">
        {readiness.map((step) => (
          <div
            key={step.label}
            className="inline-flex min-w-0 items-center gap-2 rounded-full border border-line bg-canvas px-3 py-1.5"
          >
            <span
              className={cn(
                "size-2.5 shrink-0 rounded-full",
                step.ready ? "bg-success" : "bg-ink-muted/35",
              )}
            />
            <span className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
              {step.label}
            </span>
            <span className="truncate text-xs font-black text-ink">
              {step.detail}
            </span>
          </div>
        ))}
      </div>

      <div className="space-y-5 p-4">
        <div className="grid gap-4 lg:grid-cols-3">
          <SelectField
            label="Business process"
            value={trainingProfile.business_process}
            options={businessProcesses}
            onChange={(value) => onUpdate({ business_process: value })}
          />
          <TextField
            label="Monthly invoice volume"
            value={trainingProfile.invoice_volume}
            onChange={(value) => onUpdate({ invoice_volume: value })}
            placeholder="Example: 250 invoices/month"
          />
          <SelectField
            label="AI policy"
            value={trainingProfile.llm_policy}
            options={llmPolicies}
            onChange={(value) => onUpdate({ llm_policy: value })}
          />
        </div>

        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
            Expected fields
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {expectedFieldOptions.map((field) => {
              const checked = trainingProfile.expected_fields.includes(
                field.value,
              );
              return (
                <label
                  key={field.value}
                  className={cn(
                    "flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm font-bold transition-colors",
                    checked
                      ? "border-accent/45 bg-accent-soft text-accent-ink"
                      : "border-line bg-canvas text-ink-secondary hover:border-accent/50",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleField(field.value)}
                    className="size-4 shrink-0 accent-[var(--accent)]"
                  />
                  <span className="min-w-0 leading-5">{field.label}</span>
                </label>
              );
            })}
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <TextAreaField
            label="Extraction instructions"
            value={trainingProfile.extraction_instructions}
            onChange={(value) =>
              onUpdate({ extraction_instructions: value })
            }
            hint="Describe where things sit on this client's invoices — e.g. which block holds the supplier name, and which total to use. Two or three sentences is plenty."
            status={{
              ready: trainingProfile.extraction_instructions.trim().length > 0,
              readyText: "Sent with every extraction",
              emptyText: "Optional · improves accuracy",
            }}
            wide
          />
          <TextAreaField
            label="Validation rules"
            value={trainingProfile.validation_rules.join("\n")}
            onChange={(value) =>
              onUpdate({
                validation_rules: value
                  .split("\n")
                  .map((line) => line.trim())
                  .filter(Boolean),
              })
            }
            hint="One check per line, in plain words — e.g. line totals must add up to the subtotal."
            status={{
              ready: trainingProfile.validation_rules.length > 0,
              readyText: `${trainingProfile.validation_rules.length} rule${trainingProfile.validation_rules.length === 1 ? "" : "s"} active`,
              emptyText: "Optional · improves accuracy",
            }}
          />
          <TextAreaField
            label="Posting expectations"
            value={trainingProfile.posting_expectations}
            onChange={(value) => onUpdate({ posting_expectations: value })}
            hint="How entries should land in the accounting system — anything the ledger fields above don't already capture."
            status={{
              ready: trainingProfile.posting_expectations.trim().length > 0,
              readyText: "Sent with every extraction",
              emptyText: "Optional · improves accuracy",
            }}
          />
          <TextAreaField
            label="Exception examples"
            value={trainingProfile.exception_examples}
            onChange={(value) => onUpdate({ exception_examples: value })}
            hint="Known quirks: a supplier whose invoices arrive in a different layout, fields that usually need a manual check."
            status={{
              ready: trainingProfile.exception_examples.trim().length > 0,
              readyText: "Saved",
              emptyText: "Optional",
            }}
            wide
          />
        </div>

        <div className="rounded-2xl border border-line bg-canvas p-4">
          <div className="grid gap-4 xl:grid-cols-[minmax(240px,320px)_minmax(0,1fr)] xl:items-end">
            <label className="min-w-0">
              <span className="mb-2 block text-[11px] font-extrabold uppercase text-ink-muted">
                Sample invoice
              </span>
              <span className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink transition-colors hover:border-accent hover:bg-accent-soft">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-white">
                  <Upload size={15} />
                </span>
                <span className="min-w-0 flex-1 truncate">
                  {sampleFile ? sampleFile.name : "Choose PDF"}
                </span>
              </span>
              <input
                id={sampleInputId}
                key={sampleFile ? sampleFile.name : "empty-training-sample"}
                type="file"
                accept="application/pdf"
                onChange={(event) =>
                  onFileChange(event.target.files?.[0] ?? null)
                }
                className="sr-only"
              />
            </label>
            <TextField
              label="Sample notes"
              value={sampleNotes}
              onChange={onNotesChange}
              placeholder="Vendor, tax format, special fields"
            />
          </div>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {!selectedProfile ? (
              <p className="text-xs font-bold text-gold">
                Save this client profile once before attaching sample invoices.
              </p>
            ) : (
              <p className="text-xs font-semibold text-ink-secondary">
                Add 2-3 real examples so SiftEntry can recommend parser, tax,
                and posting settings for this client.
              </p>
            )}
            <Button
              type="button"
              variant="primary"
              className="h-11 w-full shrink-0 whitespace-nowrap sm:w-auto sm:min-w-[180px]"
              disabled={!selectedProfile || !sampleFile || uploading}
              onClick={onUpload}
            >
              {uploading ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <Upload size={15} />
              )}
              Upload sample
            </Button>
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink-muted">
              Uploaded samples
            </p>
            <span className="rounded-full border border-line bg-canvas px-2.5 py-1 text-xs font-black text-ink-secondary">
              {samples.length}
            </span>
          </div>
          {samples.length ? (
            <div className="grid gap-2 xl:grid-cols-2">
              {samples.slice(0, 6).map((sample) => (
                <div
                  key={sample.id || sample.filename}
                  className="flex min-w-0 items-start gap-3 rounded-xl border border-line bg-canvas px-3 py-3"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
                    <FileText size={16} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-black text-ink">
                      {sample.filename || "Sample invoice"}
                    </span>
                    <span className="mt-1 block truncate text-xs font-bold text-ink-secondary">
                      {formatBytes(sample.size_bytes)} /{" "}
                      {sample.status || "uploaded"}
                    </span>
                    {sample.notes && (
                      <span className="mt-1 block truncate text-xs font-semibold text-ink-muted">
                        {sample.notes}
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-line-strong bg-canvas px-4 py-5 text-sm font-semibold text-ink-secondary">
              Add two or three real invoice examples per client to make parser
              recommendations and future LLM extraction more accurate.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  optional = false,
  wide = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Plain-language guidance shown under the input. Prefer this over
   *  example-style placeholders, which read as already-filled values. */
  hint?: string;
  optional?: boolean;
  wide?: boolean;
}) {
  return (
    <label className={cn("block", wide && "md:col-span-2 xl:col-span-full")}>
      <span className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
        {optional && (
          <span className="ml-1.5 font-bold normal-case tracking-normal text-ink-muted/70">
            · optional
          </span>
        )}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
      />
      {hint && (
        <span className="mt-1.5 block text-xs font-semibold leading-5 text-ink-muted">
          {hint}
        </span>
      )}
    </label>
  );
}

function FieldGroup({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-line bg-canvas p-4">
      <p className="text-sm font-black text-ink">{title}</p>
      <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
        {detail}
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{children}</div>
    </div>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  status,
  wide = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** What this field does for the user, in plain language. */
  hint?: string;
  /** Inline status: what the AI does with this field right now. */
  status?: { ready: boolean; readyText: string; emptyText: string };
  wide?: boolean;
}) {
  return (
    <label className={cn("block", wide && "md:col-span-2 xl:col-span-full")}>
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] font-extrabold uppercase text-ink-muted">
          {label}
        </span>
        {status && (
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-black",
              status.ready
                ? "bg-success-soft text-success"
                : "bg-surface-subtle text-ink-muted",
            )}
          >
            {status.ready ? <CheckCircle2 size={12} /> : <CircleDashed size={12} />}
            {status.ready ? status.readyText : status.emptyText}
          </span>
        )}
      </span>
      {hint && (
        <span className="mt-1 block text-xs font-semibold leading-5 text-ink-muted">
          {hint}
        </span>
      )}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={4}
        className="mt-2 min-h-28 w-full resize-y rounded-xl border border-line-strong bg-surface px-3 py-3 text-sm font-bold leading-6 text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
      />
    </label>
  );
}

function SelectField<TValue extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: TValue;
  options: { label: string; value: TValue }[];
  onChange: (value: TValue) => void;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as TValue)}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors focus:border-accent"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
