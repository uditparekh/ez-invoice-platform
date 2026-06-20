import { FileClock } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function HistoryPage() {
  return (
    <PlaceholderPage
      eyebrow="Audit trail"
      title="Invoice history"
      description="Review extraction, validation, approval, posting, and correction activity across the organization."
      icon={FileClock}
    />
  );
}
