import { cn } from "@/lib/utils";

export interface QueueCounts {
  uploaded: number;
  extracted: number;
  validated: number;
  sent: number;
  exceptions: number;
}

export function QueueMetrics({ counts }: { counts: QueueCounts }) {
  return (
    <section className="grid grid-cols-2 border-b border-line bg-surface lg:grid-cols-5">
      <QueueMetric label="Uploaded" value={counts.uploaded} />
      <QueueMetric label="Auto-extracted" value={counts.extracted} active />
      <QueueMetric label="Validated" value={counts.validated} />
      <QueueMetric label="Posted" value={counts.sent} tone="posted" />
      <QueueMetric
        label="Exceptions"
        value={counts.exceptions}
        tone="warning"
      />
    </section>
  );
}

function QueueMetric({
  label,
  value,
  active = false,
  tone = "default",
}: {
  label: string;
  value: number;
  active?: boolean;
  tone?: "default" | "warning" | "posted";
}) {
  return (
    <div
      className={cn(
        "relative flex min-h-[72px] items-center gap-3 border-b border-line px-4 py-3 last:col-span-2 sm:border-r lg:last:col-span-1 lg:border-b-0",
      )}
    >
      <strong
        className={cn(
          "text-2xl font-semibold leading-none text-ink tabular-nums",
          tone === "warning" && "text-gold",
          tone === "posted" && "text-success",
          active && "text-accent-ink",
        )}
      >
        {value}
      </strong>
      <span className="min-w-0 text-sm font-semibold leading-5 text-ink-secondary">
        {label}
      </span>
    </div>
  );
}
