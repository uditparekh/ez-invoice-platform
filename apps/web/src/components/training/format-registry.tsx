"use client";

import { ArrowRight, GraduationCap, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

import {
  useSupplierFormats,
  type SupplierFormat,
} from "@/hooks/use-supplier-formats";
import { cn } from "@/lib/utils";

/** Training mode — UI for the supplier format registry (Phase B).
 *  Every supplier format starts in Training; five consecutive approvals
 *  with zero corrections graduate it to Trusted. Reviewing invoices IS
 *  the training — the "Train" actions route into the queue. */
export function FormatRegistry() {
  const { loading, trustedAfter, formats, untrained } = useSupplierFormats();

  if (loading || (!formats.length && !untrained.length)) return null;

  const trusted = formats.filter((format) => format.status === "trusted");

  return (
    <section className="mt-8">
      {/* Training hero — same visual family as the Sift hero */}
      <div className="flex flex-col gap-4 rounded-2xl bg-gradient-to-r from-[var(--hero-from)] via-[var(--hero-via)] to-[var(--hero-to)] px-6 py-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-200/80">
            Training mode
          </p>
          <p className="mt-1 text-lg font-semibold leading-snug text-white sm:text-xl">
            {trusted.length} trusted format{trusted.length === 1 ? "" : "s"} ·{" "}
            {formats.length - trusted.length + untrained.length} in training —
            every clean approval teaches SiftEntry.
          </p>
        </div>
        <Link
          href="/app/invoices"
          className="inline-flex h-12 shrink-0 items-center gap-2 self-start rounded-xl bg-white px-5 text-sm font-semibold text-[var(--hero-via)] shadow-sm sm:self-auto"
        >
          <GraduationCap size={17} />
          Train formats
          <ArrowRight size={15} />
        </Link>
      </div>

      {/* New formats detected */}
      {untrained.length > 0 && (
        <div className="mt-4 rounded-2xl border border-dashed border-accent/50 bg-accent-soft/60 px-5 py-4">
          <p className="text-sm font-semibold text-accent-ink">
            <Sparkles size={15} className="mr-1.5 inline" />
            New format{untrained.length === 1 ? "" : "s"} detected
          </p>
          <p className="mt-1 text-xs font-semibold leading-5 text-accent-ink/80">
            {untrained
              .slice(0, 3)
              .map(
                (supplier) =>
                  `${supplier.supplier_name} (${supplier.invoice_count} invoice${supplier.invoice_count === 1 ? "" : "s"})`,
              )
              .join(" · ")}
            {untrained.length > 3 ? ` · +${untrained.length - 3} more` : ""} —
            review and approve their invoices to start training.
          </p>
        </div>
      )}

      {/* Format collection */}
      {formats.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface">
          {formats.map((format) => (
            <FormatRow
              key={format.supplier_key}
              format={format}
              trustedAfter={trustedAfter}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function FormatRow({
  format,
  trustedAfter,
}: {
  format: SupplierFormat;
  trustedAfter: number;
}) {
  const isTrusted = format.status === "trusted";
  const progress = Math.min(format.clean_streak, trustedAfter);

  return (
    <div className="flex flex-col gap-2 border-b border-line px-4 py-3.5 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-ink">
          {format.supplier_name}
        </p>
        <p className="text-xs font-semibold text-ink-secondary">
          {format.samples_count} invoice{format.samples_count === 1 ? "" : "s"}{" "}
          reviewed
          {format.supplier_tax_id ? ` · ${format.supplier_tax_id}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {!isTrusted && (
          <span className="flex items-center gap-1.5" aria-hidden>
            {Array.from({ length: trustedAfter }).map((_, index) => (
              <span
                key={index}
                className={cn(
                  "h-1.5 w-5 rounded-full",
                  index < progress ? "bg-accent" : "bg-line",
                )}
              />
            ))}
          </span>
        )}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
            isTrusted
              ? "bg-success-soft text-success"
              : "bg-gold-soft text-gold-ink",
          )}
        >
          {isTrusted ? <ShieldCheck size={12} /> : <GraduationCap size={12} />}
          {isTrusted ? "Trusted" : `Training ${progress}/${trustedAfter}`}
        </span>
      </div>
    </div>
  );
}
