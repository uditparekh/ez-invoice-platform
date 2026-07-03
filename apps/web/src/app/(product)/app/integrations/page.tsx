import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileCog,
  FileSpreadsheet,
  KeyRound,
  Landmark,
  Network,
  PlugZap,
  RefreshCcw,
  ShieldCheck,
  Table2,
  Workflow,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/page-header";

const systems = [
  {
    name: "QuickBooks",
    href: "/app/accounting/quickbooks",
    icon: Network,
    status: "Pilot ready",
    statusTone: "success",
    connection: "OAuth API",
    object: "Supplier Bill",
    masterData: "Vendors + taxes",
    detail: "Post approved bills through the QuickBooks sandbox or connected client company.",
  },
  {
    name: "Tally",
    href: "/app/accounting/tally",
    icon: Table2,
    status: "Pilot ready",
    statusTone: "success",
    connection: "Local XML bridge",
    object: "Item Invoice / Voucher",
    masterData: "Ledgers + stock items",
    detail: "Use the Windows connector beside TallyPrime for profile-owned posting.",
  },
  {
    name: "Zoho Books",
    href: "/app/accounting/zoho-books",
    icon: FileSpreadsheet,
    status: "Configured",
    statusTone: "success",
    connection: "OAuth API",
    object: "Bill",
    masterData: "Contacts + taxes",
    detail: "Cloud bill posting path ready for sandbox validation and pilot rollout.",
  },
  {
    name: "Coupa",
    href: "/app/accounting/coupa",
    icon: Database,
    status: "Export ready",
    statusTone: "neutral",
    connection: "Package export",
    object: "Invoice payload",
    masterData: "Suppliers + account codes",
    detail: "Download a clean AP import package while direct API setup is planned.",
  },
  {
    name: "NetSuite",
    href: "/app/accounting/netsuite",
    icon: Landmark,
    status: "Export ready",
    statusTone: "neutral",
    connection: "Package export",
    object: "Vendor bill",
    masterData: "Subsidiaries + dimensions",
    detail: "Prepare vendor bill files with client-specific mappings and dimensions.",
  },
  {
    name: "SAP",
    href: "/app/accounting/sap",
    icon: FileCog,
    status: "Planned",
    statusTone: "muted",
    connection: "API / IDoc",
    object: "AP document",
    masterData: "Company codes + GL",
    detail: "Enterprise path for BAPI, IDoc, or template-based AP posting.",
  },
] as const;

export default function IntegrationsPage() {
  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Integrations"
        section="Posting paths"
        description="Connect each client profile to the accounting system they already use."
        action={
          <Link
            href="/app/client-profiles"
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-accent bg-accent px-4 text-sm font-black text-white shadow-sm shadow-accent/20 transition-colors hover:bg-accent-hover"
          >
            Manage profiles
            <ArrowRight size={16} />
          </Link>
        }
      />

      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="overflow-hidden rounded-[28px] border border-line bg-surface shadow-card">
          <div className="grid divide-y divide-line lg:grid-cols-4 lg:divide-x lg:divide-y-0">
            <IntegrationFact
              label="Live systems"
              value="QuickBooks · Tally · Zoho"
              icon={<PlugZap size={18} />}
            />
            <IntegrationFact
              label="Profile-owned"
              value="Ledgers, taxes, rules"
              icon={<ShieldCheck size={18} />}
            />
            <IntegrationFact
              label="Retry history"
              value="Backend posting logs"
              icon={<RefreshCcw size={18} />}
            />
            <IntegrationFact
              label="Secure boundary"
              value="Client-scoped tokens"
              icon={<KeyRound size={18} />}
            />
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {systems.map((system) => (
            <Link
              key={system.name}
              href={system.href}
              className="group flex min-h-[286px] flex-col rounded-[28px] border border-line bg-surface p-5 shadow-card transition-colors hover:border-accent hover:bg-accent-soft dark:hover:bg-surface-strong"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="grid size-[52px] place-items-center rounded-2xl bg-gradient-to-br from-accent to-cyan text-white shadow-glow">
                  <system.icon size={22} />
                </span>
                <StatusPill tone={system.statusTone}>{system.status}</StatusPill>
              </div>

              <div className="mt-5 min-w-0">
                <p className="text-[11px] font-black uppercase tracking-[0.16em] text-ink-muted">
                  Accounting system
                </p>
                <h2 className="mt-1 text-2xl font-black tracking-tight text-ink">
                  {system.name}
                </h2>
                <p className="mt-3 min-h-12 text-sm font-semibold leading-6 text-ink-secondary">
                  {system.detail}
                </p>
              </div>

              <div className="mt-5 grid gap-2">
                <SystemFact label="Connection" value={system.connection} />
                <SystemFact label="Posting object" value={system.object} />
                <SystemFact label="Master data" value={system.masterData} />
              </div>

              <span className="mt-auto inline-flex items-center gap-2 pt-5 text-sm font-black text-accent dark:text-cyan">
                Open setup
                <ArrowRight
                  size={15}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </span>
            </Link>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-[28px] border border-line bg-surface p-5 shadow-card">
            <div className="flex items-start gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent-ink dark:text-cyan">
                <Workflow size={19} />
              </span>
              <div className="min-w-0">
                <h2 className="text-lg font-black text-ink">
                  Posting flow
                </h2>
                <p className="mt-1 text-sm leading-6 text-ink-secondary">
                  Every accounting action starts from the selected client profile, then writes a posting log with the exact system response.
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-4">
              {[
                ["1", "Client profile", "Country, tax mode, ledgers, connector."],
                ["2", "Approved invoice", "Validated fields and line items."],
                ["3", "Target payload", "Bill, voucher, XML, or export package."],
                ["4", "Posting log", "Success, failure, retry, and audit trail."],
              ].map(([step, title, detail]) => (
                <div
                  key={step}
                  className="rounded-2xl border border-line bg-canvas p-4"
                >
                  <span className="grid size-8 place-items-center rounded-full bg-accent text-sm font-black text-white">
                    {step}
                  </span>
                  <p className="mt-3 text-sm font-black text-ink">{title}</p>
                  <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
                    {detail}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[28px] border border-line bg-surface p-5 shadow-card">
            <p className="text-[11px] font-black uppercase tracking-[0.16em] text-ink-muted">
              Connector experience
            </p>
            <h2 className="mt-2 text-lg font-black text-ink">
              Tally runs locally. SiftEntry stays in the cloud.
            </h2>
            <div className="mt-5 space-y-3">
              {[
                "Client installs the Windows connector beside TallyPrime.",
                "Connector shows Tally detected, cloud connected, last posted invoice, and retry jobs.",
                "SiftEntry queues approved vouchers and the connector posts them securely.",
              ].map((item) => (
                <div
                  key={item}
                  className="flex gap-3 rounded-2xl border border-line bg-canvas p-3"
                >
                  <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-success" />
                  <p className="text-sm font-semibold leading-6 text-ink-secondary">
                    {item}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function IntegrationFact({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <div className="flex min-h-28 items-center gap-3 px-5 py-4">
      <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent-ink dark:text-cyan">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-black uppercase tracking-[0.16em] text-ink-muted">
          {label}
        </p>
        <p className="mt-1 truncate text-base font-black text-ink">{value}</p>
      </div>
    </div>
  );
}

function SystemFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-2xl border border-line bg-canvas px-3 py-2.5">
      <span className="shrink-0 text-[10px] font-black uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </span>
      <span className="truncate text-right text-xs font-black text-ink">
        {value}
      </span>
    </div>
  );
}

function StatusPill({
  children,
  tone,
}: {
  children: string;
  tone: "success" | "neutral" | "muted";
}) {
  const styles =
    tone === "success"
      ? "border-success/25 bg-success-soft text-success"
      : tone === "neutral"
        ? "border-cyan/25 bg-cyan-soft text-cyan"
        : "border-line bg-surface-subtle text-ink-muted";

  return (
    <span
      className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-black ${styles}`}
    >
      {tone === "success" && <CheckCircle2 size={13} />}
      {children}
    </span>
  );
}
