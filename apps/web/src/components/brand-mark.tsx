export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-[8px] bg-accent text-sm font-extrabold text-white dark:text-[#111310]">
        EZ
      </span>
      {!compact && (
        <span className="min-w-0">
          <span className="block truncate text-[15px] font-bold text-ink">
            EZ-Invoice
          </span>
          <span className="mt-0.5 block font-mono text-[11px] font-medium text-ink-muted">
            AP automation
          </span>
        </span>
      )}
    </div>
  );
}
