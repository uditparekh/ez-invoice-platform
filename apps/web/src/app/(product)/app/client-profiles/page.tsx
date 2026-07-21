"use client";

import {
  ArrowRight,
  CheckCircle2,
  LoaderCircle,
  Plus,
  Settings2,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ProfileWizard } from "@/components/client-profiles/profile-wizard";
import { FormatRegistry } from "@/components/training/format-registry";
import { ClientProfilesPanel } from "@/components/client-profiles-panel";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { PageHeader } from "@/components/dashboard/page-header";
import { useClientProfiles } from "@/hooks/use-client-profiles";
import type { ClientProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Client profiles — UI Spec §13.
 *  Overview-first: pending-approval banner, profile cards with real setup
 *  status, "+ New profile" full-screen wizard. The advanced editor (the full
 *  panel with connection settings, mappings, templates, AI readiness) stays
 *  one click away — nothing lost, everything organized. */

const statusLabels: Record<string, string> = {
  draft: "Draft",
  samples_added: "Samples added",
  ready_for_admin_review: "Pending approval",
  active: "Active",
};

export default function ClientProfilesPage() {
  const {
    profiles,
    loading,
    saving,
    error,
    reload,
    createProfile,
    updateProfile,
    uploadTrainingSample,
  } = useClientProfiles();

  const [wizardOpen, setWizardOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [activating, setActivating] = useState("");
  const [notice, setNotice] = useState("");

  const pending = useMemo(
    () =>
      profiles.filter(
        (profile) =>
          onboardingStatus(profile) === "ready_for_admin_review",
      ),
    [profiles],
  );

  async function approveAndActivate(profile: ClientProfile) {
    setActivating(profile.id);
    setNotice("");
    try {
      await updateProfile(profile.id, {
        settings: {
          ...profile.settings,
          training_profile: {
            ...profile.settings.training_profile,
            onboarding_status: "active",
          },
        },
      });
      setNotice(`${profile.name} approved & activated — live posting enabled.`);
    } catch (approveError) {
      setNotice((approveError as Error).message);
    } finally {
      setActivating("");
    }
  }

  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Client profiles"
        section="Per-client accounting logic"
        description="Each profile holds the system, tax behavior, ledgers, mappings, and training samples for one client."
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setEditorOpen((open) => !open)}
              className={cn(
                "inline-flex h-11 items-center gap-2 rounded-xl border px-4 text-sm font-black transition-colors",
                editorOpen
                  ? "border-accent bg-accent-soft text-accent-ink"
                  : "border-line-strong bg-surface text-ink-secondary hover:border-accent hover:text-accent",
              )}
            >
              <Settings2 size={16} />
              Advanced editor
            </button>
            <button
              type="button"
              onClick={() => setWizardOpen(true)}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/25 transition-colors hover:bg-accent-hover"
            >
              <Plus size={16} />
              New profile
            </button>
          </div>
        }
      />

      <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        {loading ? (
          <LoadingState label="Loading client profiles" />
        ) : error ? (
          <p className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
            {error}
          </p>
        ) : (
          <>
            {notice && (
              <p className="rounded-2xl border border-success/30 bg-success-soft px-4 py-3 text-sm font-bold text-success">
                {notice}
              </p>
            )}

            {/* pending approvals — the admin flow */}
            {pending.map((profile) => (
              <div
                key={profile.id}
                className="flex flex-col gap-3 rounded-2xl border border-gold-soft bg-gold-soft/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm font-black text-ink">
                    {profile.name}{" "}
                    <span className="ml-1 rounded-full bg-gold/15 px-2.5 py-0.5 text-[11px] font-black uppercase tracking-wide text-gold-ink">
                      Pending approval
                    </span>
                  </p>
                  <p className="mt-1 text-sm font-semibold text-gold-ink">
                    {systemLabel(profile)} · {profile.settings.country_name} ·{" "}
                    {sampleCount(profile)} sample
                    {sampleCount(profile) === 1 ? "" : "s"} attached · awaiting
                    admin review before live posting
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditorOpen(true)}
                    className="inline-flex h-10 items-center rounded-xl border border-line-strong bg-surface px-3.5 text-sm font-black text-ink-secondary transition-colors hover:border-accent hover:text-accent"
                  >
                    Review setup
                  </button>
                  <button
                    type="button"
                    disabled={activating === profile.id || saving}
                    onClick={() => void approveAndActivate(profile)}
                    className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-success px-4 text-sm font-black text-white transition-colors hover:bg-success/90 disabled:opacity-60"
                  >
                    {activating === profile.id ? (
                      <LoaderCircle size={15} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={15} />
                    )}
                    Approve &amp; activate
                  </button>
                </div>
              </div>
            ))}

            {/* profile cards */}
            {profiles.length ? (
              <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {profiles.map((profile) => {
                  const status = onboardingStatus(profile);
                  const mappings =
                    profile.settings.item_mappings?.length ?? 0;
                  return (
                    <article
                      key={profile.id}
                      className="flex flex-col rounded-2xl border border-line bg-surface p-5 shadow-card transition-shadow hover:shadow-pop"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent-soft font-display text-sm font-black text-accent-ink">
                          {initials(profile.name)}
                        </span>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {profile.is_default && (
                            <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-accent-ink">
                              Default
                            </span>
                          )}
                          <span
                            className={cn(
                              "rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wide",
                              status === "active"
                                ? "bg-success-soft text-success"
                                : status === "ready_for_admin_review"
                                  ? "bg-gold-soft text-gold-ink"
                                  : "bg-surface-strong text-ink-muted",
                            )}
                          >
                            {statusLabels[status] ?? status}
                          </span>
                        </div>
                      </div>
                      <h3 className="mt-3 truncate text-lg font-black text-ink">
                        {profile.name}
                      </h3>
                      <p className="mt-0.5 text-sm font-bold text-ink-secondary">
                        {systemLabel(profile)} · {postingLabel(profile)}
                      </p>
                      <p className="text-sm font-semibold text-ink-muted">
                        {profile.settings.country_name} ·{" "}
                        {profile.settings.tax_registration_label} ·{" "}
                        {profile.settings.default_currency}
                      </p>
                      <div className="mt-4 flex items-center gap-4 border-t border-line pt-3 text-xs font-bold text-ink-secondary">
                        <span>
                          {sampleCount(profile)} sample
                          {sampleCount(profile) === 1 ? "" : "s"}
                        </span>
                        <span>
                          {mappings} mapping{mappings === 1 ? "" : "s"}
                        </span>
                        <button
                          type="button"
                          onClick={() => setEditorOpen(true)}
                          className="ml-auto inline-flex items-center gap-1 font-black text-accent transition-colors hover:text-accent-hover"
                        >
                          Open profile
                          <ArrowRight size={13} />
                        </button>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : (
              <EmptyState
                icon={Users}
                title="Onboard your first client"
                description="A 4-minute wizard captures the accounting system, tax behavior, posting mode, and sample invoices."
              />
            )}

            {/* advanced editor — the full existing panel, nothing lost */}
            {editorOpen && (
              <section id="advanced-editor" className="pt-2">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-lg font-black text-ink">
                    Advanced editor
                  </h2>
                  <button
                    type="button"
                    onClick={() => setEditorOpen(false)}
                    className="text-sm font-black text-ink-secondary hover:text-accent"
                  >
                    Collapse
                  </button>
                </div>
                <ClientProfilesPanel />
              </section>
            )}
          </>
        )}
        <FormatRegistry />
      </main>

      <ProfileWizard
        open={wizardOpen}
        saving={saving}
        onClose={() => {
          setWizardOpen(false);
          void reload();
        }}
        onCreate={createProfile}
        onUploadSample={uploadTrainingSample}
      />
    </div>
  );
}

function onboardingStatus(profile: ClientProfile) {
  return profile.settings.training_profile?.onboarding_status || "draft";
}

function sampleCount(profile: ClientProfile) {
  return profile.settings.training_profile?.sample_invoices?.length ?? 0;
}

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase() || "CP"
  );
}

function systemLabel(profile: ClientProfile) {
  const labels: Record<string, string> = {
    tally: "Tally",
    quickbooks: "QuickBooks",
    zoho_books: "Zoho Books",
    coupa: "Coupa",
    netsuite: "NetSuite",
    sap: "SAP",
    excel: "Excel",
  };
  return labels[profile.accounting_system] ?? profile.accounting_system;
}

function postingLabel(profile: ClientProfile) {
  const labels: Record<string, string> = {
    item_invoice: "Item invoice",
    accounting_voucher: "Accounting voucher",
    supplier_bill: "Supplier bill",
    export_package: "Export package",
    custom: "Custom",
  };
  return labels[profile.settings.posting_mode] ?? profile.settings.posting_mode;
}
