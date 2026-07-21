"use client";

import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  FileText,
  Link2,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ClientProfilesPanel } from "@/components/client-profiles-panel";
import { ContentCard } from "@/components/dashboard/content-card";
import { LoadingState } from "@/components/dashboard/loading-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button } from "@/components/ui/button";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import {
  exceptionInvoices,
  invoiceTotal,
  readyInvoices,
} from "@/lib/invoice-metrics";
import type {
  AccountingSystem,
  TallyConnectorProfileStatus,
  TallyConnectorStatusResponse,
} from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

export interface AccountingSystemConfig {
  system: AccountingSystem;
  name: string;
  section: string;
  category: string;
  description: string;
  status: "pilot-ready" | "configured" | "export-ready" | "planned";
  connection: string;
  postingObject: string;
  masterData: string;
  direction: string;
  primaryAction: string;
  checklist: string[];
  notes: string[];
}

const statusLabels: Record<AccountingSystemConfig["status"], string> = {
  "pilot-ready": "Pilot ready",
  configured: "Configured",
  "export-ready": "Export ready",
  planned: "Planned",
};

export function AccountingSystemPage({ config }: { config: AccountingSystemConfig }) {
  const { invoices, loading, error } = useWorkspaceInvoices();
  const ready = readyInvoices(invoices);
  const blocked = exceptionInvoices(invoices);
  const total = invoiceTotal(ready);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title={config.name}
        section={config.section}
        description={config.description}
        action={<SystemStatus status={config.status} />}
      />

      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="rounded-2xl border border-line bg-surface px-5 py-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <InfoCell label="Connection" value={config.connection} />
            <InfoCell label="Posting object" value={config.postingObject} />
            <InfoCell label="Master data" value={config.masterData} />
            <InfoCell label="Direction" value={config.direction} />
          </div>
        </section>

        {loading ? (
          <LoadingState label={`Loading ${config.name} readiness`} />
        ) : (
          <>
            {error && (
              <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger">
                {error}
              </div>
            )}

            <section className="grid gap-4 lg:grid-cols-3">
              <MetricCard
                label="Ready invoices"
                value={ready.length}
                detail="Validated or approved for posting"
                tone="success"
                icon={<CheckCircle2 size={18} />}
              />
              <MetricCard
                label="Ready value"
                value={formatCurrency(total, invoices[0]?.currency || "USD")}
                detail="Across the current workspace queue"
                tone="accent"
                icon={<FileText size={18} />}
              />
              <MetricCard
                label="Blocked"
                value={blocked.length}
                detail="Need field, ledger, tax, or vendor review"
                tone={blocked.length ? "warning" : "default"}
                icon={<CircleDashed size={18} />}
              />
            </section>
          </>
        )}

        <SetupStepper config={config} />

        <section className="grid gap-6 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.1fr)]">
          <SystemSetupCard config={config} />
          <ContentCard
            title={`${config.name} posting workflow`}
            subtitle="The same operational steps from the working SiftEntry pilot, organized for a multi-client SaaS workspace."
            action={<Link2 size={18} className="text-cyan" />}
          >
            <div className="space-y-4">
              {config.checklist.map((item, index) => (
                <div
                  key={item}
                  className="flex gap-4 border-b border-line pb-4 last:border-b-0 last:pb-0"
                >
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-black text-accent-ink dark:text-cyan">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-black text-ink">{item}</p>
                    <p className="mt-1 text-sm leading-6 text-ink-secondary">
                      Designed to match the proven SiftEntry pilot steps before
                      enabling production posting from this console.
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </ContentCard>

        </section>

        <ClientProfilesPanel
          accountingSystem={config.system}
          showSystemField={false}
          title={`${config.name} client profiles`}
          subtitle="Profiles are the source of truth for company names, country/tax defaults, ledgers, item names, and posting mode."
        />
      </main>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </p>
      <p className="mt-1 text-sm font-black text-ink">{value}</p>
    </div>
  );
}

function SystemSetupCard({ config }: { config: AccountingSystemConfig }) {
  if (config.system === "tally") return <TallySetupCard config={config} />;

  const cloudSystem =
    config.system === "quickbooks" || config.system === "zoho_books";
  return (
    <ContentCard
      title={`${config.name} setup`}
      subtitle={
        cloudSystem
          ? "Save non-secret workspace metadata here. OAuth secrets remain server-side."
          : "Export-first systems use profile-backed package templates before live API posting."
      }
      action={<ShieldCheck size={18} className="text-success" />}
    >
      <div className="space-y-3">
        {config.notes.map((note) => (
          <div
            key={note}
            className="rounded-xl border border-line bg-surface-subtle px-4 py-3 text-sm font-semibold leading-6 text-ink-secondary"
          >
            {note}
          </div>
        ))}
        <Button className="mt-2 w-full justify-between">
          {config.primaryAction}
          <ArrowRight size={16} />
        </Button>
      </div>
    </ContentCard>
  );
}

const CONNECTOR_STATUS_REFRESH_MS = 15_000;

function describeLastSeen(seconds: number | null): string {
  if (seconds === null) return "Never connected";
  if (seconds < 5) return "Just now";
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

function ConnectorBadge({ status }: { status: TallyConnectorProfileStatus }) {
  if (!status.connector_enabled) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-subtle px-3 py-1 text-xs font-black text-ink-muted">
        <CircleDashed size={13} />
        Disabled
      </span>
    );
  }
  if (status.connected) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success-soft px-3 py-1 text-xs font-black text-success">
        <span className="size-2 rounded-full bg-success" />
        Connected
      </span>
    );
  }
  if (status.last_seen_at) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-danger/30 bg-danger-soft px-3 py-1 text-xs font-black text-danger">
        <span className="size-2 rounded-full bg-danger" />
        Disconnected
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold-soft px-3 py-1 text-xs font-black text-gold">
      <CircleDashed size={13} />
      Waiting for first check-in
    </span>
  );
}

function TallySetupCard({ config }: { config: AccountingSystemConfig }) {
  const { activeOrganizationId } = useAuth();
  const [statuses, setStatuses] = useState<TallyConnectorProfileStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const loadStatus = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeOrganizationId) return;
      try {
        const response = await fetch(
          `/api/organizations/${activeOrganizationId}/connectors/tally/status`,
          { signal, cache: "no-store" },
        );
        if (!response.ok) {
          throw new Error(`Connector status returned HTTP ${response.status}.`);
        }
        const payload = (await response.json()) as TallyConnectorStatusResponse;
        setStatuses(payload.statuses);
        setError("");
        setRefreshedAt(new Date());
      } catch (caught) {
        if ((caught as Error).name === "AbortError") return;
        setError((caught as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [activeOrganizationId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const kickoff = window.setTimeout(() => {
      void loadStatus(controller.signal);
    }, 0);
    const timer = window.setInterval(() => {
      void loadStatus(controller.signal);
    }, CONNECTOR_STATUS_REFRESH_MS);
    return () => {
      window.clearTimeout(kickoff);
      window.clearInterval(timer);
      controller.abort();
    };
  }, [loadStatus]);

  return (
    <ContentCard
      title="Windows connector status"
      subtitle="Live view of the SiftEntry Tally Connector running beside TallyPrime on the client's computer. Updates automatically."
      action={
        <button
          type="button"
          onClick={() => void loadStatus()}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-ink-secondary transition-colors hover:border-accent hover:text-accent"
        >
          <RotateCcw size={13} />
          Refresh
        </button>
      }
    >
      <div className="space-y-4">
        {loading && activeOrganizationId ? (
          <p className="text-sm font-semibold text-ink-secondary">
            Checking connector status…
          </p>
        ) : error ? (
          <div className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm font-bold text-danger">
            {error}
          </div>
        ) : statuses.length === 0 ? (
          <div className="rounded-xl border border-line bg-surface-subtle px-4 py-3 text-sm font-semibold leading-6 text-ink-secondary">
            No Tally client profiles yet. Create one below with a workspace ID
            and connector token under connection settings — the connector on the
            client&apos;s computer uses those two values to check in.
          </div>
        ) : (
          statuses.map((status) => (
            <div
              key={status.client_profile_id}
              className="rounded-xl border border-line bg-surface-subtle px-4 py-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-black text-ink">
                  {status.profile_name}
                </p>
                <ConnectorBadge status={status} />
              </div>
              <div className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                <StatusLine
                  label="Tally company"
                  value={status.tally_company || "Not set on profile"}
                />
                <StatusLine
                  label="Workspace ID"
                  value={status.workspace_id || "Not configured"}
                />
                <StatusLine
                  label="Last check-in"
                  value={describeLastSeen(status.seconds_since_seen)}
                />
                <StatusLine
                  label="TallyPrime"
                  value={
                    status.tally_detected === null
                      ? "Unknown"
                      : status.tally_detected
                        ? "Detected (port 9000)"
                        : "Not detected — open TallyPrime"
                  }
                  tone={
                    status.tally_detected === false && status.connected
                      ? "warning"
                      : undefined
                  }
                />
                {status.connector_host && (
                  <StatusLine
                    label="Computer"
                    value={
                      status.connector_version
                        ? `${status.connector_host} · v${status.connector_version}`
                        : status.connector_host
                    }
                  />
                )}
                {status.last_posting_at && (
                  <StatusLine
                    label="Last posting"
                    value={`${
                      status.last_posting_invoice_number || "Invoice"
                    } — ${status.last_posting_success ? "posted" : "failed"}`}
                    tone={
                      status.last_posting_success === false
                        ? "warning"
                        : undefined
                    }
                  />
                )}
              </div>
              {!status.connector_configured && (
                <p className="mt-3 rounded-lg border border-gold/30 bg-gold-soft px-3 py-2 text-xs font-bold leading-5 text-gold">
                  Add a workspace ID and connector token to this profile&apos;s
                  connection settings, then enter the same two values in the
                  connector on the client&apos;s computer.
                </p>
              )}
            </div>
          ))
        )}
        {refreshedAt && !loading && (
          <p className="text-xs font-semibold text-ink-muted">
            Auto-refreshes every 15 seconds · Last checked{" "}
            {refreshedAt.toLocaleTimeString()}
          </p>
        )}
        <a
          href="/downloads/SiftEntry-Tally-Connector-Kit.zip"
          download
          className="flex items-center justify-between gap-3 rounded-xl border border-accent/40 bg-accent-soft px-4 py-3 transition-colors hover:border-accent"
        >
          <span className="min-w-0">
            <span className="block text-sm font-black text-accent-ink dark:text-cyan">
              Download the Windows connector kit
            </span>
            <span className="mt-0.5 block text-xs font-semibold leading-5 text-ink-secondary">
              Zip with the connector, setup scripts, and a plain-language guide
              for the client&apos;s accountant.
            </span>
          </span>
          <ArrowRight size={16} className="shrink-0 text-accent" />
        </a>
        <div className="space-y-3">
          {config.notes.map((note) => (
            <div
              key={note}
              className="rounded-xl border border-line bg-surface-subtle px-4 py-3 text-sm font-semibold leading-6 text-ink-secondary"
            >
              {note}
            </div>
          ))}
        </div>
      </div>
    </ContentCard>
  );
}

function StatusLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warning";
}) {
  return (
    <div>
      <p className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </p>
      <p
        className={`mt-0.5 text-sm font-bold ${
          tone === "warning" ? "text-gold" : "text-ink"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

const stepperSteps: Record<string, { title: string; detail: string }[]> = {
  tally: [
    {
      title: "Install the connector on the client's computer",
      detail:
        "Download the SiftEntry Tally Connector kit below and run it on the Windows machine where TallyPrime lives.",
    },
    {
      title: "Enable HTTP/XML in TallyPrime",
      detail: "F1 › Settings › Connectivity — allow local XML requests (port 9000).",
    },
    {
      title: "Enter the workspace ID & connector token",
      detail:
        "Copy both values from the client profile below into the connector's settings window, then start it.",
    },
    {
      title: "Watch the status card turn green",
      detail:
        "\"Connected\" plus \"Tally detected\" in the connector status card below means the pipe is live.",
    },
    {
      title: "Post a sample voucher (dry run)",
      detail:
        "Approve a test invoice with dry run on — proves the flow without touching real books.",
    },
  ],
  cloud: [
    {
      title: "Authorize the workspace",
      detail: "Connect via OAuth — secrets stay server-side, never in the browser.",
    },
    {
      title: "Pick the company / organization",
      detail: "Choose which books this workspace posts into.",
    },
    {
      title: "Map default ledgers & taxes",
      detail: "Set purchase and tax accounts on the client profile.",
    },
    {
      title: "Post a sample bill (sandbox)",
      detail: "Dry-run a bill to confirm accounts resolve before live posting.",
    },
  ],
  export: [
    {
      title: "Choose the export template",
      detail: "Bill package with attachments, mapped to this system's import format.",
    },
    {
      title: "Map fields on the client profile",
      detail: "Vendor, GL, tax, and item columns aligned to the import sheet.",
    },
    {
      title: "Run a sample export",
      detail: "Download one package and validate it in the target system.",
    },
  ],
};

function SetupStepper({ config }: { config: AccountingSystemConfig }) {
  const steps =
    config.system === "tally"
      ? stepperSteps.tally
      : config.system === "quickbooks" || config.system === "zoho_books"
        ? stepperSteps.cloud
        : stepperSteps.export;
  const storageKey = `siftentry.setup.${config.system}`;
  function readStoredSteps() {
    if (typeof window === "undefined") {
      return { done: steps.map(() => false), collapsed: false };
    }
    try {
      const stored = JSON.parse(
        window.localStorage.getItem(storageKey) || "[]",
      ) as boolean[];
      if (Array.isArray(stored) && stored.length === steps.length) {
        return { done: stored, collapsed: stored.every(Boolean) };
      }
    } catch {
      /* fresh setup */
    }
    return { done: steps.map(() => false), collapsed: false };
  }
  const initialSteps = readStoredSteps();
  const [done, setDone] = useState<boolean[]>(initialSteps.done);
  const [collapsed, setCollapsed] = useState(initialSteps.collapsed);

  function toggle(index: number) {
    setDone((current) => {
      const next = current.map((value, i) => (i === index ? !value : value));
      window.localStorage.setItem(storageKey, JSON.stringify(next));
      if (next.every(Boolean)) setCollapsed(true);
      return next;
    });
  }

  const completed = done.filter(Boolean).length;

  if (collapsed && completed === steps.length) {
    return (
      <section className="flex flex-col gap-3 rounded-2xl border border-success/30 bg-success-soft/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-black text-success">
          <CheckCircle2 size={16} className="mr-1.5 inline" />
          Setup complete — all {steps.length} steps verified. This page now leads
          with live status and client profiles.
        </p>
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-ink-secondary transition-colors hover:border-accent hover:text-accent"
        >
          <RotateCcw size={13} />
          Re-run setup steps
        </button>
      </section>
    );
  }

  return (
    <ContentCard
      title={`${config.name} setup guide`}
      subtitle={`${completed} of ${steps.length} steps complete — check off each step as you finish it. Re-runnable anytime.`}
      action={
        completed === steps.length ? (
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-black text-ink-secondary transition-colors hover:border-accent hover:text-accent"
          >
            <ChevronDown size={13} />
            Collapse
          </button>
        ) : undefined
      }
    >
      <div className="space-y-0">
        {steps.map((step, index) => (
          <button
            key={step.title}
            type="button"
            onClick={() => toggle(index)}
            className="flex w-full gap-4 border-b border-line py-4 text-left transition-colors last:border-b-0 hover:bg-surface-subtle first:pt-0 last:pb-0"
          >
            <span
              className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-black transition-colors ${
                done[index]
                  ? "bg-success text-white"
                  : index === done.findIndex((value) => !value)
                    ? "bg-accent text-white"
                    : "bg-surface-strong text-ink-muted"
              }`}
            >
              {done[index] ? "✓" : index + 1}
            </span>
            <span className="min-w-0">
              <span
                className={`block text-sm font-black ${done[index] ? "text-ink-muted line-through" : "text-ink"}`}
              >
                {step.title}
              </span>
              <span className="mt-0.5 block text-sm leading-5 text-ink-secondary">
                {step.detail}
              </span>
            </span>
          </button>
        ))}
      </div>
    </ContentCard>
  );
}

function SystemStatus({
  status,
}: {
  status: AccountingSystemConfig["status"];
}) {
  const ready = status === "pilot-ready" || status === "configured";
  return (
    <span className="inline-flex h-10 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm font-black text-ink-secondary">
      {ready ? (
        <ShieldCheck size={16} className="text-success" />
      ) : (
        <CircleDashed size={16} className="text-gold" />
      )}
      {statusLabels[status]}
    </span>
  );
}
