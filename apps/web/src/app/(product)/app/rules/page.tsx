import { ShieldCheck } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function RulesPage() {
  return (
    <PlaceholderPage
      eyebrow="Automation"
      title="Approval and posting rules"
      description="Define validation thresholds, approval routing, duplicate controls, and accounting recommendations."
      icon={ShieldCheck}
    />
  );
}
