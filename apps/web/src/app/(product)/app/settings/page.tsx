"use client";

import { Building2, KeyRound, Shield } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { ClientProfilesPanel } from "@/components/client-profiles-panel";
import { ContentCard } from "@/components/dashboard/content-card";
import { MetricCard } from "@/components/dashboard/metric-card";
import { PageHeader } from "@/components/dashboard/page-header";
import { PasswordChangeCard } from "@/components/settings/password-change-card";
import { TeamManagementPanel } from "@/components/settings/team-management-panel";

export default function SettingsPage() {
  const { user, activeOrganizationId } = useAuth();
  const membership =
    user?.memberships.find(
      (candidate) => candidate.organization_id === activeOrganizationId,
    ) ?? user?.memberships[0];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-canvas">
      <PageHeader
        title="Workspace"
        section="Settings"
        description="Manage the organization defaults that every invoice, connector, mapping, and user permission depends on."
      />
      <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard
            label="Organization"
            value={membership?.organization_name ?? "Workspace"}
            detail={membership?.role ?? "Member"}
            icon={<Building2 size={18} />}
          />
          <MetricCard
            label="Members"
            value={user?.memberships.length ?? 0}
            detail="Accessible organizations for this user"
            tone="accent"
            icon={<Shield size={18} />}
          />
          <MetricCard
            label="Security"
            value="JWT"
            detail="API-backed authenticated sessions"
            tone="success"
            icon={<KeyRound size={18} />}
          />
        </section>

        <ContentCard
          title="Workspace profile"
          subtitle="These defaults frame client-specific posting, tax, parser, and audit behavior."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <SettingRow label="Primary organization" value={membership?.organization_name ?? "Not selected"} />
            <SettingRow label="Current role" value={membership?.role ?? "member"} />
            <SettingRow label="User email" value={user?.email ?? "Not signed in"} />
            <SettingRow label="Default parser" value="Auto-detect invoice format" />
            <SettingRow label="Default currency" value="Client workspace default" />
            <SettingRow label="Evidence retention" value="PDF + JSON + posting response" />
          </div>
        </ContentCard>

        <TeamManagementPanel />

        <PasswordChangeCard />

        <ClientProfilesPanel />
      </main>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-canvas px-4 py-3">
      <p className="text-[11px] font-extrabold uppercase text-ink-muted">
        {label}
      </p>
      <p className="mt-2 break-words text-sm font-black capitalize text-ink">
        {value}
      </p>
    </div>
  );
}
