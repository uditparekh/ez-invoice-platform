"use client";

import {
  ArrowRight,
  BadgeCheck,
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
import {
  type ChangeEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { useAuth } from "@/components/auth-provider";
import { ProfileConnectionStatus } from "@/components/profile-connection-status";
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

const profileSections = [
  { id: "company", label: "Company" },
  { id: "connection", label: "Connection" },
  { id: "posting", label: "Posting rules" },
  { id: "extraction", label: "Extraction guidance" },
  { id: "samples", label: "Samples & checks" },
] as const;
type ProfileSection = (typeof profileSections)[number]["id"];

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
  if (!value || options.some((option) => option.value === value))
    return options;
  return [{ label: `Custom (${value})`, value }, ...options];
}

interface ClientProfilesPanelProps {
  accountingSystem?: AccountingSystem;
  title?: string;
  subtitle?: string;
  showSystemField?: boolean;
}

export function ClientProfilesPanel(props: ClientProfilesPanelProps = {}) {
  const { activeOrganizationId } = useAuth();
  return (
    <ProfileEditor key={activeOrganizationId ?? "no-workspace"} {...props} />
  );
}

function ProfileEditor({
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
  const { user, activeOrganizationId } = useAuth();
  const role = user?.memberships.find(
    (membership) => membership.organization_id === activeOrganizationId,
  )?.role;
  const canEdit = ["owner", "admin", "accountant"].includes(role ?? "");
  const canManage = ["owner", "admin"].includes(role ?? "");
  const editorId = useId();
  const [activeSection, setActiveSection] = useState<ProfileSection>("company");
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
    if (
      loading ||
      selectedId ||
      preserveBlankDraftRef.current ||
      !profiles.length
    ) {
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
    const trainingProfile = coerceTrainingProfile(
      draft.settings.training_profile,
    );
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
    if (saving || trainingUploading) return;
    if (!allowDiscard()) return;
    setActiveSection("company");
    preserveBlankDraftRef.current = true;
    setSelectedId(null);
    setDraft(blankProfile(accountingSystem ?? "tally"));
    setNotice("");
    setTrainingSampleFile(null);
    setTrainingSampleNotes("");
  }

  function selectProfile(profile: ClientProfile) {
    if (saving || trainingUploading) return;
    if (!allowDiscard()) return;
    setActiveSection("company");
    preserveBlankDraftRef.current = false;
    setSelectedId(profile.id);
    setDraft(profileToPayload(profile));
    setNotice("");
    setTrainingSampleFile(null);
    setTrainingSampleNotes("");
  }

  function useIndiaGstItemTemplate() {
    if (saving || trainingUploading) return;
    if (!allowDiscard()) return;
    setActiveSection("company");
    preserveBlankDraftRef.current = true;
    setSelectedId(null);
    setDraft(indiaGstItemInvoiceTemplate());
    setNotice(
      "India GST item-invoice template loaded. Add the client's exact Tally names before saving.",
    );
  }

  async function saveProfile() {
    if (!canEdit) return;
    if (
      onboardingStatus === "active" &&
      isDirty &&
      !window.confirm(
        "Save changes to this active profile? They apply immediately to future processing. Existing invoice approval is not a frozen posting plan yet.",
      )
    )
      return;
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
      setDraft(profileToPayload(saved));
      setNotice("Client profile saved.");
    } catch (saveError) {
      setNotice((saveError as Error).message);
    }
  }

  async function uploadTrainingSampleAction() {
    if (!requireSaved()) return;
    setNotice("");
    if (!selectedProfile) {
      setNotice("Save the client profile before uploading sample invoices.");
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
      setNotice("Sample invoice uploaded.");
    } catch (uploadError) {
      setNotice((uploadError as Error).message);
    } finally {
      setTrainingUploading(false);
    }
  }

  async function importProfile(event: ChangeEvent<HTMLInputElement>) {
    if (saving || trainingUploading) return;
    const file = event.target.files?.[0];
    if (!file) return;
    if (!allowDiscard()) {
      event.target.value = "";
      return;
    }
    preserveBlankDraftRef.current = true;
    setActiveSection("company");
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
    if (!requireSaved()) return;
    if (!selectedProfile) return;
    setNotice("");
    try {
      const updated = await setDefaultProfile(selectedProfile.id);
      setDraft(profileToPayload(updated));
      setNotice("Default profile updated.");
    } catch (defaultError) {
      setNotice((defaultError as Error).message);
    }
  }

  async function submitForReview() {
    if (!requireSaved()) return;
    if (!selectedProfile) {
      setNotice(
        "Save the client profile before submitting it for admin review.",
      );
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
    if (!requireSaved()) return;
    if (!selectedProfile) {
      setNotice("Save the client profile before generating recommendations.");
      return;
    }
    if (
      !window.confirm(
        "Apply suggested setup values to the saved profile? This can change parser and posting settings. Review all changes before processing invoices.",
      )
    )
      return;
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
    if (!requireSaved()) return;
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
  const trainingProfile = coerceTrainingProfile(
    draft.settings.training_profile,
  );
  const onboardingChecklist = getOnboardingChecklist(draft, draftSystem);
  const onboardingStatus = trainingProfile.onboarding_status || "draft";
  const isDirty =
    JSON.stringify(draft) !==
    JSON.stringify(
      selectedProfile
        ? profileToPayload(selectedProfile)
        : blankProfile(accountingSystem ?? "tally"),
    );

  useEffect(() => {
    if (!isDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  function allowDiscard() {
    return !isDirty || window.confirm("Discard unsaved profile changes?");
  }
  function requireSaved() {
    if (!isDirty) return true;
    setNotice(
      "Save your changes before continuing. This action uses the saved profile.",
    );
    return false;
  }

  return (
    <ContentCard
      title={title}
      subtitle={subtitle}
      action={
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={newProfile} disabled={!canEdit || saving}>
            <Plus size={14} />
            New profile
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!canEdit || saving}
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
              disabled={!canEdit || saving}
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
      <div className="space-y-5" data-profile-editor>
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
                libraryCollapsed
                  ? "justify-between xl:flex-col xl:items-center"
                  : "justify-between",
              )}
            >
              {!libraryCollapsed && (
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
                    Profile library
                  </p>
                  <h3 className="mt-1 text-base font-semibold text-ink">
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
                  className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink-secondary"
                  title={`${filteredProfiles.length} profile${filteredProfiles.length === 1 ? "" : "s"}`}
                >
                  {filteredProfiles.length}
                </span>
                <button
                  type="button"
                  onClick={() => toggleLibrary()}
                  aria-expanded={!libraryCollapsed}
                  aria-controls="profile-library-list"
                  title={
                    libraryCollapsed
                      ? "Expand profile library"
                      : "Collapse profile library"
                  }
                  className="grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-surface text-ink-secondary transition-colors hover:border-accent hover:text-accent-ink"
                >
                  <span className="hidden xl:block">
                    {libraryCollapsed ? (
                      <PanelLeftOpen size={16} />
                    ) : (
                      <PanelLeftClose size={16} />
                    )}
                  </span>
                  <span className="xl:hidden">
                    {libraryCollapsed ? (
                      <ChevronDown size={16} />
                    ) : (
                      <ChevronUp size={16} />
                    )}
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
                    aria-current={
                      selectedId === profile.id ? "true" : undefined
                    }
                    className={cn(
                      "grid size-10 place-items-center rounded-xl border text-xs font-semibold uppercase transition-colors",
                      selectedId === profile.id
                        ? "border-accent bg-accent-soft text-accent-ink"
                        : "border-line bg-surface text-ink-secondary hover:border-accent hover:text-accent-ink",
                    )}
                  >
                    {profile.accounting_system.slice(0, 2)}
                  </button>
                ))}
              </div>
            ) : (
              <div id="profile-library-list">
                <label className="mt-4 flex h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink-secondary">
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
                    <div className="rounded-2xl border border-line bg-surface px-4 py-6 text-sm font-medium text-ink-secondary">
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
                          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-xs font-semibold uppercase text-accent-ink">
                            {profile.accounting_system.slice(0, 2)}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-ink">
                              {profile.name}
                            </span>
                            <span className="mt-1 block truncate text-xs font-medium text-ink-muted">
                              {systemLabel(profile.accounting_system)} /{" "}
                              {profile.settings.company_name ||
                                "Company not set"}
                            </span>
                            <span className="mt-2 flex flex-wrap gap-1.5">
                              <MiniChip>
                                {profile.settings.default_currency || "USD"}
                              </MiniChip>
                              <MiniChip>
                                {postingModeLabel(
                                  profile.settings.posting_mode,
                                )}
                              </MiniChip>
                              {profile.is_default && (
                                <MiniChip tone="accent">Default</MiniChip>
                              )}
                            </span>
                          </span>
                          {profile.is_default && (
                            <Star
                              size={16}
                              className="shrink-0 fill-accent text-accent-ink"
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

          <section className="min-w-0 overflow-hidden rounded-2xl border border-line bg-canvas">
            <div className="flex flex-col gap-4 border-b border-line bg-surface px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
                  {selectedProfile ? "Editing profile" : "New profile"}
                </p>
                <h3 className="mt-1 break-words text-xl font-semibold text-ink">
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
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={makeDefault}
                    disabled={!canManage || isDirty || saving}
                  >
                    <BadgeCheck size={14} />
                    Set default
                  </Button>
                )}
                {selectedProfile && (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={removeProfile}
                    disabled={!canManage || saving}
                  >
                    <Trash2 size={14} />
                    Delete
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="primary"
                  onClick={saveProfile}
                  disabled={!canEdit || saving || trainingUploading}
                >
                  {saving ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Save size={14} />
                  )}
                  {onboardingStatus === "active"
                    ? "Save changes"
                    : "Save draft"}
                </Button>
              </div>
            </div>

            {(notice || error) && (
              <div
                className={cn(
                  "mx-5 mt-5 rounded-xl border px-4 py-3 text-sm font-medium",
                  notice === "Client profile saved." ||
                    notice === "Default profile updated." ||
                    notice === "Client profile deleted."
                    ? "border-success/30 bg-success-soft text-success"
                    : "border-gold/30 bg-gold-soft text-gold",
                )}
              >
                <span role="status" aria-live="polite">
                  {notice || error}
                </span>
              </div>
            )}

            <nav
              aria-label="Profile sections"
              className="border-b border-line bg-surface p-3 sm:p-4"
            >
              <div
                role="tablist"
                aria-label="Client profile setup"
                className="grid grid-cols-2 gap-2 lg:grid-cols-5"
              >
                {profileSections.map((section, index) => (
                  <button
                    key={section.id}
                    type="button"
                    role="tab"
                    id={`${editorId}-tab-${section.id}`}
                    aria-controls={`${editorId}-panel-${section.id}`}
                    aria-selected={activeSection === section.id}
                    tabIndex={activeSection === section.id ? 0 : -1}
                    onClick={() => setActiveSection(section.id)}
                    onKeyDown={(event) => {
                      const next =
                        event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? profileSections.length - 1
                            : event.key === "ArrowRight"
                              ? (index + 1) % profileSections.length
                              : event.key === "ArrowLeft"
                                ? (index + profileSections.length - 1) %
                                  profileSections.length
                                : -1;
                      if (next < 0) return;
                      event.preventDefault();
                      setActiveSection(profileSections[next].id);
                      document
                        .getElementById(
                          `${editorId}-tab-${profileSections[next].id}`,
                        )
                        ?.focus();
                    }}
                    className={cn(
                      "min-h-12 rounded-xl border px-3 py-2 text-left text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                      activeSection === section.id
                        ? "border-accent/40 bg-accent-soft text-accent-ink"
                        : "border-transparent text-ink-secondary hover:bg-canvas",
                    )}
                  >
                    <span className="mb-0.5 block text-xs opacity-70">
                      0{index + 1}
                    </span>
                    {section.label}
                  </button>
                ))}
              </div>
            </nav>
            <fieldset
              disabled={!canEdit || loading || saving || trainingUploading}
              className="min-w-0"
            >
              <legend className="sr-only">Client profile configuration</legend>
              <div
                className="space-y-5 p-3 sm:p-5"
                role="tabpanel"
                id={`${editorId}-panel-company`}
                aria-labelledby={`${editorId}-tab-company`}
                hidden={activeSection !== "company"}
              >
                <div className="rounded-2xl border border-line bg-surface p-4">
                  <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
                        Company
                      </p>
                      <h4 className="mt-1 text-lg font-semibold text-ink">
                        Identity & accounting destination
                      </h4>
                    </div>
                    <span className="w-fit rounded-full border border-line bg-canvas px-3 py-1 text-xs font-semibold text-ink-secondary">
                      {draft.settings.default_currency || "USD"} /{" "}
                      {draft.settings.country_code || "US"}
                    </span>
                  </div>
                  <FormGrid>
                    <TextField
                      label="Profile name"
                      wide
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
                          if (
                            selectedProfile &&
                            nextSystem !== draft.accounting_system &&
                            !window.confirm(
                              "Change accounting destination? Connection settings and entry type will reset for the new system. Other saved values stay in this form; review them before saving.",
                            )
                          )
                            return;
                          const nextDefaults =
                            blankProfile(nextSystem).settings;
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
                      wide
                      unverified={draftSystem === "tally"}
                      value={draft.settings.company_name}
                      onChange={(value) =>
                        updateSettings("company_name", value)
                      }
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
                  title="Country, currency & tax"
                  detail="Defaults for this company. These are configuration values, not evidence extracted from an invoice."
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
                      onChange={(value) =>
                        updateSettings("country_name", value)
                      }
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

                {draft.is_default && (
                  <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-medium text-success">
                    <CheckCircle2 size={16} />
                    This profile will become the default for{" "}
                    {systemLabel(draftSystem)}.
                  </div>
                )}

                <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-medium text-ink-secondary">
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
              <div
                className="space-y-5 p-3 sm:p-5"
                role="tabpanel"
                id={`${editorId}-panel-connection`}
                aria-labelledby={`${editorId}-tab-connection`}
                hidden={activeSection !== "connection"}
              >
                <ProfileConnectionStatus
                  profile={selectedProfile}
                  system={draftSystem}
                  dirty={isDirty}
                />
                <SettingsPanel
                  title="Connection settings"
                  detail="Save these values before entering the same workspace ID and token in the Windows connector."
                  defaultOpen
                >
                  {renderConnectionFields(
                    draftSystem,
                    draft.settings.connection_settings ?? {},
                    updateConnectionSetting,
                    canManage,
                  )}
                </SettingsPanel>
                <SettingsPanel
                  title="Advanced environment"
                  detail="Technical configuration. Keep existing values unless your integration requires a change."
                >
                  <FormGrid>
                    {" "}
                    <TextField
                      label="Environment"
                      value={draft.settings.environment}
                      onChange={(value) => updateSettings("environment", value)}
                      placeholder="production or sandbox"
                    />
                  </FormGrid>
                </SettingsPanel>
              </div>
              <div
                className="space-y-5 p-3 sm:p-5"
                role="tabpanel"
                id={`${editorId}-panel-posting`}
                aria-labelledby={`${editorId}-tab-posting`}
                hidden={activeSection !== "posting"}
              >
                <SettingsPanel
                  title="Entry type"
                  detail="Invoices still require explicit approval. Changing these settings does not approve an invoice."
                  defaultOpen
                >
                  <FormGrid>
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
                        updateSettings(
                          "posting_mode",
                          value as ProfilePostingMode,
                        )
                      }
                    />
                    <TextField
                      label="Voucher type"
                      wide
                      unverified={draftSystem === "tally"}
                      value={draft.settings.voucher_type}
                      onChange={(value) =>
                        updateSettings("voucher_type", value)
                      }
                      placeholder="Purchase"
                    />
                  </FormGrid>
                </SettingsPanel>
                <SettingsPanel
                  title="Ledgers & inventory"
                  detail="The exact names from this client's books. Postings fail if a name here differs from the accounting system by even one character — copy names, don't type them."
                >
                  <div className="space-y-4">
                    {draftSystem === "tally" && (
                      <p className="rounded-xl border border-gold/30 bg-gold-soft p-3 text-sm text-gold">
                        Manually entered Tally names are Unverified. Saving or
                        activating a profile does not check that these names
                        exist in Tally.
                      </p>
                    )}
                    <FieldGroup
                      title="Where purchases post"
                      detail="Every invoice debits the purchase ledger and credits the supplier. Tax is split out to its own ledgers."
                    >
                      <TextField
                        label="Purchase ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        value={draft.settings.purchase_ledger}
                        onChange={(value) =>
                          updateSettings("purchase_ledger", value)
                        }
                        hint="Copy the exact ledger name from the accounting system."
                      />
                      <TextField
                        label="Tax ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        value={draft.settings.tax_ledger}
                        onChange={(value) =>
                          updateSettings("tax_ledger", value)
                        }
                        hint="Used when tax is posted as one line, or as the IGST fallback."
                      />
                      <TextField
                        label="Input IGST ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        value={String(
                          draft.settings.tax_settings.igst_ledger ?? "",
                        )}
                        onChange={(value) =>
                          updateTaxSetting("igst_ledger", value)
                        }
                        hint="Interstate GST. Leave blank to use the tax ledger."
                      />
                      <TextField
                        label="Input CGST ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        value={String(
                          draft.settings.tax_settings.cgst_ledger ?? "",
                        )}
                        onChange={(value) =>
                          updateTaxSetting("cgst_ledger", value)
                        }
                        hint="Central half of intrastate GST."
                      />
                      <TextField
                        label="Input SGST ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        value={String(
                          draft.settings.tax_settings.sgst_ledger ?? "",
                        )}
                        onChange={(value) =>
                          updateTaxSetting("sgst_ledger", value)
                        }
                        hint="State half of intrastate GST."
                      />
                      <TextField
                        label="TCS ledger"
                        wide
                        unverified={draftSystem === "tally"}
                        optional
                        value={draft.settings.tcs_ledger}
                        onChange={(value) =>
                          updateSettings("tcs_ledger", value)
                        }
                        hint="Only if suppliers charge TCS on invoices."
                      />
                      <TextField
                        label="Round-off ledger"
                        wide
                        unverified={draftSystem === "tally"}
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
                          wide
                          unverified={draftSystem === "tally"}
                          value={draft.settings.stock_item_name}
                          onChange={(value) =>
                            updateSettings("stock_item_name", value)
                          }
                          hint="Exact stock item name as it appears in the accounting system."
                        />
                        <TextField
                          label="Unit (UOM)"
                          wide
                          unverified={draftSystem === "tally"}
                          value={draft.settings.stock_item_uom}
                          onChange={(value) =>
                            updateSettings("stock_item_uom", value)
                          }
                          hint="The unit symbol that stock item uses — for example Nos or KGS."
                        />
                        <TextField
                          label="HSN/SAC"
                          optional
                          value={draft.settings.stock_item_hsn}
                          onChange={(value) =>
                            updateSettings("stock_item_hsn", value)
                          }
                          hint="Recommended for GST validation on India profiles."
                        />
                        <TextField
                          label="Godown / location"
                          wide
                          unverified={draftSystem === "tally"}
                          optional
                          value={draft.settings.godown_name}
                          onChange={(value) =>
                            updateSettings("godown_name", value)
                          }
                          hint="Only if the accounting system prompts for a godown during entry."
                        />
                      </FieldGroup>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-line-strong bg-canvas px-4 py-3 text-xs font-semibold leading-5 text-ink-secondary">
                        Stock item settings are hidden because this profile
                        posts ledger-only accounting vouchers. Switch the
                        posting mode to an inventory-backed mode to configure
                        stock items.
                      </div>
                    )}

                    <div className="flex flex-col gap-3 rounded-2xl border border-line bg-canvas p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-ink">
                          Line mapping rules
                        </p>
                        <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
                          {draft.settings.item_mappings.length
                            ? `${draft.settings.item_mappings.length} saved rule${draft.settings.item_mappings.length === 1 ? "" : "s"}. Ledger and tax overrides can apply in any posting mode; stock allocations apply only in inventory modes.`
                            : "Map invoice lines to accounting categories and ledgers. Inventory modes can also map stock items and units."}
                        </p>
                      </div>
                      <Link
                        href="/app/rules"
                        className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl border border-line bg-surface px-4 text-sm font-semibold text-accent-ink transition-colors hover:border-accent"
                      >
                        Manage item mappings
                        <ArrowRight size={14} />
                      </Link>
                    </div>
                  </div>
                </SettingsPanel>

                <TextAreaField
                  label="Accounting review notes"
                  value={trainingProfile.posting_expectations}
                  onChange={(value) =>
                    updateTrainingProfile({ posting_expectations: value })
                  }
                  hint="Document the intended entry for your reviewer. These notes do not override ledger fields or item mappings."
                  wide
                />
              </div>
              <div
                className="space-y-5 p-3 sm:p-5"
                role="tabpanel"
                id={`${editorId}-panel-extraction`}
                aria-labelledby={`${editorId}-tab-extraction`}
                hidden={activeSection !== "extraction"}
              >
                <SettingsPanel
                  title="Document parsing"
                  detail="How invoice content is read, separate from where the accounting entry posts."
                  defaultOpen
                >
                  <FormGrid>
                    {" "}
                    <SelectField
                      label="Default parser"
                      value={draft.settings.default_parser}
                      options={parsers}
                      onChange={(value) =>
                        updateSettings("default_parser", value)
                      }
                    />
                    <SelectField
                      label="Invoice format"
                      value={draft.settings.invoice_format}
                      options={invoiceFormatOptions}
                      onChange={(value) =>
                        updateSettings("invoice_format", value)
                      }
                    />
                  </FormGrid>
                </SettingsPanel>
                <TrainingProfileSection
                  section="guidance"
                  selectedProfile={selectedProfile}
                  trainingProfile={trainingProfile}
                  sampleFile={trainingSampleFile}
                  sampleNotes={trainingSampleNotes}
                  uploading={trainingUploading || saving}
                  dirty={isDirty}
                  onUpdate={updateTrainingProfile}
                  onToggleField={toggleExpectedTrainingField}
                  onFileChange={setTrainingSampleFile}
                  onNotesChange={setTrainingSampleNotes}
                  onUpload={() => void uploadTrainingSampleAction()}
                />
                <AiReadinessPanel
                  aiStatus={aiStatus}
                  aiStatusError={aiStatusError}
                />
              </div>
              <div
                className="space-y-5 p-3 sm:p-5"
                role="tabpanel"
                id={`${editorId}-panel-samples`}
                aria-labelledby={`${editorId}-tab-samples`}
                hidden={activeSection !== "samples"}
              >
                <TrainingProfileSection
                  section="samples"
                  selectedProfile={selectedProfile}
                  trainingProfile={trainingProfile}
                  sampleFile={trainingSampleFile}
                  sampleNotes={trainingSampleNotes}
                  uploading={trainingUploading || saving}
                  dirty={isDirty}
                  onUpdate={updateTrainingProfile}
                  onToggleField={toggleExpectedTrainingField}
                  onFileChange={setTrainingSampleFile}
                  onNotesChange={setTrainingSampleNotes}
                  onUpload={() => void uploadTrainingSampleAction()}
                />
                <OnboardingApprovalPanel
                  selectedProfile={selectedProfile}
                  status={onboardingStatus}
                  checklist={onboardingChecklist}
                  saving={saving || trainingUploading || isDirty}
                  canManage={canManage}
                  dirty={isDirty}
                  onRecommend={() => void generateRecommendations()}
                  onSubmitReview={() => void submitForReview()}
                  onActivate={() => void approveAndActivate()}
                />
              </div>
            </fieldset>
            <div className="flex flex-col gap-3 border-t border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-ink-secondary">
                {!canEdit
                  ? "Read-only access. Ask an owner or admin to update this profile."
                  : isDirty
                    ? "Unsaved changes · save before running setup actions."
                    : selectedProfile
                      ? "All changes saved. Invoice approval is still required."
                      : "Save a draft before adding samples or activating."}
              </p>
              <Button
                onClick={saveProfile}
                disabled={!canEdit || saving || trainingUploading}
                className="shrink-0"
              >
                {saving ? (
                  <LoaderCircle size={15} className="animate-spin" />
                ) : (
                  <Save size={15} />
                )}
                {onboardingStatus === "active" ? "Save changes" : "Save draft"}
              </Button>
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
      detail: trainingProfile.extraction_instructions
        ? "Configured"
        : "Recommended",
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
        detail: taxMode.includes("gst")
          ? "GST ledger mapping"
          : "Tax ledger mapping",
        ready: taxMode.includes("gst") ? taxLedgerReady : true,
        required: taxMode.includes("gst"),
      },
    );
    if (isItemInvoice) {
      items.push(
        {
          label: "Stock item",
          detail: settings.stock_item_name || "Exact Tally stock item",
          ready: Boolean(
            settings.stock_item_name || settings.item_mappings.length,
          ),
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
  canManage,
  dirty,
}: {
  canManage: boolean;
  dirty: boolean;
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
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
            Client onboarding
          </p>
          <h4 className="mt-1 text-lg font-semibold text-ink">
            Setup review and activation
          </h4>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-secondary">
            These checks show whether configuration is filled in, not whether
            Tally names or extraction accuracy are verified. Activation records
            setup review; it never approves an invoice.
          </p>
        </div>
        <span
          className={cn(
            "inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold",
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

      <div className="grid gap-3 p-4 md:grid-cols-2">
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
              {item.ready ? (
                <CheckCircle2 size={14} />
              ) : (
                <CircleDashed size={14} />
              )}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-ink">
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
          {dirty
            ? "Save your changes before setup actions."
            : blockers.length
              ? `${blockers.length} required setup item${blockers.length === 1 ? "" : "s"} missing.`
              : warnings.length
                ? `${warnings.length} optional improvement${warnings.length === 1 ? "" : "s"} remaining.`
                : "Required fields are filled. Verify the actual accounting setup before live use."}
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
            Apply setup suggestions
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!selectedProfile || saving}
            onClick={onSubmitReview}
          >
            <BadgeCheck size={14} />
            Submit for review
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={
              !selectedProfile ||
              saving ||
              !canManage ||
              active ||
              blockers.length > 0
            }
            onClick={onActivate}
          >
            <ShieldCheck size={14} />
            {active ? "Profile active" : "Activate profile"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function AiReadinessPanel({
  aiStatus,
  aiStatusError,
}: {
  aiStatus: AiExtractionStatus | null;
  aiStatusError: string;
}) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <h4 className="text-base font-semibold text-ink">AI assistance status</h4>
      <p className="mt-2 text-sm text-ink-secondary">
        {aiStatusError ||
          (aiStatus
            ? `${formatProvider(aiStatus.provider)} · ${aiStatus.configured ? "Provider configured" : "Provider not configured"} · ${humanizeToken(aiStatus.policy)}`
            : "Checking provider configuration…")}
      </p>
      <p className="mt-2 text-sm leading-6 text-ink-secondary">
        Configuration is not an accuracy score. Guidance can inform AI when
        routing invokes it; uploaded samples do not automatically train a model.
        Review extracted values against the original invoice.
      </p>
    </div>
  );
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
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-canvas px-2.5 py-1 text-xs font-semibold text-ink-secondary">
      <span className="shrink-0 text-accent-ink dark:text-cyan-ink">
        {icon}
      </span>
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
        "inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.08em]",
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
  canManage: boolean,
) {
  if (system === "tally") {
    return (
      <div className="space-y-4">
        <p className="rounded-xl border border-line bg-canvas p-3 text-sm text-ink-secondary">
          Windows connector SiftEntry URL:{" "}
          <strong className="break-all text-ink">
            https://app.siftentry.com
          </strong>{" "}
          (no /app suffix). Run Test connection on the client&apos;s PC; it
          works without invoices and never posts.
        </p>
        <fieldset disabled={!canManage} className="min-w-0 space-y-4">
          <legend className="sr-only">Connector credentials</legend>
          {!canManage && (
            <p className="text-sm text-ink-secondary">
              Only owners and admins can change connector credentials.
            </p>
          )}
          <FormGrid>
            <TextField
              label="Workspace ID"
              value={connectionText(
                settings,
                "workspace_id",
                "local-workspace",
              )}
              onChange={(value) => onChange("workspace_id", value)}
              wide
              hint="Must exactly match the Windows connector. Stop it before changing credentials."
            />
            <TextField
              label="Connector token"
              type="password"
              value={connectionText(settings, "connector_token")}
              onChange={(value) => onChange("connector_token", value)}
              wide
              placeholder={
                connectionBool(settings, "connector_token_set")
                  ? "Saved — leave blank to keep it"
                  : "Generate a secure token"
              }
              hint="Tokens are hidden. Save a generated token, then reveal it on Integrations → Tally to copy it to Windows. Never include tokens in support screenshots."
            />
          </FormGrid>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              if (
                connectionBool(settings, "connector_token_set") &&
                !window.confirm(
                  "Replace the saved connector token? Stop the connector first. After saving, it will need the new token.",
                )
              )
                return;
              const bytes = crypto.getRandomValues(new Uint8Array(32));
              onChange(
                "connector_token",
                Array.from(bytes, (byte) =>
                  byte.toString(16).padStart(2, "0"),
                ).join(""),
              );
            }}
          >
            Generate secure token
          </Button>
          <p className="text-xs text-ink-secondary">
            Generation changes this form only. Save to apply it.
          </p>
        </fieldset>
        <SettingsPanel
          title="Advanced connection settings"
          detail="Local addresses and posting transport. These are not the public SiftEntry URL."
        >
          <FormGrid>
            <TextField
              label="Local agent URL"
              value={connectionText(
                settings,
                "connector_url",
                "http://127.0.0.1:8765",
              )}
              onChange={(value) => onChange("connector_url", value)}
              wide
              hint="Legacy local-agent address. Do not paste it into the Windows connector's SiftEntry URL."
            />
            <TextField
              label="Tally URL"
              value={connectionText(
                settings,
                "tally_url",
                "http://localhost:9000",
              )}
              onChange={(value) => onChange("tally_url", value)}
              wide
              hint="Tally XML endpoint on the client's PC. Never expose port 9000 to the internet."
            />
          </FormGrid>
          <div className="mt-4">
            <CheckboxField
              label="Use local connector for posting"
              checked={connectionBool(settings, "connector_enabled", true)}
              onChange={(value) => onChange("connector_enabled", value)}
            />
          </div>
        </SettingsPanel>
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
    throw new Error(
      "Imported profile is missing a supported accounting system.",
    );
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
    <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-medium text-ink-secondary">
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
  return <div className="grid gap-4 md:grid-cols-2">{children}</div>;
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
          <span className="block text-sm font-semibold text-ink">{title}</span>
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
  section,
  selectedProfile,
  trainingProfile,
  sampleFile,
  sampleNotes,
  uploading,
  dirty,
  onUpdate,
  onToggleField,
  onFileChange,
  onNotesChange,
  onUpload,
}: {
  section: "guidance" | "samples";
  selectedProfile: ClientProfile | null;
  trainingProfile: ClientTrainingProfile;
  sampleFile: File | null;
  sampleNotes: string;
  uploading: boolean;
  dirty: boolean;
  onUpdate: (patch: Partial<ClientTrainingProfile>) => void;
  onToggleField: (field: string) => void;
  onFileChange: (file: File | null) => void;
  onNotesChange: (value: string) => void;
  onUpload: () => void;
}) {
  const samples = trainingProfile.sample_invoices ?? [];
  const sampleInputId = `sample-${selectedProfile?.id ?? "new"}`;
  return (
    <div className="space-y-5 rounded-2xl border border-line bg-surface p-4">
      <div>
        <h4 className="text-lg font-semibold text-ink">
          {section === "guidance"
            ? "Reading the invoice"
            : "Example invoices & expected values"}
        </h4>
        <p className="mt-1 text-sm leading-6 text-ink-secondary">
          {section === "guidance"
            ? "Describe where to find values. Keep accounting destinations in Posting rules. Invoice approval remains mandatory regardless of AI policy."
            : "Keep representative examples and reviewer notes together. A structured, scored regression test set will follow in the extraction-learning phase."}
        </p>
      </div>
      {section === "guidance" ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
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
              label="AI assistance policy"
              value={trainingProfile.llm_policy}
              options={llmPolicies}
              onChange={(value) => onUpdate({ llm_policy: value })}
            />
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
              Fields to check
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
                      "flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
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

          <div className="grid gap-4">
            <TextAreaField
              label="Extraction instructions"
              value={trainingProfile.extraction_instructions}
              onChange={(value) => onUpdate({ extraction_instructions: value })}
              hint="Describe where things sit on this client's invoices — e.g. which block holds the supplier name, and which total to use. Two or three sentences is plenty."
              status={{
                ready:
                  trainingProfile.extraction_instructions.trim().length > 0,
                readyText: "Guidance entered",
                emptyText: "Optional guidance",
              }}
              wide
            />
            <TextAreaField
              label="Reviewer validation guidance"
              value={trainingProfile.validation_rules.join("\n")}
              onChange={(value) =>
                onUpdate({
                  validation_rules: value.split("\n"),
                })
              }
              hint="One plain-language check per line. These are review/AI instructions, not executable validation rules."
              status={{
                ready: trainingProfile.validation_rules.length > 0,
                readyText: `${trainingProfile.validation_rules.length} check${trainingProfile.validation_rules.length === 1 ? "" : "s"} entered`,
                emptyText: "Optional guidance",
              }}
            />

            <TextAreaField
              label="Exception examples"
              value={trainingProfile.exception_examples}
              onChange={(value) => onUpdate({ exception_examples: value })}
              hint="Notes for your reviewer. These examples are stored with the profile but are not currently sent to the AI."
              status={{
                ready: trainingProfile.exception_examples.trim().length > 0,
                readyText: "Saved",
                emptyText: "Optional",
              }}
              wide
            />
          </div>
        </>
      ) : (
        <>
          {dirty && (
            <p role="status" className="text-sm text-gold">
              Save your changes before uploading a sample.
            </p>
          )}
          <div className="rounded-2xl border border-line bg-canvas p-4">
            <div className="grid gap-4 xl:grid-cols-[minmax(240px,320px)_minmax(0,1fr)] xl:items-end">
              <label className="min-w-0">
                <span className="mb-2 block text-xs font-semibold uppercase text-ink-muted">
                  Sample invoice
                </span>
                <span className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink transition-colors hover:border-accent hover:bg-accent-soft">
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
                label="Expected values & sample notes"
                value={sampleNotes}
                onChange={onNotesChange}
                placeholder="Example: invoice INV-104, total USD 1,250.00; reviewer confirmation pending"
              />
            </div>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              {!selectedProfile ? (
                <p className="text-xs font-medium text-gold">
                  Save this client profile once before attaching sample
                  invoices.
                </p>
              ) : (
                <p className="text-xs font-semibold text-ink-secondary">
                  Use varied layouts and document types. Uploading does not
                  confirm expected values or prove extraction accuracy.
                </p>
              )}
              <Button
                type="button"
                variant="primary"
                className="h-11 w-full shrink-0 whitespace-nowrap sm:w-auto sm:min-w-[180px]"
                disabled={!selectedProfile || !sampleFile || uploading || dirty}
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
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
                Uploaded samples
              </p>
              <span className="rounded-full border border-line bg-canvas px-2.5 py-1 text-xs font-semibold text-ink-secondary">
                {samples.length}
              </span>
            </div>
            {samples.length ? (
              <div className="grid gap-4">
                {samples.map((sample, sampleIndex) => (
                  <div
                    key={sample.id || sample.filename}
                    className="min-w-0 space-y-3 rounded-xl border border-line bg-canvas p-4"
                  >
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
                      <FileText size={16} />
                    </span>
                    <div className="min-w-0">
                      <span className="block break-words text-sm font-semibold text-ink">
                        {sample.filename || "Sample invoice"}
                      </span>
                      <span className="mt-1 block break-words text-xs font-medium text-ink-secondary">
                        {formatBytes(sample.size_bytes)} /{" "}
                        {sample.fields_confirmed
                          ? "Fields marked confirmed"
                          : "Expected values not confirmed"}
                      </span>
                    </div>
                    <TextAreaField
                      label={`Expected values — ${sample.filename || `sample ${sampleIndex + 1}`}`}
                      value={sample.notes}
                      hint="Open the original PDF and record the expected invoice number, date, currency, totals and relevant line values. Editing these notes clears confirmation."
                      onChange={(notes) =>
                        onUpdate({
                          sample_invoices: samples.map((item, index) =>
                            index === sampleIndex
                              ? { ...item, notes, fields_confirmed: false }
                              : item,
                          ),
                        })
                      }
                    />
                    <label className="flex min-h-11 items-start gap-3 text-sm text-ink-secondary">
                      <input
                        type="checkbox"
                        className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
                        disabled={!sample.notes.trim()}
                        checked={sample.fields_confirmed}
                        onChange={(event) =>
                          onUpdate({
                            sample_invoices: samples.map((item, index) =>
                              index === sampleIndex
                                ? {
                                    ...item,
                                    fields_confirmed: event.target.checked,
                                  }
                                : item,
                            ),
                          })
                        }
                      />
                      I checked these expected values against the original PDF.
                      Save to record this review; this is not an automated
                      accuracy result.
                    </label>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-line-strong bg-canvas px-4 py-5 text-sm font-semibold text-ink-secondary">
                No sample invoices yet. Add representative PDFs and record
                expected values in the notes for your reviewer.
              </div>
            )}
          </div>
        </>
      )}
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
  unverified = false,
  type = "text",
}: {
  unverified?: boolean;
  type?: "text" | "password";
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
    <label className={cn("block min-w-0", wide && "col-span-full")}>
      <span className="text-xs font-semibold uppercase text-ink-muted">
        {label}
        {unverified && (
          <span className="ml-2 inline-block rounded-md bg-gold-soft px-2 py-0.5 text-xs font-medium normal-case text-gold">
            Unverified
          </span>
        )}
        {optional && (
          <span className="ml-1.5 font-medium normal-case tracking-normal text-ink-muted/70">
            · optional
          </span>
        )}
      </span>
      <input
        type={type}
        aria-label={label}
        autoComplete={type === "password" ? "new-password" : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
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
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
        {detail}
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">{children}</div>
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
    <label className={cn("block min-w-0", wide && "col-span-full")}>
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase text-ink-muted">
          {label}
        </span>
        {status && (
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
              status.ready
                ? "bg-success-soft text-success"
                : "bg-surface-subtle text-ink-muted",
            )}
          >
            {status.ready ? (
              <CheckCircle2 size={12} />
            ) : (
              <CircleDashed size={12} />
            )}
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
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={4}
        className="mt-2 min-h-28 w-full resize-y rounded-xl border border-line-strong bg-surface px-3 py-3 text-sm font-medium leading-6 text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
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
      <span className="text-xs font-semibold uppercase text-ink-muted">
        {label}
      </span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value as TValue)}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-medium text-ink outline-none transition-colors focus:border-accent"
      >
        {(value && !options.some((option) => option.value === value)
          ? [{ label: `Custom (${value})`, value }, ...options]
          : options
        ).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
