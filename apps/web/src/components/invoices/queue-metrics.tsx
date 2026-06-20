import { cn } from "@/lib/utils";

export interface QueueCounts {
  total: number;
  review: number;
  ready: number;
  posted: number;
}

export function QueueMetrics({ counts }: { counts: QueueCounts }) {
  return (
    <section className="grid grid-cols-2 border-b border-line bg-surface xl:grid-cols-4">
      <QueueMetric label="In queue" value={counts.total} />
      <QueueMetric label="Needs review" value={counts.review} tone="warning" />
      <QueueMetric label="Ready for ERP" value={counts.ready} active />
      <QueueMetric label="Posted" value={counts.posted} />
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
  tone?: "default" | "warning";
}) {
  return (
    <div
      className={cn(
        "relative flex min-h-20 items-center gap-3 border-b border-line px-5 py-4 sm:border-r xl:border-b-0",
        active && "bg-accent-soft",
      )}
    >
      <strong
        className={cn(
          "font-mono text-2xl text-accent",
          tone === "warning" && "text-gold",
        )}
      >
        {value}
      </strong>
      <span className="text-sm font-semibold text-ink-secondary">{label}</span>
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-accent" />}
    </div>
  );
}
