"use client";

import {
  BarChart3,
  Building2,
  CircleAlert,
  Database,
  Diamond,
  FileClock,
  FileCog,
  FileSpreadsheet,
  FileText,
  Landmark,
  LogOut,
  Map,
  Menu,
  Network,
  Settings2,
  ShieldCheck,
  Table2,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navGroups = [
  {
    label: "Workflow",
    items: [
      { href: "/app/invoices", label: "Invoices", icon: FileText },
      { href: "/app/history", label: "History", icon: FileClock },
      { href: "/app/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/app/exceptions", label: "Exceptions", icon: CircleAlert },
    ],
  },
  {
    label: "Send to ERP",
    items: [
      {
        href: "/app/accounting/quickbooks",
        label: "QuickBooks",
        icon: Network,
      },
      { href: "/app/accounting/tally", label: "Tally", icon: Table2 },
      {
        href: "/app/accounting/zoho-books",
        label: "Zoho Books",
        icon: FileSpreadsheet,
      },
      { href: "/app/accounting/coupa", label: "Coupa", icon: Database },
      { href: "/app/accounting/netsuite", label: "NetSuite", icon: Landmark },
      { href: "/app/accounting/sap", label: "SAP", icon: FileCog },
    ],
  },
  {
    label: "Settings",
    items: [
      { href: "/app/gl-mapping", label: "GL Mapping", icon: Diamond },
      { href: "/app/rules", label: "Rules", icon: ShieldCheck },
      { href: "/app/vendors", label: "Vendors", icon: Users },
      { href: "/app/roadmap", label: "Roadmap", icon: Map },
      { href: "/app/settings", label: "Workspace", icon: Settings2 },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const {
    user,
    activeOrganizationId,
    loading,
    selectOrganization,
    logout,
  } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const membership =
    user?.memberships.find(
      (candidate) => candidate.organization_id === activeOrganizationId,
    ) ?? user?.memberships[0];

  const nav = (
    <>
      <div className="flex h-16 items-center border-b border-line px-5">
        <BrandMark />
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-6">
        {navGroups.map((group, groupIndex) => (
          <div key={group.label} className={groupIndex ? "mt-8" : ""}>
            <p className="px-3 text-[10px] font-extrabold uppercase text-ink-muted">
              {group.label}
            </p>
            <nav className="mt-3 space-y-1">
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  {...item}
                  active={isActivePath(pathname, item.href)}
                  onNavigate={() => setMobileOpen(false)}
                />
              ))}
            </nav>
          </div>
        ))}
      </div>
      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-subtle px-3 py-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-black text-accent-ink">
            {(user?.full_name || user?.email || "SE")
              .split(/\s|@/)
              .slice(0, 2)
              .map((part) => part[0]?.toUpperCase())
              .join("")}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-bold text-ink">
              {loading ? "Loading account" : user?.full_name || user?.email}
            </span>
            <span className="block truncate text-[11px] capitalize text-ink-muted">
              {membership?.role ?? "workspace member"}
            </span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="size-8 px-0"
            onClick={() => void logout()}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={15} />
          </Button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[260px] flex-col border-r border-line bg-surface lg:flex">
        {nav}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/35"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="relative flex h-full w-[286px] flex-col border-r border-line bg-surface shadow-2xl">
            <Button
              variant="ghost"
              size="sm"
              className="absolute right-3 top-3 z-10 size-9 px-0"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X size={18} />
            </Button>
            {nav}
          </aside>
        </div>
      )}

      <div className="lg:pl-[260px]">
        <header className="sticky top-0 z-30 flex h-16 items-center border-b border-line bg-surface/95 px-4 backdrop-blur sm:px-6 lg:px-8">
          <Button
            variant="ghost"
            size="sm"
            className="mr-3 size-9 px-0 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={18} />
          </Button>
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-ink-secondary">
            <Building2 size={16} className="shrink-0 text-cyan" />
            {user && user.memberships.length > 1 ? (
              <select
                value={membership?.organization_id}
                onChange={(event) => selectOrganization(event.target.value)}
                aria-label="Active organization"
                className="min-w-0 max-w-[240px] bg-transparent font-semibold text-ink outline-none"
              >
                {user.memberships.map((candidate) => (
                  <option
                    key={candidate.organization_id}
                    value={candidate.organization_id}
                  >
                    {candidate.organization_name}
                  </option>
                ))}
              </select>
            ) : (
              <span className="truncate">
                {membership?.organization_name ?? "Client Workspace"}
              </span>
            )}
            <span className="hidden text-ink-muted sm:inline">/</span>
            <span className="hidden capitalize text-ink-muted sm:inline">
              {membership?.role ?? "member"}
            </span>
          </div>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        "flex h-11 items-center gap-3 rounded-xl border-l-[3px] px-3 text-sm font-bold transition-colors",
        active
          ? "border-accent bg-accent-soft text-accent-ink dark:border-cyan dark:bg-surface-strong dark:text-cyan"
          : "border-transparent text-ink-secondary hover:bg-surface-subtle hover:text-ink",
      )}
    >
      <Icon size={17} strokeWidth={1.8} />
      {label}
    </Link>
  );
}

function isActivePath(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
