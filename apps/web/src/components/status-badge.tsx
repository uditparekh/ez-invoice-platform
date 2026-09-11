import type { InvoiceStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const labels: Record<InvoiceStatus, string> = {
  uploaded: "Uploaded",
  extracted: "Extracted",
  needs_review: "Needs review",
  validated: "Validated",
  approved: "Approved",
  posting: "Posting",
  posted: "Posted",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  const warning = status === "needs_review" || status === "posting";
  const danger = status === "failed";
  const posted = status === "posted";
  const ready = status === "validated" || status === "approved";
  return (
    <span
      className={cn(
        "inline-flex min-h-7 shrink-0 items-center whitespace-nowrap rounded-md px-2.5 text-xs font-medium",
        danger
          ? "bg-danger-soft text-danger"
          : warning
            ? "bg-gold-soft text-gold"
            : posted
              ? "bg-success-soft text-success"
              : ready
                ? "bg-success-soft text-success"
                : "bg-accent-soft text-accent-ink",
      )}
    >
      {labels[status]}
    </span>
  );
}
