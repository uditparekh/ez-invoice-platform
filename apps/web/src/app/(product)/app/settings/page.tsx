import { Settings2 } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export default function SettingsPage() {
  return (
    <PlaceholderPage
      eyebrow="Organization"
      title="Workspace settings"
      description="Manage members, roles, legal entities, currencies, security, and organization defaults."
      icon={Settings2}
    />
  );
}
