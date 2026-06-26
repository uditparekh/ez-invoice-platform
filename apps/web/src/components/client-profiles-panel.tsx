"use client";

import {
  BadgeCheck,
  CheckCircle2,
  CopyPlus,
  LoaderCircle,
  Plus,
  Save,
  Star,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ContentCard } from "@/components/dashboard/content-card";
import { Button } from "@/components/ui/button";
import { useClientProfiles } from "@/hooks/use-client-profiles";
import type {
  AccountingSystem,
  ClientProfile,
  ClientProfileItemMapping,
  ClientProfilePayload,
  ClientProfileSettings,
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

const postingModes: { label: string; value: ProfilePostingMode }[] = [
  { label: "Accounting voucher", value: "accounting_voucher" },
  { label: "Item invoice", value: "item_invoice" },
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

const emptyMapping: ClientProfileItemMapping = {
  source_description_contains: "",
  source_hsn_sac: "",
  target_item_name: "",
  target_uom: "",
  purchase_ledger: "",
  tax_ledger: "",
  metadata: {},
};

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
    tax_settings: {},
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
      workspace_id: "client-test",
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

function blankProfile(
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

function neelPtaProfile(): ClientProfilePayload {
  return {
    name: "NEEL ENTERPRISE - PTA item invoice",
    accounting_system: "tally",
    description:
      "Confirmed Tally profile for PTA SWEEP item invoice with IGST, TCS, and round-off ledgers.",
    is_default: true,
    settings: {
      ...defaultSettings(),
      company_name: "NEEL ENTERPRISE",
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
      purchase_ledger: "PURCHASES A/C",
      tax_ledger: "IGST A/C",
      tcs_ledger: "TCS",
      round_off_ledger: "ROUND OFF",
      stock_item_name: "PTA SWEEP",
      stock_item_hsn: "29173600",
      stock_item_uom: "KGS",
      item_mappings: [
        {
          ...emptyMapping,
          source_description_contains: "PTA",
          source_hsn_sac: "29173600",
          target_item_name: "PTA SWEEP",
          target_uom: "KGS",
          purchase_ledger: "PURCHASES A/C",
          tax_ledger: "IGST A/C",
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
    deleteProfile,
  } = useClientProfiles({ accountingSystem });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ClientProfilePayload>(() =>
    blankProfile(accountingSystem ?? "tally"),
  );
  const [notice, setNotice] = useState("");

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedId) ?? null,
    [profiles, selectedId],
  );

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

  function updatePrimaryMapping<Key extends keyof ClientProfileItemMapping>(
    key: Key,
    value: ClientProfileItemMapping[Key],
  ) {
    setDraft((current) => {
      const [first = emptyMapping, ...rest] = current.settings.item_mappings;
      return {
        ...current,
        settings: {
          ...current.settings,
          item_mappings: [{ ...first, [key]: value }, ...rest],
        },
      };
    });
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
    setSelectedId(null);
    setDraft(blankProfile(accountingSystem ?? "tally"));
    setNotice("");
  }

  function selectProfile(profile: ClientProfile) {
    setSelectedId(profile.id);
    setDraft(profileToPayload(profile));
    setNotice("");
  }

  function useNeelTemplate() {
    setSelectedId(null);
    setDraft(neelPtaProfile());
    setNotice("Neel PTA template loaded. Review and save it to this workspace.");
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
      setSelectedId(saved.id);
      setNotice("Client profile saved.");
    } catch (saveError) {
      setNotice((saveError as Error).message);
    }
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

  async function removeProfile() {
    if (!selectedProfile) return;
    const confirmed = window.confirm(
      `Delete "${selectedProfile.name}" from this workspace?`,
    );
    if (!confirmed) return;
    setNotice("");
    try {
      await deleteProfile(selectedProfile.id);
      setSelectedId(null);
      setDraft(blankProfile(accountingSystem ?? "tally"));
      setNotice("Client profile deleted.");
    } catch (deleteError) {
      setNotice((deleteError as Error).message);
    }
  }

  const mapping = draft.settings.item_mappings[0] ?? emptyMapping;
  const countryOptions = optionsWithCurrent(
    countryProfiles.map(({ label, value }) => ({ label, value })),
    draft.settings.country_code,
  );
  const invoiceFormatOptions = optionsWithCurrent(
    invoiceFormats,
    draft.settings.invoice_format,
  );
  const taxModeOptions = optionsWithCurrent(taxModes, draft.settings.tax_mode);

  return (
    <ContentCard
      title={title}
      subtitle={subtitle}
      action={
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={newProfile}>
            <Plus size={14} />
            New
          </Button>
          {(!accountingSystem || accountingSystem === "tally") && (
            <Button size="sm" variant="secondary" onClick={useNeelTemplate}>
              <CopyPlus size={14} />
              Neel template
            </Button>
          )}
        </div>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-3">
          {loading ? (
            <div className="rounded-2xl border border-line bg-canvas px-4 py-6 text-sm font-bold text-ink-secondary">
              <LoaderCircle className="mr-2 inline animate-spin" size={16} />
              Loading profiles
            </div>
          ) : profiles.length ? (
            profiles.map((profile) => (
              <button
                key={profile.id}
                type="button"
                onClick={() => selectProfile(profile)}
                className={cn(
                  "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                  selectedId === profile.id
                    ? "border-accent bg-accent-soft"
                    : "border-line bg-canvas hover:border-accent hover:bg-surface-subtle",
                )}
              >
                <div className="flex items-start gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface text-xs font-black uppercase text-accent-ink">
                    {profile.accounting_system.slice(0, 2)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-black text-ink">
                      {profile.name}
                    </span>
                    <span className="mt-1 block text-xs font-bold capitalize text-ink-muted">
                      {systemLabel(profile.accounting_system)}
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
            <div className="rounded-2xl border border-dashed border-line-strong bg-canvas px-4 py-6 text-sm font-semibold text-ink-secondary">
              No profiles yet. Start with a blank profile or load the Neel
              template.
            </div>
          )}
        </aside>

        <section className="rounded-2xl border border-line bg-canvas">
          <div className="flex flex-col gap-3 border-b border-line px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[11px] font-extrabold uppercase text-ink-muted">
                {selectedProfile ? "Editing profile" : "New profile"}
              </p>
              <h3 className="mt-1 text-lg font-black text-ink">
                {draft.name || "Untitled client setup"}
              </h3>
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
              <Button size="sm" variant="primary" onClick={saveProfile} disabled={saving}>
                {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
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

          <div className="space-y-6 p-5">
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
                label="Description"
                value={draft.description}
                onChange={(value) => updateDraft("description", value)}
                placeholder="When this profile should be used"
                wide
              />
            </FormGrid>

            <SectionTitle
              title="Connection"
              detail="Save workspace-level connection metadata here. Keep production secrets and long-lived OAuth tokens in server-side secret storage."
            />
            {renderConnectionFields(
              accountingSystem ?? draft.accounting_system,
              draft.settings.connection_settings ?? {},
              updateConnectionSetting,
            )}

            <SectionTitle
              title="Country, format, and taxes"
              detail="Choose the client market once; SiftEntry saves the default currency, invoice format, and tax behavior for this workspace."
            />
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

            <SectionTitle
              title="Posting setup"
              detail="These values are written into the ERP payload or export package."
            />
            <FormGrid>
              <TextField
                label="Company name"
                value={draft.settings.company_name}
                onChange={(value) => updateSettings("company_name", value)}
                placeholder="Exact Tally or ERP company"
              />
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

            <SectionTitle
              title="Ledgers"
              detail="Use exact names from the client's accounting system."
            />
            <FormGrid>
              <TextField
                label="Purchase ledger"
                value={draft.settings.purchase_ledger}
                onChange={(value) => updateSettings("purchase_ledger", value)}
                placeholder="PURCHASES A/C"
              />
              <TextField
                label="Tax ledger"
                value={draft.settings.tax_ledger}
                onChange={(value) => updateSettings("tax_ledger", value)}
                placeholder="IGST A/C"
              />
              <TextField
                label="TCS ledger"
                value={draft.settings.tcs_ledger}
                onChange={(value) => updateSettings("tcs_ledger", value)}
                placeholder="TCS"
              />
              <TextField
                label="Round-off ledger"
                value={draft.settings.round_off_ledger}
                onChange={(value) => updateSettings("round_off_ledger", value)}
                placeholder="ROUND OFF"
              />
            </FormGrid>

            <SectionTitle
              title="Stock item"
              detail="Needed when the client expects Tally Item Invoice mode."
            />
            <FormGrid>
              <TextField
                label="Stock item"
                value={draft.settings.stock_item_name}
                onChange={(value) => updateSettings("stock_item_name", value)}
                placeholder="PTA SWEEP"
              />
              <TextField
                label="HSN/SAC"
                value={draft.settings.stock_item_hsn}
                onChange={(value) => updateSettings("stock_item_hsn", value)}
                placeholder="29173600"
              />
              <TextField
                label="UOM"
                value={draft.settings.stock_item_uom}
                onChange={(value) => updateSettings("stock_item_uom", value)}
                placeholder="KGS"
              />
              <TextField
                label="Godown/location"
                value={draft.settings.godown_name}
                onChange={(value) => updateSettings("godown_name", value)}
                placeholder="Optional"
              />
            </FormGrid>

            <SectionTitle
              title="Primary item mapping"
              detail="The first matching rule used for item and ledger recommendations."
            />
            <FormGrid>
              <TextField
                label="Description contains"
                value={mapping.source_description_contains}
                onChange={(value) =>
                  updatePrimaryMapping("source_description_contains", value)
                }
                placeholder="PTA"
              />
              <TextField
                label="Source HSN/SAC"
                value={mapping.source_hsn_sac}
                onChange={(value) => updatePrimaryMapping("source_hsn_sac", value)}
                placeholder="29173600"
              />
              <TextField
                label="Target item"
                value={mapping.target_item_name}
                onChange={(value) => updatePrimaryMapping("target_item_name", value)}
                placeholder="PTA SWEEP"
              />
              <TextField
                label="Target UOM"
                value={mapping.target_uom}
                onChange={(value) => updatePrimaryMapping("target_uom", value)}
                placeholder="KGS"
              />
              <TextField
                label="Mapping purchase ledger"
                value={mapping.purchase_ledger}
                onChange={(value) => updatePrimaryMapping("purchase_ledger", value)}
                placeholder="PURCHASES A/C"
              />
              <TextField
                label="Mapping tax ledger"
                value={mapping.tax_ledger}
                onChange={(value) => updatePrimaryMapping("tax_ledger", value)}
                placeholder="IGST A/C"
              />
            </FormGrid>

            {draft.is_default && (
              <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
                <CheckCircle2 size={16} />
                This profile will become the default for{" "}
                {systemLabel(draft.accounting_system)}.
              </div>
            )}

            <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-bold text-ink-secondary">
              <input
                type="checkbox"
                checked={draft.is_default}
                onChange={(event) => updateDraft("is_default", event.target.checked)}
                className="size-4 accent-[var(--accent)]"
              />
              Use as default for this accounting system
            </label>
          </div>
        </section>
      </div>
    </ContentCard>
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
            value={connectionText(settings, "workspace_id", "client-test")}
            onChange={(value) => onChange("workspace_id", value)}
            placeholder="client-test"
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

function SectionTitle({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="border-t border-line pt-5">
      <h4 className="text-sm font-black text-ink">{title}</h4>
      <p className="mt-1 text-sm leading-5 text-ink-secondary">{detail}</p>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  wide = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  wide?: boolean;
}) {
  return (
    <label className={cn("block", wide && "md:col-span-2 xl:col-span-3")}>
      <span className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
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
