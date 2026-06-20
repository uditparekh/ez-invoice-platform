"use client";

import {
  BarChart3,
  Building2,
  CircleAlert,
  FileClock,
  FileText,
  LogOut,
  Menu,
  Plug,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/app/invoices", label: "Invoices", icon: FileText },
  { href: "/app/history", label: "History", icon: FileClock },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/app/exceptions", label: "Exceptions", icon: CircleAlert },
];

const workspaceNavigation = [
  { href: "/app/integrations", label: "Integrations", icon: Plug },
  { href: "/app/rules", label: "Rules", icon: ShieldCheck },
  { href: "/app/settings", label: "Settings", icon: Settings2 },
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
        <p className="px-3 text-[10px] font-extrabold uppercase text-ink-muted">
          Workflow
        </p>
        <nav className="mt-3 space-y-1">
          {navigation.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={pathname === item.href}
              onNavigate={() => setMobileOpen(false)}
            />
          ))}
        </nav>
        <p className="mt-8 px-3 text-[10px] font-extrabold uppercase text-ink-muted">
          Workspace
        </p>
        <nav className="mt-3 space-y-1">
          {workspaceNavigation.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={pathname === item.href}
              onNavigate={() => setMobileOpen(false)}
            />
          ))}
        </nav>
      </div>
      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-[7px] px-3 py-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-strong text-xs font-bold text-ink">
            {(user?.full_name || user?.email || "EZ")
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
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-line bg-surface lg:flex">
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

      <div className="lg:pl-[248px]">
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
            <Building2 size={16} className="shrink-0 text-accent" />
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
  icon: typeof FileText;
  active: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        "flex h-11 items-center gap-3 rounded-[7px] border-l-2 px-3 text-sm font-semibold transition-colors",
        active
          ? "border-accent bg-accent-soft text-accent-ink"
          : "border-transparent text-ink-secondary hover:bg-surface-subtle hover:text-ink",
      )}
    >
      <Icon size={17} strokeWidth={1.8} />
      {label}
    </Link>
  );
}
