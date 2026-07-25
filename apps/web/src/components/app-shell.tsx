"use client";

import {
  BarChart3,
  Building2,
  Grid2X2,
  FileClock,
  FileText,
  LogOut,
  Menu,
  PlugZap,
  Search,
  SlidersHorizontal,
  Users,
  Workflow,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import {
  CommandCenter,
  openCommandPalette,
} from "@/components/command-center";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navGroups = [
  {
    label: "Work",
    items: [
      { href: "/app", label: "Home", icon: Grid2X2 },
      { href: "/app/invoices", label: "Invoices", icon: FileText },
      { href: "/app/history", label: "History", icon: FileClock },
      { href: "/app/analytics", label: "Insights", icon: BarChart3 },
    ],
  },
  {
    label: "Configure",
    items: [
      { href: "/app/integrations", label: "Integrations", icon: PlugZap },
      { href: "/app/rules", label: "Rules & mapping", icon: Workflow },
      { href: "/app/client-profiles", label: "Client profiles", icon: Users },
      { href: "/app/settings", label: "Settings", icon: SlidersHorizontal },
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

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    };
    const closeOnDesktop = () => {
      if (window.innerWidth >= 1024) {
        setMobileOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", closeOnDesktop);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", closeOnDesktop);
    };
  }, [mobileOpen]);

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
          <div
            key={group.label}
            className={cn(
              groupIndex ? "mt-8 max-lg:mt-0" : "",
              group.label === "Work" && "max-lg:hidden",
            )}
          >
            <p className="px-3 text-[11px] font-extrabold uppercase tracking-[0.18em] text-ink-muted">
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
        <div className="flex flex-col items-stretch gap-2 rounded-xl border border-transparent p-2 transition-colors hover:border-line hover:bg-surface-subtle lg:flex-row lg:items-center lg:gap-3 lg:pr-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-3">
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
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-9 w-32 shrink-0 self-start justify-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-xs font-extrabold text-ink-secondary transition-colors hover:border-danger/40 hover:bg-danger-soft hover:text-danger lg:w-auto lg:self-auto"
            onClick={() => void logout()}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={14} />
            Sign out
          </Button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[260px] flex-col border-r border-line bg-shell lg:flex">
        {nav}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/35"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="relative flex h-full w-[286px] flex-col border-r border-line bg-shell shadow-pop">
            <Button
              variant="secondary"
              size="sm"
              className="absolute right-3 top-3 z-10 size-10 rounded-xl px-0"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X size={18} />
            </Button>
            {nav}
          </aside>
        </div>
      )}

      <div className="min-w-0 lg:pl-[260px]">
        <header className="sticky top-0 z-30 flex h-16 items-center border-b border-line bg-shell/95 px-4 backdrop-blur sm:px-6 lg:px-8">
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
          <button
            type="button"
            onClick={openCommandPalette}
            className="ml-auto mr-3 hidden h-10 w-[min(34vw,360px)] items-center gap-2 rounded-full border border-line bg-surface-subtle px-3 text-sm font-semibold text-ink-muted transition-colors hover:border-line-strong hover:text-ink-secondary xl:flex"
            aria-label="Open command palette"
          >
            <span className="size-2 rounded-full bg-cyan" />
            <span className="min-w-0 flex-1 truncate text-left">
              Search invoices, vendors, pages…
            </span>
            <kbd className="rounded-md border border-line-strong bg-surface px-1.5 py-0.5 font-mono text-[10px] font-black text-ink-secondary">
              ⌘K
            </kbd>
          </button>
          <button
            type="button"
            onClick={openCommandPalette}
            className="ml-auto mr-2 grid size-11 place-items-center rounded-full border border-line bg-surface-subtle text-ink-secondary transition-colors hover:border-line-strong hover:text-ink xl:hidden"
            aria-label="Search invoices, vendors, and pages"
          >
            <Search size={17} />
          </button>
          <div>
            <ThemeToggle />
          </div>
        </header>
        <main className="min-w-0 overflow-x-hidden pb-24 lg:pb-0">
          {children}
        </main>
      </div>
      <MobileTabBar
        pathname={pathname}
        onOpenMenu={() => setMobileOpen(true)}
      />
      <CommandCenter />
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
          ? "border-accent bg-accent-soft text-accent-ink"
          : "border-transparent text-ink-secondary hover:bg-surface-subtle hover:text-ink",
      )}
    >
      <Icon size={17} strokeWidth={1.8} />
      {label}
    </Link>
  );
}

function isActivePath(pathname: string, href: string) {
  if (href === "/app") return pathname === "/app";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function MobileTabBar({
  pathname,
  onOpenMenu,
}: {
  pathname: string;
  onOpenMenu: () => void;
}) {
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-shell/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      <div className="mx-auto grid h-16 max-w-lg grid-cols-5">
        {navGroups[0].items.map((item) => {
          const active = isActivePath(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center justify-center gap-1 text-[10px] font-bold transition-colors",
                active
                  ? "text-accent-ink"
                  : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              <Icon size={20} strokeWidth={active ? 2.4 : 1.8} />
              {item.label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={onOpenMenu}
          className="flex flex-col items-center justify-center gap-1 text-[10px] font-bold text-ink-muted transition-colors hover:text-ink-secondary"
        >
          <Menu size={20} strokeWidth={1.8} />
          Menu
        </button>
      </div>
    </nav>
  );
}
