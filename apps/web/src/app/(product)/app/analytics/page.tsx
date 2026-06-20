import { BarChart3 } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function AnalyticsPage() {
  return (
    <PlaceholderPage
      eyebrow="Operations"
      title="AP analytics"
      description="Track invoice throughput, processing time, exception rates, supplier concentration, and posted spend."
      icon={BarChart3}
    />
  );
}
