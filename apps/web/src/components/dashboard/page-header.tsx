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
    <section className="border-b border-line bg-canvas px-4 py-5 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4">
        <div className="min-w-0 flex-[1_1_24rem] [overflow-wrap:anywhere]">
          <h1 className="flex min-w-0 flex-wrap items-baseline text-2xl font-semibold leading-tight text-ink">
            <span>{title}</span>
            {section && (
              <>
                <span className="mx-2 text-base text-ink-muted">/</span>
                <span className="text-base font-medium text-ink-secondary">
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
        {action && (
          <div className="min-w-0 max-w-full flex-[0_1_auto]">{action}</div>
        )}
      </div>
    </section>
  );
}
