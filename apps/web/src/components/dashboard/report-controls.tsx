"use client";

import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { currentMonth, type ReportRange } from "@/lib/reporting";

export function ReportControls({
  range,
  onChange,
  onRefresh,
  loading,
  children,
}: {
  range: ReportRange;
  onChange: (range: ReportRange) => void;
  onRefresh: () => void;
  loading: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="report-toolbar">
      <div className="flex min-w-0 flex-wrap items-end gap-3">
        <label className="report-date">
          <span>From</span>
          <input
            aria-label="From date"
            type="date"
            value={range.start}
            max={range.end}
            onChange={(e) =>
              e.target.value && onChange({ ...range, start: e.target.value })
            }
          />
        </label>
        <label className="report-date">
          <span>Through</span>
          <input
            aria-label="Through date"
            type="date"
            value={range.end}
            min={range.start}
            onChange={(e) =>
              e.target.value && onChange({ ...range, end: e.target.value })
            }
          />
        </label>
        <Button size="sm" onClick={() => onChange(currentMonth())}>
          This month
        </Button>
        <Button
          size="sm"
          onClick={() => {
            const end = new Date();
            const start = new Date(end.getTime() - 89 * 86400000);
            onChange({
              start: start.toISOString().slice(0, 10),
              end: end.toISOString().slice(0, 10),
            });
          }}
        >
          Last 90 days
        </Button>
        <span className="pb-2 text-xs text-ink-secondary">UTC</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {children}
        <Button
          size="sm"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh report"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          <span>Refresh</span>
        </Button>
      </div>
    </div>
  );
}

export function ReportError({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger"
    >
      <p>{message}</p>
      <Button onClick={retry}>Try again</Button>
    </div>
  );
}

export function ReportMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail: string;
}) {
  return (
    <div className="report-metric">
      <p className="text-sm font-medium text-ink-secondary">{label}</p>
      <p className="mt-2 break-words text-3xl font-semibold tracking-tight text-ink tabular-nums">
        {value}
      </p>
      <p className="mt-1 text-xs text-ink-secondary">{detail}</p>
    </div>
  );
}
