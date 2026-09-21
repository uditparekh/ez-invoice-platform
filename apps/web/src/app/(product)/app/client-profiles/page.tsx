"use client";

import { ClientProfilesPanel } from "@/components/client-profiles-panel";
import { PageHeader } from "@/components/dashboard/page-header";
import { FormatRegistry } from "@/components/training/format-registry";

/** One shared editor for the main profile page and accounting integration pages. */
export default function ClientProfilesPage() {
  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Client profiles"
        section="Workspace setup"
        description="Company, connection, accounting rules and invoice guidance — one clear setup for each client."
      />
      <main className="space-y-6 p-3 sm:p-6 lg:p-8">
        <ClientProfilesPanel subtitle="Work through the five sections. Save configuration separately from activation; every invoice still needs approval." />
        <FormatRegistry />
      </main>
    </div>
  );
}
