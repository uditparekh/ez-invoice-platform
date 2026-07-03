"use client";

import {
  ArrowUpRight,
  BadgeCheck,
  BadgeDollarSign,
  BarChart3,
  FileClock,
  FileText,
  Grid2X2,
  Keyboard,
  Moon,
  PlugZap,
  Plus,
  Search,
  SlidersHorizontal,
  Upload,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { useWorkspaceInvoices } from "@/hooks/use-workspace-invoices";
import { cn, formatCurrency } from "@/lib/utils";

/** Command center — UI Spec §18 wow backlog #1 + #2.
 *  ⌘K / Ctrl+K command palette (actions · pages · live invoice search)
 *  and the "?" keyboard-shortcuts overlay. Mounted once in AppShell.
 *  Anything in the app can open the palette via:
 *  window.dispatchEvent(new CustomEvent("siftentry:palette")) */

const PALETTE_EVENT = "siftentry:palette";

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(PALETTE_EVENT));
}

type Command = {
  id: string;
  group: "Actions" | "Pages";
  label: string;
  hint?: string;
  keywords: string;
  icon: ReactNode;
  run: (router: ReturnType<typeof useRouter>) => void;
};

const commands: Command[] = [
  {
    id: "act-upload",
    group: "Actions",
    label: "Upload invoices",
    hint: "PDF → queue",
    keywords: "upload add new invoice pdf import",
    icon: <Upload size={16} />,
    run: (router) => router.push("/app/invoices"),
  },
  {
    id: "act-sift",
    group: "Actions",
    label: "Start Sift mode",
    hint: "clear the review queue",
    keywords: "sift review triage keyboard clear queue",
    icon: <Zap size={16} />,
    run: (router) => router.push("/app/sift"),
  },
  {
    id: "act-profile",
    group: "Actions",
    label: "New client profile",
    hint: "4-minute wizard",
    keywords: "client profile onboarding wizard new create",
    icon: <Plus size={16} />,
    run: (router) => router.push("/app/client-profiles"),
  },
  {
    id: "act-approvals",
    group: "Actions",
    label: "Open approvals",
    hint: "one-tap sign-off",
    keywords: "approve approval pending sign off mobile",
    icon: <BadgeCheck size={16} />,
    run: (router) => router.push("/app/approvals"),
  },
  {
    id: "act-theme",
    group: "Actions",
    label: "Toggle dark mode",
    keywords: "theme dark light appearance toggle",
    icon: <Moon size={16} />,
    run: () => {
      const dark = !document.documentElement.classList.contains("dark");
      document.documentElement.classList.toggle("dark", dark);
      window.localStorage.setItem("siftentry-theme", dark ? "dark" : "light");
    },
  },
  { id: "pg-home", group: "Pages", label: "Home", keywords: "home dashboard start", icon: <Grid2X2 size={16} />, run: (router) => router.push("/app") },
  { id: "pg-invoices", group: "Pages", label: "Invoices", keywords: "invoices queue documents bills", icon: <FileText size={16} />, run: (router) => router.push("/app/invoices") },
  { id: "pg-history", group: "Pages", label: "History", keywords: "history audit log postings retry", icon: <FileClock size={16} />, run: (router) => router.push("/app/history") },
  { id: "pg-insights", group: "Pages", label: "Insights", keywords: "insights analytics charts spend touchless finance", icon: <BarChart3 size={16} />, run: (router) => router.push("/app/analytics") },
  { id: "pg-integrations", group: "Pages", label: "Integrations", keywords: "integrations tally quickbooks zoho connect", icon: <PlugZap size={16} />, run: (router) => router.push("/app/integrations") },
  { id: "pg-rules", group: "Pages", label: "Rules & mapping", keywords: "rules mapping gl ledger simulator vendor memory training", icon: <Workflow size={16} />, run: (router) => router.push("/app/rules") },
  { id: "pg-clients", group: "Pages", label: "Client profiles", keywords: "clients profiles onboarding wizard", icon: <Users size={16} />, run: (router) => router.push("/app/client-profiles") },
  { id: "pg-settings", group: "Pages", label: "Settings", keywords: "settings team retention notifications appearance security", icon: <SlidersHorizontal size={16} />, run: (router) => router.push("/app/settings") },
];

export function CommandCenter() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShortcutsOpen(false);
        setPaletteOpen((open) => !open);
        return;
      }
      const tag = (event.target as HTMLElement)?.tagName;
      const typing =
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if (event.key === "?" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        setPaletteOpen(false);
        setShortcutsOpen((open) => !open);
      }
    }
    function onOpenEvent() {
      setShortcutsOpen(false);
      setPaletteOpen(true);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener(PALETTE_EVENT, onOpenEvent);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener(PALETTE_EVENT, onOpenEvent);
    };
  }, []);

  return (
    <>
      {paletteOpen && <Palette onClose={() => setPaletteOpen(false)} />}
      {shortcutsOpen && (
        <ShortcutsOverlay onClose={() => setShortcutsOpen(false)} />
      )}
    </>
  );
}

/* ================= palette ================= */

function Palette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { activeOrganizationId } = useAuth();
  const { invoices } = useWorkspaceInvoices();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const q = query.trim().toLowerCase();

  const approvedCount = useMemo(
    () => invoices.filter((invoice) => invoice.status === "approved").length,
    [invoices],
  );

  const allCommands = useMemo<Command[]>(() => {
    if (!approvedCount || !activeOrganizationId) return commands;
    const batch: Command = {
      id: "act-batch-post",
      group: "Actions",
      label: `Post all approved invoices (${approvedCount})`,
      hint: "batch → books",
      keywords: "post all ready approved batch tally books push",
      icon: <BadgeDollarSign size={16} />,
      run: (nav) => {
        if (
          !window.confirm(
            `Post ${approvedCount} approved invoice${approvedCount === 1 ? "" : "s"} to the accounting system now? Results land in History › Posting log.`,
          )
        )
          return;
        void fetch(
          `/api/organizations/${activeOrganizationId}/invoices/post-ready`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          },
        ).finally(() => nav.push("/app/history"));
      },
    };
    return [batch, ...commands];
  }, [approvedCount, activeOrganizationId]);

  const matchedCommands = useMemo(
    () =>
      allCommands.filter(
        (command) =>
          !q ||
          command.label.toLowerCase().includes(q) ||
          command.keywords.includes(q),
      ),
    [allCommands, q],
  );

  const matchedInvoices = useMemo(() => {
    if (!q) return invoices.slice(0, 3);
    return invoices
      .filter(
        (invoice) =>
          (invoice.invoice_number || "").toLowerCase().includes(q) ||
          (invoice.supplier.name || "").toLowerCase().includes(q),
      )
      .slice(0, 6);
  }, [invoices, q]);

  type Row =
    | { kind: "command"; command: Command }
    | { kind: "invoice"; invoice: (typeof invoices)[number] };

  const rows: Row[] = useMemo(
    () => [
      ...matchedCommands.map((command) => ({ kind: "command" as const, command })),
      ...matchedInvoices.map((invoice) => ({ kind: "invoice" as const, invoice })),
    ],
    [matchedCommands, matchedInvoices],
  );

  const execute = useCallback(
    (row: Row) => {
      onClose();
      if (row.kind === "command") row.command.run(router);
      else
        router.push(
          `/app/invoices?invoice=${row.invoice.id}&mode=review`,
        );
    },
    [onClose, router],
  );

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(rows.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter" && rows[activeIndex]) {
      event.preventDefault();
      execute(rows[activeIndex]);
    }
  }

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-row="${activeIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  let renderedGroup = "";

  return (
    <div
      className="fixed inset-0 z-[70] bg-black/45 p-4 backdrop-blur-[2px]"
      onMouseDown={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="mx-auto mt-[12vh] max-w-[580px] overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-pop"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search size={17} className="shrink-0 text-ink-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="Search invoices, vendors, pages, actions…"
            className="h-14 min-w-0 flex-1 bg-transparent text-[15px] font-semibold text-ink outline-none placeholder:text-ink-muted"
            aria-label="Command palette search"
          />
          <Kbd>esc</Kbd>
        </div>

        <div ref={listRef} className="max-h-[46vh] overflow-y-auto p-2">
          {rows.length === 0 && (
            <p className="px-3 py-8 text-center text-sm font-semibold text-ink-muted">
              No matches for “{query}” — try a vendor name or invoice number.
            </p>
          )}
          {rows.map((row, index) => {
            const group = row.kind === "command" ? row.command.group : "Invoices";
            const header =
              group !== renderedGroup ? (renderedGroup = group) : null;
            return (
              <div key={row.kind === "command" ? row.command.id : row.invoice.id}>
                {header && (
                  <p className="px-3 pb-1 pt-3 text-[10px] font-extrabold uppercase tracking-[0.16em] text-ink-muted first:pt-1">
                    {header}
                  </p>
                )}
                <button
                  type="button"
                  data-row={index}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => execute(row)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                    index === activeIndex
                      ? "bg-accent-soft text-accent-ink"
                      : "text-ink-secondary",
                  )}
                >
                  {row.kind === "command" ? (
                    <>
                      <span
                        className={cn(
                          "grid size-8 shrink-0 place-items-center rounded-lg",
                          index === activeIndex
                            ? "bg-accent text-white"
                            : "bg-surface-strong text-ink-secondary",
                        )}
                      >
                        {row.command.icon}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-black text-ink">
                        {row.command.label}
                      </span>
                      {row.command.hint && (
                        <span className="shrink-0 text-xs font-semibold text-ink-muted">
                          {row.command.hint}
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <span
                        className={cn(
                          "grid size-8 shrink-0 place-items-center rounded-lg",
                          index === activeIndex
                            ? "bg-accent text-white"
                            : "bg-surface-strong text-ink-secondary",
                        )}
                      >
                        <FileText size={15} />
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        <span className="block truncate text-sm font-black text-ink">
                          {row.invoice.supplier.name || "Supplier pending"} ·{" "}
                          <span className="font-mono">
                            {row.invoice.invoice_number || row.invoice.id.slice(0, 8)}
                          </span>
                        </span>
                        <span className="block text-xs font-bold text-ink-muted">
                          {formatCurrency(row.invoice.total, row.invoice.currency)} ·{" "}
                          {row.invoice.status.replaceAll("_", " ")}
                        </span>
                      </span>
                      <ArrowUpRight size={14} className="shrink-0 text-ink-muted" />
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-4 border-t border-line bg-surface-subtle px-4 py-2.5 text-[11px] font-bold text-ink-muted">
          <span><Kbd>↑↓</Kbd> navigate</span>
          <span><Kbd>↵</Kbd> open</span>
          <span><Kbd>esc</Kbd> close</span>
          <span className="ml-auto"><Kbd>?</Kbd> all shortcuts</span>
        </div>
      </div>
    </div>
  );
}

/* ================= shortcuts overlay ================= */

function ShortcutsOverlay({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const groups: { title: string; rows: [string, string][] }[] = [
    {
      title: "Global",
      rows: [
        ["⌘K / Ctrl+K", "Open the command palette"],
        ["?", "Show this shortcuts overlay"],
        ["Esc", "Close any overlay"],
      ],
    },
    {
      title: "Invoices queue",
      rows: [
        ["J / K", "Next / previous invoice"],
        ["Enter", "Open the selected invoice in review"],
        ["/", "Focus search"],
      ],
    },
    {
      title: "Invoices queue",
      rows: [
        ["J / K", "Move selection down / up the list"],
        ["Enter", "Open the selected invoice in review"],
        ["/", "Focus the queue search"],
      ],
    },
    {
      title: "Sift mode",
      rows: [
        ["A / Enter", "Approve & next"],
        ["E", "Edit in the Review Workspace"],
        ["S", "Skip to the back of the queue"],
        ["J / K", "Next / previous invoice"],
        ["Esc", "Exit Sift mode"],
      ],
    },
    {
      title: "Review Workspace",
      rows: [
        ["Click a field", "Highlight its evidence on the PDF"],
        ["Drag the divider", "Resize PDF vs fields (double-click resets)"],
        ["← →", "Resize when the divider is focused"],
      ],
    },
  ];

  return (
    <div
      className="fixed inset-0 z-[70] bg-black/45 p-4 backdrop-blur-[2px]"
      onMouseDown={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="mx-auto mt-[10vh] max-w-[520px] overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-pop"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <p className="flex items-center gap-2 text-sm font-black text-ink">
            <Keyboard size={16} className="text-accent" />
            Keyboard shortcuts
          </p>
          <Kbd>esc</Kbd>
        </div>
        <div className="max-h-[56vh] space-y-5 overflow-y-auto p-5">
          {groups.map((group) => (
            <div key={group.title}>
              <p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-ink-muted">
                {group.title}
              </p>
              <div className="mt-2 divide-y divide-line rounded-xl border border-line">
                {group.rows.map(([keys, action]) => (
                  <div
                    key={keys}
                    className="flex items-center justify-between gap-4 px-3.5 py-2.5"
                  >
                    <span className="text-sm font-semibold text-ink-secondary">
                      {action}
                    </span>
                    <Kbd>{keys}</Kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-md border border-line-strong bg-surface-strong px-1.5 py-0.5 font-mono text-[11px] font-black text-ink-secondary">
      {children}
    </kbd>
  );
}
