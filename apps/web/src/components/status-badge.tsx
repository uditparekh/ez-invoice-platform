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
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-bold",
        danger
          ? "bg-danger-soft text-danger"
          : warning
            ? "bg-gold-soft text-gold"
            : "bg-accent-soft text-accent-ink",
      )}
    >
      {labels[status]}
    </span>
  );
}
