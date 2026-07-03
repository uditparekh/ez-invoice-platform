import type { ReactNode } from "react";

export function ContentCard({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-line bg-surface shadow-card ${className}`}>
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-black text-ink">{title}</h2>
          {subtitle && (
            <p className="mt-1 text-sm leading-5 text-ink-secondary">
              {subtitle}
            </p>
          )}
        </div>
        {action && <div className="w-full xl:w-auto xl:shrink-0">{action}</div>}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}
