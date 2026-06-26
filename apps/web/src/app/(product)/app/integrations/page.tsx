import Link from "next/link";
import {
  ArrowRight,
  Database,
  FileCog,
  FileSpreadsheet,
  Landmark,
  Network,
  Table2,
} from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { PageHeader } from "@/components/dashboard/page-header";

export default function IntegrationsPage() {
  const systems = [
    {
      name: "QuickBooks",
      href: "/app/accounting/quickbooks",
      icon: Network,
      status: "Pilot ready",
      detail: "OAuth Bills, vendors, and account mapping.",
    },
    {
      name: "Tally",
      href: "/app/accounting/tally",
      icon: Table2,
      status: "Pilot ready",
      detail: "Local XML connector for TallyPrime purchase vouchers.",
    },
    {
      name: "Zoho Books",
      href: "/app/accounting/zoho-books",
      icon: FileSpreadsheet,
      status: "Configured",
      detail: "Cloud bill posting flow ready for sandbox validation.",
    },
    {
      name: "Coupa",
      href: "/app/accounting/coupa",
      icon: Database,
      status: "Export ready",
      detail: "Structured package for import and middleware workflows.",
    },
    {
      name: "NetSuite",
      href: "/app/accounting/netsuite",
      icon: Landmark,
      status: "Export ready",
      detail: "Vendor bill package with dimensions and subsidiaries.",
    },
    {
      name: "SAP",
      href: "/app/accounting/sap",
      icon: FileCog,
      status: "Planned",
      detail: "BAPI, IDoc, or template export path for enterprise AP.",
    },
  ];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Integrations"
        section="Accounting systems"
        description="Manage the posting paths that move approved supplier invoices into each client accounting system."
      />
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <ContentCard
          title="ERP connection matrix"
          subtitle="The React console mirrors the proven pilot coverage while keeping each system in its own setup path."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {systems.map((system) => (
              <Link
                key={system.name}
                href={system.href}
                className="group rounded-2xl border border-line bg-canvas p-5 transition-colors hover:border-accent hover:bg-accent-soft dark:hover:bg-surface-strong"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent-ink dark:text-cyan">
                    <system.icon size={20} />
                  </span>
                  <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-black text-ink-secondary">
                    {system.status}
                  </span>
                </div>
                <h2 className="mt-5 text-lg font-black text-ink">
                  {system.name}
                </h2>
                <p className="mt-2 min-h-12 text-sm leading-6 text-ink-secondary">
                  {system.detail}
                </p>
                <span className="mt-4 inline-flex items-center gap-2 text-sm font-black text-accent dark:text-cyan">
                  Open setup
                  <ArrowRight size={15} />
                </span>
              </Link>
            ))}
          </div>
        </ContentCard>
      </main>
    </div>
  );
}
