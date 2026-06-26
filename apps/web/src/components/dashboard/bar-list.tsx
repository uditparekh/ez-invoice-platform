import { formatCurrency } from "@/lib/utils";

export function BarList({
  rows,
  currency = "USD",
  emptyLabel,
}: {
  rows: { label: string; total: number; count?: number }[];
  currency?: string;
  emptyLabel: string;
}) {
  const max = Math.max(...rows.map((row) => row.total), 1);

  if (!rows.length) {
    return <p className="text-sm font-semibold text-ink-muted">{emptyLabel}</p>;
  }

  return (
    <div className="space-y-4">
      {rows.slice(0, 6).map((row) => (
        <div key={row.label}>
          <div className="flex items-center justify-between gap-4">
            <p className="truncate text-sm font-bold text-ink-secondary">
              {row.label}
            </p>
            <p className="shrink-0 font-mono text-sm font-black text-ink">
              {formatCurrency(row.total, currency)}
            </p>
          </div>
          <div className="mt-2 h-2 rounded-full bg-surface-strong">
            <div
              className="h-full rounded-full bg-accent dark:bg-cyan"
              style={{ width: `${Math.max(8, (row.total / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
