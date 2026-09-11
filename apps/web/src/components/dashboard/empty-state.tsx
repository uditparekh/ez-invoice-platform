import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="grid min-h-60 place-items-center rounded-2xl border border-dashed border-line-strong bg-surface text-center">
      <div className="px-6">
        <Icon className="mx-auto text-ink-muted" size={28} />
        <p className="mt-4 text-base font-semibold text-ink">{title}</p>
        <p className="mt-2 max-w-md text-sm leading-6 text-ink-secondary">
          {description}
        </p>
      </div>
    </div>
  );
}
