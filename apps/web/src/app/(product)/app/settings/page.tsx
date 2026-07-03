"use client";

import {
  Bell,
  Building2,
  Database,
  KeyRound,
  Moon,
  Palette,
  Sun,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { PageHeader } from "@/components/dashboard/page-header";
import { PasswordChangeCard } from "@/components/settings/password-change-card";
import { TeamManagementPanel } from "@/components/settings/team-management-panel";
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

  return (
    <div className="min-h-[calc(100vh-68px)] bg-canvas">
      <PageHeader
        title="Settings"
        section="Workspace & account"
        description="Workspace-wide defaults and your personal preferences. Client accounting logic lives in Client profiles."
      />
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          {/* two-group rail */}
          <nav className="lg:sticky lg:top-24 lg:self-start">
            <div className="flex gap-1 overflow-x-auto lg:flex-col lg:gap-0">
              {(["WORKSPACE", "MY ACCOUNT"] as const).map((group) => (
                <div key={group} className="flex gap-1 lg:block">
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
                          "flex w-full shrink-0 items-center gap-2.5 whitespace-nowrap rounded-xl px-3 py-2.5 text-sm font-bold transition-colors",
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
            {section === "organization" && <OrganizationPane />}
            {section === "team" && <TeamManagementPanel />}
            {section === "retention" && <RetentionPane />}
            {section === "profile" && <ProfilePane />}
            {section === "security" && <PasswordChangeCard />}
            {section === "notifications" && <NotificationsPane />}
            {section === "appearance" && <AppearancePane />}
          </div>
        </div>
      </main>
    </div>
  );
}

/* ================= workspace panes ================= */

function OrganizationPane() {
  const { user, activeOrganizationId } = useAuth();
  const membership =
    user?.memberships.find(
      (candidate) => candidate.organization_id === activeOrganizationId,
    ) ?? user?.memberships[0];
  const orgName = membership?.organization_name ?? "Your workspace";
  const [prefs, setPrefs] = usePrefs("siftentry.org.defaults", {
    currency: "USD",
    country: "auto",
    system: "tally",
  });

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
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Default currency">
          <Select
            value={prefs.currency}
            onChange={(currency) => setPrefs({ ...prefs, currency })}
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
            value={prefs.country}
            onChange={(country) => setPrefs({ ...prefs, country })}
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
          value={prefs.system}
          onChange={(system) => setPrefs({ ...prefs, system })}
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
      <SyncNote />
    </Pane>
  );
}

function RetentionPane() {
  const [policy, setPolicy] = usePrefs("siftentry.org.retention", {
    mode: "review_window",
  });
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
            onClick={() => setPolicy({ mode: value })}
            className={cn(
              "w-full rounded-2xl border bg-surface p-4 text-left transition-all",
              policy.mode === value
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
      <SyncNote />
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

function NotificationsPane() {
  const [prefs, setPrefs] = usePrefs("siftentry.notifications", {
    approvals: true,
    failures: true,
    digest: false,
  });
  const rows: [keyof typeof prefs, string, string][] = [
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
              checked={prefs[key]}
              onChange={(event) =>
                setPrefs({ ...prefs, [key]: event.target.checked })
              }
              className="mt-1 size-5 shrink-0 accent-[var(--accent)]"
            />
          </label>
        ))}
      </div>
      <SyncNote />
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

function usePrefs<T extends Record<string, unknown>>(
  key: string,
  initial: T,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return initial;
    try {
      const stored = JSON.parse(window.localStorage.getItem(key) || "null");
      if (stored && typeof stored === "object")
        return { ...initial, ...stored };
    } catch {
      /* defaults */
    }
    return initial;
  });
  function update(next: T) {
    setValue(next);
    window.localStorage.setItem(key, JSON.stringify(next));
  }
  return [value, update];
}

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

function SyncNote() {
  return (
    <p className="text-xs font-semibold text-ink-muted">
      Saved as a workspace preference on this device — syncs to the backend when
      the organization-settings API lands.
    </p>
  );
}
