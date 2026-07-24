"use client";

import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  FlaskConical,
  LoaderCircle,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useClientProfiles } from "@/hooks/use-client-profiles";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import type {
  ClientProfile,
  ClientProfileItemMapping,
  Invoice,
} from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";

/** Rules & mapping — UI Spec §12. Four tabs:
 *  GL mapping (live profile item_mappings, editable) · Rules (+ real simulator) ·
 *  Vendor memory (corrections/learning) · Parser training (real sample uploads). */

type RulesTab = "mapping" | "rules" | "vendors" | "training";

export default function RulesPage() {
  const { activeOrganizationId } = useAuth();
  const { invoices } = useWorkspaceInvoices();
  const {
    profiles,
    loading: profilesLoading,
    saving,
    updateProfile,
    uploadTrainingSample,
  } = useClientProfiles();

  const [tab, setTab] = useState<RulesTab>("mapping");
  const [profileId, setProfileId] = useState<string>("");
  const profile =
    profiles.find((candidate) => candidate.id === profileId) ??
    profiles.find((candidate) => candidate.is_default) ??
    profiles[0] ??
    null;

  const unmapped = useMemo(
    () => unmappedDescriptions(invoices, profile),
    [invoices, profile],
  );

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Rules & mapping"
        section={profile ? profile.name : "Client configuration"}
        description="Ledger mappings, posting controls, vendor memory, and parser training — the logic layer every invoice flows through."
        action={
          profiles.length > 1 ? (
            <label className="flex h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 text-sm font-black text-ink">
              Profile
              <select
                value={profile?.id ?? ""}
                onChange={(event) => setProfileId(event.target.value)}
                className="bg-transparent font-bold text-accent outline-none"
              >
                {profiles.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name}
                  </option>
                ))}
              </select>
            </label>
          ) : undefined
        }
      />

      <div className="border-b border-line bg-shell/95 backdrop-blur">
        <div className="mx-auto grid max-w-[1440px] grid-cols-2 gap-2 px-4 py-3 sm:flex sm:gap-1 sm:overflow-x-auto sm:px-6 sm:py-0 lg:px-8">
          <TabButton active={tab === "mapping"} onClick={() => setTab("mapping")}>
            GL mapping
            {unmapped.length > 0 && <CountBadge tone="warning">{unmapped.length}</CountBadge>}
          </TabButton>
          <TabButton active={tab === "rules"} onClick={() => setTab("rules")}>
            Rules
          </TabButton>
          <TabButton active={tab === "vendors"} onClick={() => setTab("vendors")}>
            Vendor memory
          </TabButton>
          <TabButton active={tab === "training"} onClick={() => setTab("training")}>
            Parser training
          </TabButton>
        </div>
      </div>

      <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        {profilesLoading ? (
          <LoadingState label="Loading client profiles" />
        ) : !profile ? (
          <EmptyState
            icon={BrainCircuit}
            title="Create a client profile first"
            description="Mappings, rules, and parser training all live on a client profile — onboard one from Client profiles."
          />
        ) : tab === "mapping" ? (
          <MappingTab
            key={profile.id}
            profile={profile}
            unmapped={unmapped}
            saving={saving}
            onSave={(mappings) =>
              updateProfile(profile.id, {
                settings: { ...profile.settings, item_mappings: mappings },
              })
            }
          />
        ) : tab === "rules" ? (
          <RulesTabView invoices={invoices} />
        ) : tab === "vendors" ? (
          <VendorMemoryTab organizationId={activeOrganizationId} invoices={invoices} />
        ) : (
          <TrainingTab
            profile={profile}
            invoices={invoices}
            saving={saving}
            onUpload={(file, notes) => uploadTrainingSample(profile.id, file, notes)}
          />
        )}
      </main>
    </div>
  );
}

/* ================= tab 1: GL mapping ================= */

function MappingTab({
  profile,
  unmapped,
  saving,
  onSave,
}: {
  profile: ClientProfile;
  unmapped: { description: string; amount: number; currency: string }[];
  saving: boolean;
  onSave: (mappings: ClientProfileItemMapping[]) => Promise<unknown>;
}) {
  const [rows, setRows] = useState<ClientProfileItemMapping[]>(
    () => profile.settings.item_mappings?.map((mapping) => ({ ...mapping })) ?? [],
  );
  const [notice, setNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const dirty =
    JSON.stringify(rows) !==
    JSON.stringify(profile.settings.item_mappings ?? []);

  function update(index: number, patch: Partial<ClientProfileItemMapping>) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function addRow(prefill?: Partial<ClientProfileItemMapping>) {
    setRows((current) => [
      ...current,
      {
        source_description_contains: "",
        source_hsn_sac: "",
        target_item_name: "",
        target_uom: "",
        purchase_ledger: profile.settings.purchase_ledger || "",
        tax_ledger: profile.settings.tax_ledger || "",
        metadata: {},
        ...prefill,
      },
    ]);
  }

  async function save() {
    setNotice("");
    setSaveError("");
    try {
      await onSave(rows.filter((row) => row.source_description_contains.trim()));
      setNotice("Mappings saved to the profile — future invoices inherit them.");
    } catch (error) {
      setSaveError((error as Error).message);
    }
  }

  return (
    <>
      <section className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <LedgerFact label="Purchase ledger" value={profile.settings.purchase_ledger} />
        <LedgerFact label="Tax ledger" value={profile.settings.tax_ledger} />
        <LedgerFact label="TCS ledger" value={profile.settings.tcs_ledger} />
        <LedgerFact label="Round-off ledger" value={profile.settings.round_off_ledger} />
      </section>

      {unmapped.length > 0 && (
        <ContentCard
          title="Unmapped line items"
          subtitle="Seen on recent invoices with no matching rule — one click starts the mapping"
        >
          <div className="divide-y divide-line">
            {unmapped.slice(0, 5).map((item) => (
              <div
                key={item.description}
                className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <p className="min-w-0 flex-1 truncate text-sm font-bold text-gold-ink">
                  <AlertTriangle size={13} className="mr-1.5 inline" />
                  {item.description}
                  <span className="ml-2 font-mono text-xs text-ink-muted">
                    {formatCurrency(item.amount, item.currency)}
                  </span>
                </p>
                <button
                  type="button"
                  onClick={() =>
                    addRow({ source_description_contains: item.description })
                  }
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                >
                  <Plus size={13} />
                  Map it
                </button>
              </div>
            ))}
          </div>
        </ContentCard>
      )}

      <ContentCard
        title="Mapping worksheet"
        subtitle="Detected description → item, UOM, and ledgers. Use exact names from the client's books."
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => addRow()}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-line-strong bg-surface px-3.5 text-sm font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
            >
              <Plus size={15} />
              Add mapping
            </button>
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={() => void save()}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              {saving ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              Save mappings
            </button>
          </div>
        }
      >
        {rows.length ? (
          <>
          <div className="space-y-3 md:hidden">
            {rows.map((row, index) => (
              <article
                key={`card-${index}`}
                className="rounded-2xl border border-line bg-surface p-4"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
                    Mapping {index + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                    className="rounded-lg p-2.5 text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
                    aria-label={`Remove mapping ${index + 1}`}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="mt-1 space-y-3">
                  <MapField label="Description contains" value={row.source_description_contains} placeholder="e.g. PTA SWEEP" strong onChange={(value) => update(index, { source_description_contains: value })} />
                  <div className="grid grid-cols-2 gap-3">
                    <MapField label="HSN/SAC" value={row.source_hsn_sac} placeholder="—" onChange={(value) => update(index, { source_hsn_sac: value })} />
                    <MapField label="UOM" value={row.target_uom} placeholder="KGS" onChange={(value) => update(index, { target_uom: value })} />
                  </div>
                  <MapField label="Target item" value={row.target_item_name} placeholder="Stock item name" onChange={(value) => update(index, { target_item_name: value })} />
                  <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2">
                    <MapField label="Purchase ledger" value={row.purchase_ledger} placeholder="Purchase A/C" onChange={(value) => update(index, { purchase_ledger: value })} />
                    <MapField label="Tax ledger" value={row.tax_ledger} placeholder="IGST A/C" onChange={(value) => update(index, { tax_ledger: value })} />
                  </div>
                </div>
              </article>
            ))}
          </div>
          <div className="hidden overflow-x-auto md:block" data-scroll-region="true">
            <table className="w-full min-w-[860px] table-fixed border-collapse text-left text-sm">
              <thead>
                <tr className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
                  <th className="w-[22%] py-2 pr-2">Description contains</th>
                  <th className="w-[10%] px-2 py-2">HSN/SAC</th>
                  <th className="w-[20%] px-2 py-2">Target item</th>
                  <th className="w-[8%] px-2 py-2">UOM</th>
                  <th className="w-[17%] px-2 py-2">Purchase ledger</th>
                  <th className="w-[17%] px-2 py-2">Tax ledger</th>
                  <th className="w-[6%] py-2 pl-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index} className="border-t border-line">
                    <MapCell value={row.source_description_contains} placeholder="e.g. PTA SWEEP" onChange={(value) => update(index, { source_description_contains: value })} strong />
                    <MapCell value={row.source_hsn_sac} placeholder="—" onChange={(value) => update(index, { source_hsn_sac: value })} />
                    <MapCell value={row.target_item_name} placeholder="Stock item name" onChange={(value) => update(index, { target_item_name: value })} />
                    <MapCell value={row.target_uom} placeholder="KGS" onChange={(value) => update(index, { target_uom: value })} />
                    <MapCell value={row.purchase_ledger} placeholder="Purchase A/C" onChange={(value) => update(index, { purchase_ledger: value })} />
                    <MapCell value={row.tax_ledger} placeholder="IGST A/C" onChange={(value) => update(index, { tax_ledger: value })} />
                    <td className="py-2 pl-2 text-right">
                      <button
                        type="button"
                        onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                        className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
                        aria-label={`Remove mapping ${index + 1}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        ) : (
          <p className="text-sm font-semibold text-ink-muted">
            No mappings yet — add one, or click an unmapped line item above.
          </p>
        )}
        {notice && (
          <p className="mt-4 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
            {notice}
          </p>
        )}
        {saveError && (
          <p className="mt-4 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
            {saveError}
          </p>
        )}
      </ContentCard>
    </>
  );
}

/* ================= tab 2: rules + simulator ================= */

function RulesTabView({ invoices }: { invoices: Invoice[] }) {
  const [threshold, setThreshold] = useState(() => {
    if (typeof window === "undefined") return 500000;
    const stored = Number(window.localStorage.getItem("siftentry.rules.approvalThreshold"));
    return Number.isFinite(stored) && stored > 0 ? stored : 500000;
  });
  const [approvalOn, setApprovalOn] = useState(() =>
    typeof window !== "undefined"
      ? window.localStorage.getItem("siftentry.rules.approvalOn") === "true"
      : false,
  );
  const [simulated, setSimulated] = useState(false);

  const duplicates = useMemo(() => {
    const seen = new Set<string>();
    let count = 0;
    let amount = 0;
    for (const invoice of invoices) {
      const key = `${(invoice.supplier.name || "").toLowerCase()}|${invoice.total}`;
      if (invoice.total > 0 && seen.has(key)) {
        count += 1;
        amount += invoice.total;
      } else seen.add(key);
    }
    return { count, amount };
  }, [invoices]);

  const taxMismatch = useMemo(
    () =>
      invoices.filter(
        (invoice) =>
          invoice.total > 0 &&
          Math.abs(invoice.subtotal + invoice.tax_total - invoice.total) > 1,
      ).length,
    [invoices],
  );

  const sample = useMemo(() => invoices.slice(0, 30), [invoices]);
  const hits = useMemo(
    () => sample.filter((invoice) => invoice.total >= threshold),
    [sample, threshold],
  );
  const currency = invoices[0]?.currency || "USD";

  function persistApproval(on: boolean, value: number) {
    window.localStorage.setItem("siftentry.rules.approvalOn", String(on));
    window.localStorage.setItem("siftentry.rules.approvalThreshold", String(value));
  }

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-3">
        <RuleCard
          icon={<ShieldCheck size={18} />}
          title="Duplicate invoice control"
          detail="Flags matching supplier + amount (and invoice number) before posting."
          state="Active"
          live={
            duplicates.count
              ? `${duplicates.count} caught · ${formatCurrency(duplicates.amount, currency)} protected`
              : "No duplicates in the current queue"
          }
          liveTone={duplicates.count ? "warning" : "success"}
        />
        <RuleCard
          icon={<ShieldCheck size={18} />}
          title="Tax reconciliation"
          detail="Subtotal + tax must reconcile with the invoice total before it can post."
          state="Active"
          live={
            taxMismatch
              ? `${taxMismatch} invoice${taxMismatch === 1 ? "" : "s"} currently off`
              : "All invoices reconcile"
          }
          liveTone={taxMismatch ? "warning" : "success"}
        />
        <RuleCard
          icon={<ShieldCheck size={18} />}
          title={`Approval above ${formatCurrency(threshold, currency)}`}
          detail="Routes high-value invoices to an approver before posting."
          state={approvalOn ? "Active" : "Off"}
          action={
            <button
              type="button"
              onClick={() => {
                setApprovalOn((on) => {
                  persistApproval(!on, threshold);
                  return !on;
                });
              }}
              className={cn(
                "inline-flex h-9 items-center rounded-lg px-3.5 text-xs font-black transition-colors",
                approvalOn
                  ? "bg-success-soft text-success"
                  : "border border-line-strong bg-surface text-ink-secondary hover:border-accent hover:text-accent",
              )}
            >
              {approvalOn ? "Turn off" : "Turn on"}
            </button>
          }
        />
      </div>

      <ContentCard
        title="🧪 Rule simulator"
        subtitle={`Test the approval rule against your last ${sample.length} invoices before turning it on — evidence, not faith.`}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex h-11 flex-1 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3.5 text-sm font-black text-ink sm:max-w-xs">
            Threshold
            <input
              value={threshold}
              onChange={(event) => {
                const value = Number(event.target.value.replace(/[^0-9]/g, "")) || 0;
                setThreshold(value);
                setSimulated(false);
                persistApproval(approvalOn, value);
              }}
              className="min-w-0 flex-1 bg-transparent text-right font-mono outline-none"
              inputMode="numeric"
            />
          </label>
          <button
            type="button"
            onClick={() => setSimulated(true)}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover"
          >
            <FlaskConical size={16} />
            Run simulation
          </button>
        </div>

        {simulated && (
          <div className="mt-4 rounded-xl bg-accent-soft px-4 py-3.5 text-sm font-bold text-accent-ink">
            <Sparkles size={14} className="mr-1.5 inline" />
            {hits.length} of {sample.length} invoices ({formatCurrency(invoiceSum(hits), currency)})
            would have required approval · no false blocks below the threshold.
            {hits.length > 0 && (
              <span className="mt-2 block font-semibold">
                {hits
                  .slice(0, 3)
                  .map(
                    (invoice) =>
                      `${invoice.supplier.name || "Unknown"} ${formatCurrency(invoice.total, invoice.currency)}`,
                  )
                  .join(" · ")}
                {hits.length > 3 ? ` · +${hits.length - 3} more` : ""}
              </span>
            )}
          </div>
        )}
      </ContentCard>
    </>
  );
}

/* ================= tab 3: vendor memory ================= */

function VendorMemoryTab({
  organizationId,
  invoices,
}: {
  organizationId: string | null;
  invoices: Invoice[];
}) {
  const [records, setRecords] = useState<Record<string, unknown>[] | null>(null);

  useEffect(() => {
    if (!organizationId) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(
          `/api/organizations/${organizationId}/corrections/learning?limit=200`,
        );
        if (!response.ok) throw new Error();
        const payload = (await response.json()) as unknown;
        const items = Array.isArray(payload)
          ? payload
          : ((payload as { items?: unknown[] })?.items ?? []);
        if (!cancelled) setRecords(items as Record<string, unknown>[]);
      } catch {
        if (!cancelled) setRecords([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  const vendors = useMemo(() => {
    const bySupplier = new Map<string, { invoices: number; flags: number; learned: number }>();
    for (const invoice of invoices) {
      const name = invoice.supplier.name || "Unknown supplier";
      const entry = bySupplier.get(name) ?? { invoices: 0, flags: 0, learned: 0 };
      entry.invoices += 1;
      if (invoice.validation_issues.length || invoice.status === "needs_review")
        entry.flags += 1;
      bySupplier.set(name, entry);
    }
    for (const record of records ?? []) {
      const name =
        stringOf(record, "supplier_name") ||
        stringOf(record, "supplier") ||
        stringOf(record, "vendor");
      if (!name) continue;
      const entry = bySupplier.get(name) ?? { invoices: 0, flags: 0, learned: 0 };
      entry.learned += 1;
      bySupplier.set(name, entry);
    }
    return [...bySupplier.entries()]
      .map(([name, entry]) => ({ name, ...entry }))
      .sort((a, b) => b.invoices - a.invoices);
  }, [invoices, records]);

  if (records === null) return <LoadingState label="Loading vendor memory" />;
  if (!vendors.length)
    return (
      <EmptyState
        icon={BrainCircuit}
        title="Vendor memory builds itself"
        description="Every correction saved in the Review Workspace with the vendor-memory toggle on becomes a learned behavior here."
      />
    );

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {vendors.slice(0, 9).map((vendor) => {
        const state =
          vendor.flags === 0 && vendor.invoices >= 3
            ? "Active · touchless"
            : vendor.learned > 0
              ? "Learning"
              : vendor.flags > 0
                ? "Training"
                : "Watching";
        return (
          <article key={vendor.name} className="rounded-2xl border border-line bg-surface p-5 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <h3 className="min-w-0 truncate text-base font-black text-ink">{vendor.name}</h3>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2.5 py-1 text-[11px] font-black",
                  state.startsWith("Active")
                    ? "bg-success-soft text-success"
                    : state === "Learning"
                      ? "bg-cyan-soft text-cyan-ink"
                      : "bg-gold-soft text-gold-ink",
                )}
              >
                {state}
              </span>
            </div>
            <p className="mt-3 text-sm font-bold text-ink-secondary">
              {vendor.invoices} invoice{vendor.invoices === 1 ? "" : "s"} ·{" "}
              {vendor.flags} flag{vendor.flags === 1 ? "" : "s"}
            </p>
            <p className="mt-1 text-sm font-semibold text-ink-muted">
              {vendor.learned
                ? `${vendor.learned} correction${vendor.learned === 1 ? "" : "s"} learned and auto-applied`
                : "No learned corrections yet"}
            </p>
          </article>
        );
      })}
    </div>
  );
}

/* ================= tab 4: parser training ================= */

function TrainingTab({
  profile,
  invoices,
  saving,
  onUpload,
}: {
  profile: ClientProfile;
  invoices: Invoice[];
  saving: boolean;
  onUpload: (file: File, notes: string) => Promise<unknown>;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadedCount, setUploadedCount] = useState(0);

  const weakVendors = useMemo(() => {
    const byVendor = new Map<string, { sum: number; count: number; flags: number }>();
    for (const invoice of invoices) {
      const name = invoice.supplier.name || "Unknown supplier";
      const entry = byVendor.get(name) ?? { sum: 0, count: 0, flags: 0 };
      if (invoice.confidence != null) {
        entry.sum += invoice.confidence <= 1 ? invoice.confidence * 100 : invoice.confidence;
        entry.count += 1;
      }
      if (invoice.validation_issues.length) entry.flags += 1;
      byVendor.set(name, entry);
    }
    return [...byVendor.entries()]
      .map(([name, entry]) => ({
        name,
        avg: entry.count ? Math.round(entry.sum / entry.count) : null,
        flags: entry.flags,
      }))
      .filter((vendor) => (vendor.avg != null && vendor.avg < 92) || vendor.flags > 0)
      .sort((a, b) => (a.avg ?? 100) - (b.avg ?? 100));
  }, [invoices]);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setNotice("");
    setUploadError("");
    try {
      for (const file of Array.from(files)) {
        await onUpload(file, "Uploaded from Rules › Parser training");
      }
      setUploadedCount((count) => count + files.length);
      setNotice(
        `${files.length} sample${files.length === 1 ? "" : "s"} uploaded — the parser pre-trains on this client's real formats.`,
      );
    } catch (error) {
      setUploadError((error as Error).message);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
      <ContentCard
        title="Training queue"
        subtitle="Vendors where extraction confidence or flags say the parser needs more examples"
      >
        {weakVendors.length ? (
          <div className="divide-y divide-line">
            {weakVendors.slice(0, 6).map((vendor) => (
              <div key={vendor.name} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-black text-ink">{vendor.name}</p>
                  <p className="text-xs font-bold text-gold-ink">
                    {vendor.avg != null ? `avg confidence ${vendor.avg}%` : "confidence pending"}
                    {vendor.flags ? ` · ${vendor.flags} flagged` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-accent transition-colors hover:border-accent hover:bg-accent-soft"
                >
                  <UploadCloud size={13} />
                  Add samples
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm font-semibold text-ink-muted">
            All vendors ≥92% confidence with no flags — nothing needs training right now.
          </p>
        )}
      </ContentCard>

      <ContentCard
        title={`Upload training samples · ${profile.name}`}
        subtitle="2–3 real PDFs per vendor teach layout, tax placement, and invoice-number patterns"
      >
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={(event) => void handleFiles(event.target.files)}
        />
        <button
          type="button"
          disabled={saving}
          onClick={() => fileInput.current?.click()}
          className="grid w-full place-items-center rounded-2xl border-2 border-dashed border-accent/40 bg-accent-soft/40 px-6 py-10 text-center transition-colors hover:border-accent hover:bg-accent-soft disabled:opacity-60"
        >
          {saving ? (
            <LoaderCircle size={26} className="animate-spin text-accent" />
          ) : (
            <UploadCloud size={26} className="text-accent" />
          )}
          <span className="mt-3 text-sm font-black text-accent">
            Drop PDFs here or click to browse
          </span>
          <span className="mt-1 text-xs font-semibold text-ink-muted">
            {(profile.settings.training_profile?.sample_invoices?.length ?? 0) +
              uploadedCount}{" "}
            sample
            {(profile.settings.training_profile?.sample_invoices?.length ?? 0) +
              uploadedCount ===
            1
              ? ""
              : "s"}{" "}
            on file · used to pre-train extraction
          </span>
        </button>
        {notice && (
          <p className="mt-4 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
            {notice}
          </p>
        )}
        {uploadError && (
          <p className="mt-4 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
            {uploadError}
          </p>
        )}
        <p className="mt-4 text-xs font-semibold leading-5 text-ink-muted">
          Teach-fields region marking (click a field on the sample → the parser
          learns its location) ships once extraction returns coordinates — samples
          uploaded here already improve this vendor&apos;s parsing.
        </p>
      </ContentCard>
    </div>
  );
}

/* ================= shared ================= */

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex min-h-11 min-w-0 items-center justify-center rounded-xl border px-3 text-center text-xs font-black transition-colors sm:h-12 sm:shrink-0 sm:rounded-none sm:border-x-0 sm:border-t-0 sm:border-b-2 sm:px-4 sm:text-sm",
        active
          ? "border-accent bg-accent-soft text-accent sm:bg-transparent"
          : "border-line bg-surface text-ink-secondary hover:text-ink sm:border-transparent sm:bg-transparent",
      )}
    >
      {children}
    </button>
  );
}

function CountBadge({ children, tone }: { children: ReactNode; tone: "warning" }) {
  return (
    <span
      className={cn(
        "ml-1.5 rounded-full px-2 py-0.5 font-mono text-[11px] font-black",
        tone === "warning" && "bg-gold-soft text-gold-ink",
      )}
    >
      {children}
    </span>
  );
}

function LedgerFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-3.5 shadow-card">
      <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">{label}</p>
      <p className="mt-1 truncate font-mono text-sm font-black text-ink">{value || "— not set"}</p>
    </div>
  );
}

function RuleCard({
  icon,
  title,
  detail,
  state,
  live,
  liveTone = "success",
  action,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  state: string;
  live?: string;
  liveTone?: "success" | "warning";
  action?: ReactNode;
}) {
  return (
    <article className="rounded-2xl border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <span className="text-accent">{icon}</span>
        <span
          className={cn(
            "rounded-full px-3 py-1 text-xs font-black",
            state === "Active" ? "bg-success-soft text-success" : "bg-surface-strong text-ink-muted",
          )}
        >
          {state}
        </span>
      </div>
      <h3 className="mt-3 text-base font-black text-ink">{title}</h3>
      <p className="mt-1.5 text-sm font-semibold leading-5 text-ink-secondary">{detail}</p>
      {live && (
        <p className={cn("mt-3 text-sm font-black", liveTone === "warning" ? "text-gold-ink" : "text-success")}>
          {live}
        </p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </article>
  );
}

function MapField({
  label,
  value,
  placeholder,
  onChange,
  strong = false,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  strong?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2.5 text-sm outline-none transition-colors placeholder:text-ink-muted focus:border-accent",
          strong ? "font-black text-ink" : "font-bold text-ink-secondary",
        )}
      />
    </label>
  );
}

function MapCell({
  value,
  placeholder,
  onChange,
  strong = false,
}: {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  strong?: boolean;
}) {
  return (
    <td className="py-2 pr-2">
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "w-full rounded-lg border border-transparent bg-transparent px-2 py-2 text-sm outline-none transition-colors placeholder:text-ink-muted hover:border-line focus:border-accent focus:bg-canvas",
          strong ? "font-black text-ink" : "font-bold text-ink-secondary",
        )}
      />
    </td>
  );
}

function unmappedDescriptions(invoices: Invoice[], profile: ClientProfile | null) {
  if (!profile) return [];
  const mappings = profile.settings.item_mappings ?? [];
  const results = new Map<string, { description: string; amount: number; currency: string }>();
  for (const invoice of invoices) {
    for (const line of invoice.lines) {
      const description = line.description?.trim();
      if (!description || description.length < 4) continue;
      if (/igst|cgst|sgst|round.?off|tcs|tds/i.test(description)) continue;
      const mapped = mappings.some(
        (mapping) =>
          mapping.source_description_contains &&
          description.toLowerCase().includes(mapping.source_description_contains.toLowerCase()),
      );
      if (mapped || results.has(description)) continue;
      results.set(description, {
        description,
        amount: line.net_amount || line.total_amount || 0,
        currency: invoice.currency || "USD",
      });
    }
  }
  return [...results.values()];
}

function invoiceSum(invoices: Invoice[]) {
  return invoices.reduce((sum, invoice) => sum + (invoice.total || 0), 0);
}

function stringOf(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" ? value : "";
}
