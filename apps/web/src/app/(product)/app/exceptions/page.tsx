import { CircleAlert } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function ExceptionsPage() {
  return (
    <PlaceholderPage
      eyebrow="Review queue"
      title="Exceptions"
      description="Resolve missing fields, unmatched suppliers, totals, tax issues, and accounting mapping blockers."
      icon={CircleAlert}
    />
  );
}
