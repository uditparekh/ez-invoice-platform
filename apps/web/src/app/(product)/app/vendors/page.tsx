"use client";

import { Users } from "lucide-react";

import { BarList } from "@/components/dashboard/bar-list";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { groupSupplier, invoiceTotal } from "@/lib/invoice-metrics";
import { formatCurrency } from "@/lib/utils";

export default function VendorsPage() {
  const { invoices } = useWorkspaceInvoices();
  const suppliers = groupSupplier(invoices);
  const currency = invoices[0]?.currency || "USD";

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Vendors"
        section="Supplier intelligence"
        description="Track supplier matching, spend concentration, and master-data readiness before posting."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard
            label="Suppliers"
            value={suppliers.length}
            detail="Detected from invoice queue"
            tone="accent"
            icon={<Users size={18} />}
          />
          <MetricCard
            label="Invoices"
            value={invoices.length}
            detail="Current workspace"
          />
          <MetricCard
            label="Total spend"
            value={formatCurrency(invoiceTotal(invoices), currency)}
            detail="Across detected suppliers"
            tone="success"
          />
        </section>

        <ContentCard
          title="Supplier spend"
          subtitle="This becomes the starting point for vendor master matching and duplicate checks."
        >
          {suppliers.length ? (
            <BarList rows={suppliers} currency={currency} emptyLabel="No vendors yet." />
          ) : (
            <EmptyState
              icon={Users}
              title="No vendors yet"
              description="Upload invoices to build the supplier list and matching history."
            />
          )}
        </ContentCard>
      </main>
    </div>
  );
}
