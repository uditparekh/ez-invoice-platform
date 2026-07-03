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
import { useState } from "react";

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
import type { AccountingSystem } from "@/lib/types";
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
            subtitle="The same operational steps from the working EZ-Invoice pilot, organized for a multi-client SaaS workspace."
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
                      Designed to match the proven EZ-Invoice pilot steps before
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

function TallySetupCard({ config }: { config: AccountingSystemConfig }) {
  const [connectorUrl, setConnectorUrl] = useState("http://127.0.0.1:8765");
  const [token, setToken] = useState("");
  const [testing, setTesting] = useState<"health" | "tally" | null>(null);
  const [message, setMessage] = useState("");
  const [ok, setOk] = useState<boolean | null>(null);

  async function runTest(mode: "health" | "tally") {
    setTesting(mode);
    setMessage("");
    setOk(null);
    try {
      const response = await fetch("/api/integrations/tally/test-connector", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connectorUrl, token, mode }),
      });
      const payload = (await response.json()) as {
        success?: boolean;
        message?: string;
      };
      setOk(Boolean(payload.success && response.ok));
      setMessage(payload.message ?? "No response returned.");
    } catch (error) {
      setOk(false);
      setMessage((error as Error).message);
    } finally {
      setTesting(null);
    }
  }

  return (
    <ContentCard
      title="Local connector"
      subtitle="Use this on the Windows computer where TallyPrime is open with HTTP/XML enabled."
      action={<ShieldCheck size={18} className="text-success" />}
    >
      <div className="space-y-4">
        <label className="block">
          <span className="text-[11px] font-extrabold uppercase text-ink-muted">
            Connector URL
          </span>
          <input
            value={connectorUrl}
            onChange={(event) => setConnectorUrl(event.target.value)}
            className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="text-[11px] font-extrabold uppercase text-ink-muted">
            Connector token
          </span>
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Local test token"
            className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <Button
            variant="secondary"
            onClick={() => void runTest("health")}
            disabled={Boolean(testing)}
          >
            {testing === "health" ? "Testing..." : "Test connector"}
          </Button>
          <Button
            variant="primary"
            onClick={() => void runTest("tally")}
            disabled={Boolean(testing)}
          >
            {testing === "tally" ? "Testing..." : config.primaryAction}
          </Button>
        </div>
        {message && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm font-bold leading-6 ${
              ok
                ? "border-success/30 bg-success-soft text-success"
                : "border-gold/30 bg-gold-soft text-gold"
            }`}
          >
            {message}
          </div>
        )}
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

const stepperSteps: Record<string, { title: string; detail: string }[]> = {
  tally: [
    {
      title: "Download the local connector",
      detail:
        "SiftEntry-Bridge for Windows — runs beside TallyPrime on the client machine.",
    },
    {
      title: "Enable HTTP/XML in TallyPrime",
      detail: "F1 › Settings › Connectivity — allow local XML requests (port 9000).",
    },
    {
      title: "Enter connector URL & token",
      detail:
        "Use the Local connector card below — defaults to http://127.0.0.1:8765.",
    },
    {
      title: "Test the connection",
      detail: "Run \"Test connector\" below — a healthy bridge answers in milliseconds.",
    },
    {
      title: "Post a sample voucher (sandbox)",
      detail:
        "Run the sample-voucher test below — proves the pipe without touching real books.",
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
