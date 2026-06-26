"use client";

import { BrainCircuit, Route, ShieldCheck, SlidersHorizontal } from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { exceptionInvoices, readyInvoices } from "@/lib/invoice-metrics";

export default function RulesPage() {
  const { invoices } = useWorkspaceInvoices();
  const rules = [
    {
      title: "Duplicate invoice control",
      detail: "Flag matching supplier, invoice number, date, and amount before posting.",
      state: "Active",
    },
    {
      title: "Ledger readiness check",
      detail: "Require mapped purchase, tax, vendor, and item names before ERP posting.",
      state: "Active",
    },
    {
      title: "High confidence autopass",
      detail: "Allow clean invoices over the confidence threshold to move into ready status.",
      state: "Draft",
    },
    {
      title: "Natural-language approval rules",
      detail: "Example: route invoices over USD 5,000 to a senior approver.",
      state: "Planned",
    },
  ];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Rules"
        section="Automation"
        description="Configure validation thresholds, approval routing, duplicate controls, and accounting recommendations."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard
            label="Active rules"
            value="2"
            detail="Controls enforced before posting"
            tone="success"
            icon={<ShieldCheck size={18} />}
          />
          <MetricCard
            label="Ready queue"
            value={readyInvoices(invoices).length}
            detail="Invoices passing core checks"
            tone="accent"
            icon={<Route size={18} />}
          />
          <MetricCard
            label="Blocked by rules"
            value={exceptionInvoices(invoices).length}
            detail="Needs correction or mapping"
            tone={exceptionInvoices(invoices).length ? "warning" : "default"}
            icon={<SlidersHorizontal size={18} />}
          />
        </section>

        <ContentCard
          title="Rule library"
          subtitle="Reusable controls that stay generic across industries and accounting systems."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {rules.map((rule) => (
              <article
                key={rule.title}
                className="rounded-2xl border border-line bg-canvas p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <BrainCircuit className="text-cyan" size={20} />
                  <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-black text-ink-secondary">
                    {rule.state}
                  </span>
                </div>
                <h2 className="mt-4 text-base font-black text-ink">
                  {rule.title}
                </h2>
                <p className="mt-2 text-sm leading-6 text-ink-secondary">
                  {rule.detail}
                </p>
              </article>
            ))}
          </div>
        </ContentCard>
      </main>
    </div>
  );
}
