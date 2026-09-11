import Image from "next/image";
import clsx from "clsx";

type BrandMarkSize = "md" | "lg";

const brandSizes: Record<
  BrandMarkSize,
  {
    gap: string;
    mark: string;
    markPixels: number;
    title: string;
    subtitle: string;
  }
> = {
  md: {
    gap: "gap-2",
    mark: "size-11 rounded-xl",
    markPixels: 44,
    title: "text-[16px]",
    subtitle: "mt-1 text-xs",
  },
  lg: {
    gap: "gap-3.5",
    mark: "size-16 rounded-2xl sm:size-[72px]",
    markPixels: 72,
    title: "text-[28px] sm:text-[32px]",
    subtitle: "mt-2 text-[15px] sm:text-[16px]",
  },
};

export function BrandMark({
  compact = false,
  size = "md",
  className,
}: {
  compact?: boolean;
  size?: BrandMarkSize;
  className?: string;
}) {
  const styles = brandSizes[size];

  return (
    <div className={clsx("flex min-w-0 items-center", styles.gap, className)}>
      <Image
        alt={compact ? "SiftEntry" : ""}
        aria-hidden={compact ? undefined : "true"}
        className={clsx("shrink-0", styles.mark)}
        height={styles.markPixels}
        src="/brand/siftentry-mark-tight.svg"
        width={styles.markPixels}
      />
      {!compact && (
        <span className="flex min-w-0 flex-col justify-center">
          <span
            className={clsx(
              "block truncate font-semibold leading-none text-ink",
              styles.title,
            )}
          >
            Sift
            <span className="text-accent-ink">Entry</span>
          </span>
          <span
            className={clsx(
              "block truncate font-medium leading-none text-ink-muted",
              styles.subtitle,
            )}
          >
            Invoices in. Entries ready.
          </span>
        </span>
      )}
    </div>
  );
}
