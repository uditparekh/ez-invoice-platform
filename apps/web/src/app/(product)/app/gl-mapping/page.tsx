"use client";

import { Diamond, Wand2 } from "lucide-react";

import { ContentCard } from "@/components/dashboard/content-card";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { groupCategory } from "@/lib/invoice-metrics";
import { formatCurrency } from "@/lib/utils";

export default function GlMappingPage() {
  const { invoices } = useWorkspaceInvoices();
  const categories = groupCategory(invoices);
  const rows = categories.length
    ? categories
    : [
        { label: "Materials", total: 0 },
        { label: "Services", total: 0 },
        { label: "Freight", total: 0 },
        { label: "Taxes", total: 0 },
      ];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="GL Mapping"
        section="Client rules"
        description="Map universal invoice categories to each client's accounting ledgers, tax ledgers, and item masters."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard
            label="Detected categories"
            value={categories.length}
            detail="From current invoice lines"
            tone="accent"
            icon={<Diamond size={18} />}
          />
          <MetricCard
            label="Recommendation engine"
            value="Next"
            detail="Learns from corrections"
            icon={<Wand2 size={18} />}
          />
          <MetricCard
            label="Industry logic"
            value="Generic"
            detail="No industry-specific mapping"
            tone="success"
          />
        </section>

        <ContentCard
          title="Mapping worksheet"
          subtitle="Client-specific ledger names should be filled from the accounting system master data."
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="text-xs font-extrabold uppercase text-ink-muted">
                <tr className="border-b border-line">
                  <th className="px-3 py-3">Category</th>
                  <th className="px-3 py-3">Suggested ledger</th>
                  <th className="px-3 py-3">Tax treatment</th>
                  <th className="px-3 py-3 text-right">Current spend</th>
                  <th className="px-3 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label} className="border-b border-line last:border-b-0">
                    <td className="px-3 py-4 font-black text-ink">{row.label}</td>
                    <td className="px-3 py-4 text-ink-secondary">
                      Client ledger required
                    </td>
                    <td className="px-3 py-4 text-ink-secondary">
                      Workspace tax mapping
                    </td>
                    <td className="px-3 py-4 text-right font-mono font-black text-ink">
                      {formatCurrency(row.total, invoices[0]?.currency || "USD")}
                    </td>
                    <td className="px-3 py-4 text-ink-secondary">Review</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </main>
    </div>
  );
}
