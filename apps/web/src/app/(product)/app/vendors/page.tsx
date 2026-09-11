"use client";

import { BrainCircuit, Sparkles, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { BarList } from "@/components/dashboard/bar-list";
import { ContentCard } from "@/components/dashboard/content-card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { groupSupplier, invoiceTotal } from "@/lib/invoice-metrics";
import type { CorrectionLearningSignal } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

export default function VendorsPage() {
  const { activeOrganizationId } = useAuth();
  const { invoices } = useWorkspaceInvoices();
  const suppliers = groupSupplier(invoices);
  const currency = invoices[0]?.currency || "USD";
  const [learningSignals, setLearningSignals] = useState<
    CorrectionLearningSignal[]
  >([]);

  useEffect(() => {
    if (!activeOrganizationId) return;
    let mounted = true;
    fetch(
      `/api/organizations/${activeOrganizationId}/corrections/learning?limit=25`,
    )
      .then((response) => (response.ok ? response.json() : []))
      .then((payload: CorrectionLearningSignal[]) => {
        if (mounted) setLearningSignals(payload);
      })
      .catch(() => {
        if (mounted) setLearningSignals([]);
      });
    return () => {
      mounted = false;
    };
  }, [activeOrganizationId]);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Vendors"
        section="Supplier intelligence"
        description="Track supplier matching, spend concentration, and master-data readiness before posting."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
          <MetricCard
            label="Learned corrections"
            value={learningSignals.length}
            detail="Saved field fixes from review"
            tone="accent"
            icon={<BrainCircuit size={18} />}
          />
        </section>

        <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
          <ContentCard
            title="Supplier spend"
            subtitle="This becomes the starting point for vendor master matching and duplicate checks."
          >
            {suppliers.length ? (
              <BarList
                rows={suppliers}
                currency={currency}
                emptyLabel="No vendors yet."
              />
            ) : (
              <EmptyState
                icon={Users}
                title="No vendors yet"
                description="Upload invoices to build the supplier list and matching history."
              />
            )}
          </ContentCard>

          <ContentCard
            title="Correction learning"
            subtitle="Every reviewed field correction becomes training signal for parser and vendor-specific rules."
          >
            {learningSignals.length ? (
              <div className="space-y-3">
                {learningSignals.map((signal) => (
                  <CorrectionRow key={signal.id} signal={signal} />
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Sparkles}
                title="No corrections learned yet"
                description="Field edits made during invoice review will appear here as parser learning signals."
              />
            )}
          </ContentCard>
        </section>
      </main>
    </div>
  );
}

function CorrectionRow({ signal }: { signal: CorrectionLearningSignal }) {
  return (
    <article className="rounded-2xl border border-line bg-canvas p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">
            {signal.supplier_name}
          </p>
          <p className="mt-1 text-xs font-semibold text-ink-secondary">
            {signal.invoice_number} · {signal.field_path}
          </p>
        </div>
        <span className="inline-flex w-fit rounded-full border border-accent/25 bg-accent-soft px-3 py-1 text-xs font-semibold uppercase text-accent-ink">
          Learned
        </span>
      </div>
      <div className="mt-3 grid gap-2 rounded-xl border border-line bg-surface-subtle p-3 text-xs font-semibold text-ink-secondary md:grid-cols-2">
        <ValueBlock label="Before" value={signal.old_value} />
        <ValueBlock label="After" value={signal.new_value} strong />
      </div>
      {signal.actor_email && (
        <p className="mt-3 text-xs font-semibold text-ink-muted">
          Updated by {signal.actor_email}
        </p>
      )}
    </article>
  );
}

function ValueBlock({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: unknown;
  strong?: boolean;
}) {
  const rendered =
    typeof value === "string"
      ? value
      : value === null || value === undefined
        ? "Empty"
        : JSON.stringify(value);
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase text-ink-muted">{label}</p>
      <p
        className={`mt-1 truncate ${strong ? "font-semibold text-ink" : "text-ink-secondary"}`}
      >
        {rendered}
      </p>
    </div>
  );
}
