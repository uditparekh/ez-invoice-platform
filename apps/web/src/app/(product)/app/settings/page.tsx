"use client";

import {
  Bell,
  Building2,
  Database,
  KeyRound,
  Moon,
  Palette,
  Plus,
  Sun,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { CreateWorkspaceDialog } from "@/components/create-workspace-dialog";
import { PageHeader } from "@/components/dashboard/page-header";
import { PasswordChangeCard } from "@/components/settings/password-change-card";
import { TeamManagementPanel } from "@/components/settings/team-management-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Settings — UI Spec §14. Linear-style two-group rail:
 *  WORKSPACE (Organization · Team access · Data retention)
 *  MY ACCOUNT (Profile · Security · Notifications · Appearance)
 *  Client-specific accounting logic lives in Client profiles — by design. */

type Section =
  | "organization"
  | "team"
  | "retention"
  | "profile"
  | "security"
  | "notifications"
  | "appearance";

const sections: {
  group: "WORKSPACE" | "MY ACCOUNT";
  id: Section;
  label: string;
  icon: ReactNode;
}[] = [
  { group: "WORKSPACE", id: "organization", label: "Organization", icon: <Building2 size={15} /> },
  { group: "WORKSPACE", id: "team", label: "Team access", icon: <UsersRound size={15} /> },
  { group: "WORKSPACE", id: "retention", label: "Data retention", icon: <Database size={15} /> },
  { group: "MY ACCOUNT", id: "profile", label: "Profile", icon: <UserRound size={15} /> },
  { group: "MY ACCOUNT", id: "security", label: "Security", icon: <KeyRound size={15} /> },
  { group: "MY ACCOUNT", id: "notifications", label: "Notifications", icon: <Bell size={15} /> },
  { group: "MY ACCOUNT", id: "appearance", label: "Appearance", icon: <Palette size={15} /> },
];

export default function SettingsPage() {
  const [section, setSection] = useState<Section>("organization");
  const org = useOrgSettings();

  return (
    <div className="min-h-[calc(100vh-68px)] min-w-0 overflow-x-hidden bg-canvas">
      <PageHeader
        title="Settings"
        section="Workspace & account"
        description="Workspace-wide defaults and your personal preferences. Client accounting logic lives in Client profiles."
      />
      <main className="mx-auto w-full max-w-[1440px] min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <div className="grid min-w-0 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          {/* two-group rail */}
          <nav className="min-w-0 lg:sticky lg:top-24 lg:self-start">
            <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3 lg:flex lg:flex-col lg:gap-0">
              {(["WORKSPACE", "MY ACCOUNT"] as const).map((group) => (
                <div key={group} className="contents lg:block">
                  <p className="hidden px-3 pb-2 pt-4 text-[10px] font-extrabold uppercase tracking-[0.14em] text-ink-muted first:pt-0 lg:block">
                    {group}
                  </p>
                  {sections
                    .filter((item) => item.group === group)
                    .map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setSection(item.id)}
                        className={cn(
                          "flex min-h-11 w-full min-w-0 items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-xs font-bold leading-4 transition-colors sm:text-sm lg:min-h-0 lg:whitespace-nowrap",
                          section === item.id
                            ? "bg-accent-soft text-accent-ink"
                            : "text-ink-secondary hover:bg-surface-strong hover:text-ink",
                        )}
                      >
                        {item.icon}
                        {item.label}
                      </button>
                    ))}
                </div>
              ))}
            </div>
          </nav>

          {/* pane */}
          <div className="min-w-0 space-y-4">
            {section === "organization" && <OrganizationPane org={org} />}
            {section === "team" && <TeamManagementPanel />}
            {section === "retention" && <RetentionPane org={org} />}
            {section === "profile" && <ProfilePane />}
            {section === "security" && <PasswordChangeCard />}
            {section === "notifications" && <NotificationsPane org={org} />}
            {section === "appearance" && <AppearancePane />}
          </div>
        </div>
      </main>
    </div>
  );
}

/* ================= org settings (live API) ================= */

type OrgSettings = {
  default_currency: string;
  default_country: string;
  primary_accounting_system: string;
  data_retention: string;
  notifications: Record<string, boolean>;
};

type OrgSettingsState = {
  settings: OrgSettings | null;
  status: "loading" | "ready" | "saving" | "saved" | "error";
  error: string;
  save: (next: OrgSettings) => void;
};

function useOrgSettings(): OrgSettingsState {
  const { activeOrganizationId } = useAuth();
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [status, setStatus] =
    useState<OrgSettingsState["status"]>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!activeOrganizationId) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(
          `/api/organizations/${activeOrganizationId}/settings`,
        );
        if (!response.ok) throw new Error("Could not load workspace settings.");
        const payload = (await response.json()) as OrgSettings;
        if (!cancelled) {
          setSettings(payload);
          setStatus("ready");
        }
      } catch (loadError) {
        if (!cancelled) {
          setStatus("error");
          setError((loadError as Error).message);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeOrganizationId]);

  function save(next: OrgSettings) {
    const previous = settings;
    setSettings(next); // optimistic
    setStatus("saving");
    setError("");
    void (async () => {
      try {
        const response = await fetch(
          `/api/organizations/${activeOrganizationId}/settings`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(next),
          },
        );
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as {
            detail?: string;
          } | null;
          throw new Error(
            response.status === 403
              ? "Only workspace owners and admins can change these settings."
              : (payload?.detail ?? "Could not save workspace settings."),
          );
        }
        setSettings((await response.json()) as OrgSettings);
        setStatus("saved");
      } catch (saveError) {
        setSettings(previous);
        setStatus("error");
        setError((saveError as Error).message);
      }
    })();
  }

  return { settings, status, error, save };
}

function SyncState({ org }: { org: OrgSettingsState }) {
  if (org.status === "error")
    return (
      <p className="text-xs font-bold text-danger">{org.error}</p>
    );
  return (
    <p className="text-xs font-semibold text-ink-muted">
      {org.status === "saving"
        ? "Saving to workspace…"
        : org.status === "saved"
          ? "✓ Saved — synced to every workspace member."
          : "Synced to the workspace — changes apply to every member."}
    </p>
  );
}

/* ================= workspace panes ================= */

function OrganizationPane({ org }: { org: OrgSettingsState }) {
  const [workspaceDialogOpen, setWorkspaceDialogOpen] = useState(false);
  const { user, activeOrganizationId } = useAuth();
  const membership =
    user?.memberships.find(
      (candidate) => candidate.organization_id === activeOrganizationId,
    ) ?? user?.memberships[0];
  const orgName = membership?.organization_name ?? "Your workspace";
  const settings = org.settings;

  return (
    <Pane
      title="Organization"
      detail="Defaults that frame every invoice, connector, and mapping."
    >
      <Field label="Organization name">
        <p className="flex h-12 items-center rounded-xl border border-line bg-surface-subtle px-4 text-sm font-black text-ink">
          {orgName}
        </p>
        <Hint>Managed by the workspace owner.</Hint>
      </Field>
      <div className="flex flex-col gap-3 rounded-2xl border border-dashed border-line-strong bg-canvas px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-black text-ink">Onboarding another client?</p>
          <p className="mt-1 text-xs font-semibold leading-5 text-ink-secondary">
            Each client gets its own workspace so invoices, profiles, team, and
            the Tally connection never mix.
          </p>
        </div>
        <Button variant="secondary" onClick={() => setWorkspaceDialogOpen(true)}>
          <Plus size={14} />
          New workspace
        </Button>
      </div>
      <CreateWorkspaceDialog
        open={workspaceDialogOpen}
        onClose={() => setWorkspaceDialogOpen(false)}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Default currency">
          <Select
            value={settings?.default_currency ?? "USD"}
            onChange={(currency) =>
              settings && org.save({ ...settings, default_currency: currency })
            }
            options={[
              ["INR", "INR ₹ — Indian Rupee"],
              ["USD", "USD $ — US Dollar"],
              ["EUR", "EUR € — Euro"],
              ["GBP", "GBP £ — Pound"],
              ["AED", "AED — UAE Dirham"],
            ]}
          />
        </Field>
        <Field label="Default country / tax">
          <Select
            value={settings?.default_country ?? "auto"}
            onChange={(country) =>
              settings && org.save({ ...settings, default_country: country })
            }
            options={[
              ["auto", "Auto-detect from invoice"],
              ["IN", "India · GST"],
              ["US", "United States · sales tax"],
              ["GB", "United Kingdom · VAT"],
            ]}
          />
        </Field>
      </div>
      <Field label="Primary accounting system">
        <Select
          value={settings?.primary_accounting_system ?? "tally"}
          onChange={(system) =>
            settings &&
            org.save({ ...settings, primary_accounting_system: system })
          }
          options={[
            ["tally", "Tally"],
            ["quickbooks", "QuickBooks"],
            ["zoho_books", "Zoho Books"],
          ]}
        />
        <Hint>
          New client profiles pre-select this system. Per-client logic lives in
          Client profiles.
        </Hint>
      </Field>
      <SyncState org={org} />
    </Pane>
  );
}

function RetentionPane({ org }: { org: OrgSettingsState }) {
  const settings = org.settings;
  const mode = settings?.data_retention ?? "review_window";
  const options: [string, string, string][] = [
    [
      "review_window",
      "Delete after review window (default)",
      "Original PDFs are removed 7 days after review completes. Extracted data is kept.",
    ],
    [
      "retain_90",
      "Keep originals 90 days",
      "For clients that need re-audit access — storage add-on.",
    ],
    [
      "no_store",
      "Never store originals",
      "PDFs are processed in-memory and discarded immediately after extraction.",
    ],
  ];
  return (
    <Pane
      title="Data retention"
      detail="What happens to original PDFs — extracted fields and the audit trail are always kept."
    >
      <div className="space-y-2.5">
        {options.map(([value, label, detail]) => (
          <button
            key={value}
            type="button"
            onClick={() =>
              settings && org.save({ ...settings, data_retention: value })
            }
            className={cn(
              "w-full rounded-2xl border bg-surface p-4 text-left transition-all",
              mode === value
                ? "border-accent shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_15%,transparent)]"
                : "border-line hover:border-line-strong",
            )}
          >
            <p className="text-sm font-black text-ink">{label}</p>
            <p className="mt-1 text-sm font-semibold leading-5 text-ink-secondary">
              {detail}
            </p>
          </button>
        ))}
      </div>
      <p className="rounded-xl border border-line bg-surface-subtle px-4 py-3 text-xs font-semibold leading-5 text-ink-secondary">
        Connector and accounting credentials stay profile-owned · invoices and
        profiles are isolated per organization · retention events are logged to
        History.
      </p>
      <SyncState org={org} />
    </Pane>
  );
}

/* ================= account panes ================= */

function ProfilePane() {
  const { user } = useAuth();
  const name = user?.full_name || user?.email || "Your name";
  const email = user?.email || "";
  return (
    <Pane title="Profile" detail="How you appear in approvals and the audit trail.">
      <div className="flex items-center gap-4">
        <span className="grid size-14 place-items-center rounded-2xl bg-accent-soft font-display text-lg font-black text-accent-ink">
          {name
            .split(/\s+/)
            .slice(0, 2)
            .map((word: string) => word[0])
            .join("")
            .toUpperCase()}
        </span>
        <div>
          <p className="text-base font-black text-ink">{name}</p>
          <p className="text-sm font-semibold text-ink-secondary">{email}</p>
        </div>
      </div>
      <Hint>
        Name and email come from your account — every approval and correction in
        History is attributed to this identity.
      </Hint>
    </Pane>
  );
}

function NotificationsPane({ org }: { org: OrgSettingsState }) {
  const settings = org.settings;
  const prefs = settings?.notifications ?? {
    approvals: true,
    failures: true,
    digest: false,
  };
  const rows: [string, string, string][] = [
    ["approvals", "Approval requests", "When an invoice is routed to you by an approval rule."],
    ["failures", "Posting failures", "When a posting attempt fails and needs a retry or mapping fix."],
    ["digest", "Weekly digest", "Your week: posted count, value processed, what needs you Monday."],
  ];
  return (
    <Pane title="Notifications" detail="What SiftEntry emails you about.">
      <div className="space-y-2.5">
        {rows.map(([key, label, detail]) => (
          <label
            key={key}
            className="flex cursor-pointer items-start justify-between gap-4 rounded-2xl border border-line bg-surface p-4"
          >
            <span>
              <span className="block text-sm font-black text-ink">{label}</span>
              <span className="mt-0.5 block text-sm font-semibold text-ink-secondary">
                {detail}
              </span>
            </span>
            <input
              type="checkbox"
              checked={prefs[key] ?? false}
              onChange={(event) =>
                settings &&
                org.save({
                  ...settings,
                  notifications: { ...prefs, [key]: event.target.checked },
                })
              }
              className="mt-1 size-5 shrink-0 accent-[var(--accent)]"
            />
          </label>
        ))}
      </div>
      <SyncState org={org} />
    </Pane>
  );
}

function AppearancePane() {
  const [theme, setThemeState] = useState<"light" | "dark" | "system">(() => {
    if (typeof window === "undefined") return "light";
    const saved = window.localStorage.getItem("siftentry-theme");
    return saved === "dark" || saved === "light" ? saved : "system";
  });

  function apply(next: "light" | "dark" | "system") {
    setThemeState(next);
    const dark =
      next === "dark" ||
      (next === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    if (next === "system") window.localStorage.removeItem("siftentry-theme");
    else window.localStorage.setItem("siftentry-theme", next);
  }

  return (
    <Pane title="Appearance" detail="Light, dark, or follow your device.">
      <div className="grid gap-3 sm:grid-cols-3">
        {(
          [
            ["light", "Light", <Sun key="l" size={18} />],
            ["dark", "Dark", <Moon key="d" size={18} />],
            ["system", "System", <Palette key="s" size={18} />],
          ] as const
        ).map(([value, label, icon]) => (
          <button
            key={value}
            type="button"
            onClick={() => apply(value)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-2xl border bg-surface py-6 transition-all",
              theme === value
                ? "border-accent shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_15%,transparent)]"
                : "border-line hover:border-line-strong",
            )}
          >
            <span className="text-accent">{icon}</span>
            <span className="text-sm font-black text-ink">{label}</span>
          </button>
        ))}
      </div>
      <Hint>
        Dark mode uses the Elevated Slate palette — three elevation layers, warm
        off-white text.
      </Hint>
    </Pane>
  );
}

/* ================= shared ================= */


function Pane({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-6 shadow-card">
      <h2 className="text-lg font-black text-ink">{title}</h2>
      <p className="mt-1 text-sm font-semibold text-ink-secondary">{detail}</p>
      <div className="mt-5 space-y-4">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </p>
      {children}
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-12 w-full rounded-xl border border-line-strong bg-surface px-3.5 text-sm font-bold text-ink outline-none transition-colors focus:border-accent"
    >
      {options.map(([optionValue, label]) => (
        <option key={optionValue} value={optionValue}>
          {label}
        </option>
      ))}
    </select>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return (
    <p className="mt-2 text-xs font-semibold leading-5 text-ink-muted">
      {children}
    </p>
  );
}
