import type { LucideIcon } from "lucide-react";

export function PlaceholderPage({
  eyebrow,
  title,
  description,
  icon: Icon,
}: {
  eyebrow: string;
  title: string;
  description: string;
  icon: LucideIcon;
}) {
  return (
    <section className="min-h-[calc(100vh-64px)] bg-canvas px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1180px]">
        <p className="text-xs font-extrabold uppercase text-accent">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-bold text-ink">{title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-secondary">
          {description}
        </p>
        <div className="mt-10 grid min-h-80 place-items-center border-y border-line bg-surface px-6 text-center">
          <div>
            <Icon size={28} className="mx-auto text-accent" />
            <p className="mt-4 text-sm font-bold text-ink">Foundation ready</p>
            <p className="mt-2 max-w-md text-sm leading-6 text-ink-muted">
              This route is wired into the shared application shell and is
              ready for its workflow module in the next milestone.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
