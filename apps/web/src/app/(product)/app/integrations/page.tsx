import { Plug } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function IntegrationsPage() {
  return (
    <PlaceholderPage
      eyebrow="Accounting systems"
      title="Integrations"
      description="Manage secure connections to QuickBooks Online, TallyPrime, Zoho Books, and future ERP adapters."
      icon={Plug}
    />
  );
}
