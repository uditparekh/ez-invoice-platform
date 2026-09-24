"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth-provider";
import type { ReportRange, WorkspaceAnalytics } from "@/lib/reporting";

export function DemoReportNotice({
  data,
  onShowSamples,
}: {
  data?: WorkspaceAnalytics;
  onShowSamples?: (range: ReportRange) => void;
}) {
  const { user } = useAuth();
  if (user?.email.toLowerCase() !== "demo@siftentry.com") return null;
  const range = data?.available_range;
  return (
    <aside
      aria-label="About demo reports"
      className="rounded-xl border border-line bg-surface-subtle p-4 text-sm"
    >
      <h2 className="font-semibold text-ink">
        Read-only demo · sample data
      </h2>
      <p className="mt-2 leading-6 text-ink-secondary">
        Posted is illustrative, not a live accounting transaction. Reports use
        the samples’ original receipt dates, so the current month can show zero.
      </p>
      {range && (
        <p className="mt-2 text-ink-secondary">
          Sample receipt dates: {range.start} — {range.end} (UTC).
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {range && onShowSamples && (
          <button
            type="button"
            onClick={() => onShowSamples(range)}
            className="min-h-11 text-left font-medium text-accent-ink"
          >
            Show sample period
          </button>
        )}
        <Link
          href="/app/invoices"
          className="inline-flex min-h-11 items-center font-medium text-accent-ink"
        >
          Browse sample invoices
        </Link>
      </div>
    </aside>
  );
}
