import type { ReactNode } from "react";

export function PageHeader({
  title,
  section,
  description,
  action,
}: {
  title: string;
  section?: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <section className="border-b border-line bg-canvas px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h1 className="flex min-w-0 flex-wrap items-baseline gap-x-1 text-3xl font-black leading-tight text-ink">
            <span>{title}</span>
            {section && (
              <>
                <span className="text-ink-secondary">/</span>
                <span className="text-2xl font-extrabold text-ink-secondary">
                  {section}
                </span>
              </>
            )}
          </h1>
          {description && (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-secondary">
              {description}
            </p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </section>
  );
}
