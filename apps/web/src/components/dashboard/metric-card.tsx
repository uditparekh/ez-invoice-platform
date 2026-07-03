import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  detail,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "default" | "accent" | "success" | "warning" | "danger";
  icon?: ReactNode;
}) {
  return (
    <article className="min-h-36 rounded-2xl border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-extrabold uppercase text-ink-muted">
          {label}
        </p>
        {icon && <div className="text-ink-muted">{icon}</div>}
      </div>
      <div
        className={cn(
          "mt-5 truncate font-mono text-[clamp(1.9rem,2.9vw,2.5rem)] font-black leading-none text-ink",
          tone === "accent" && "text-accent dark:text-cyan",
          tone === "success" && "text-success",
          tone === "warning" && "text-gold",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </div>
      {detail && (
        <div className="mt-3 text-sm font-semibold text-ink-secondary">
          {detail}
        </div>
      )}
    </article>
  );
}
