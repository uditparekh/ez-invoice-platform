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
      <QueueMetric label="Extracted" value={counts.extracted} active />
      <QueueMetric label="Validated" value={counts.validated} />
      <QueueMetric label="Sent to ERP" value={counts.sent} tone="posted" />
      <QueueMetric label="Exceptions" value={counts.exceptions} tone="warning" />
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
        "relative flex min-h-24 items-center gap-3 border-b border-line px-5 py-4 sm:border-r lg:border-b-0",
        active && "bg-accent-soft",
      )}
    >
      <strong
        className={cn(
          "font-mono text-3xl font-black text-accent",
          tone === "warning" && "text-gold",
          tone === "posted" && "text-cyan",
          active && "text-accent",
        )}
      >
        {value}
      </strong>
      <span className="text-sm font-extrabold text-ink-secondary">{label}</span>
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-accent" />}
    </div>
  );
}
