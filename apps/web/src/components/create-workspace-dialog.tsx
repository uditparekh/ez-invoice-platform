"use client";

import { Building2, LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";
import { apiErrorMessage, cn } from "@/lib/utils";

const currencyOptions: { value: string; label: string }[] = [
  { value: "INR", label: "INR ₹ — Indian Rupee" },
  { value: "USD", label: "USD $ — US Dollar" },
  { value: "AED", label: "AED — UAE Dirham" },
  { value: "GBP", label: "GBP £ — British Pound" },
  { value: "EUR", label: "EUR € — Euro" },
  { value: "SGD", label: "SGD $ — Singapore Dollar" },
];

type CreatedOrganization = { id: string; name: string };

/**
 * Creates a new workspace (organization) and switches into it.
 *
 * Each client gets its own workspace: invoices, profiles, team, vendor memory,
 * and connector token are all scoped to it, so nothing crosses between
 * clients. The person creating the workspace becomes its owner.
 */
export function CreateWorkspaceDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { refresh, selectOrganization } = useAuth();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  // Reset the form on close rather than on open, so no state is set
  // synchronously inside an effect.
  function close() {
    if (saving) return;
    setName("");
    setError("");
    onClose();
  }

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => nameRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, saving]);

  if (!open) return null;

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Give the workspace a name — usually the client's business name.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed, default_currency: currency }),
      });
      const payload = (await response.json().catch(() => ({}))) as
        | CreatedOrganization
        | ApiErrorPayload;
      if (!response.ok || !("id" in payload)) {
        throw new Error(apiErrorMessage(payload, "Workspace could not be created."));
      }
      // Refresh first so the new workspace is in the memberships list, then
      // switch to it. Switching before the refresh briefly points the app at
      // a workspace it does not know about yet.
      await refresh();
      selectOrganization(payload.id);
      setName("");
      setError("");
      onClose();
    } catch (createError) {
      setError((createError as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-workspace-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="w-full max-w-md rounded-3xl border border-line bg-surface p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent-ink">
              <Building2 size={20} />
            </span>
            <div>
              <h2 id="create-workspace-title" className="text-lg font-black text-ink">
                New workspace
              </h2>
              <p className="mt-1 text-sm leading-6 text-ink-secondary">
                One workspace per client. Its invoices, profiles, team, and
                Tally connection stay completely separate from every other
                workspace.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={saving}
            aria-label="Close"
            className="grid size-9 shrink-0 place-items-center rounded-xl text-ink-muted transition-colors hover:bg-surface-subtle hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-[11px] font-extrabold uppercase text-ink-muted">
              Workspace name
            </span>
            <input
              ref={nameRef}
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
              placeholder="Client's business name"
              maxLength={200}
              className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-accent"
            />
            <span className="mt-1.5 block text-xs font-semibold leading-5 text-ink-muted">
              Shown in the header and on invitations. You can rename it later in Settings.
            </span>
          </label>

          <label className="block">
            <span className="text-[11px] font-extrabold uppercase text-ink-muted">
              Default currency
            </span>
            <select
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              className="mt-2 h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-sm font-bold text-ink outline-none transition-colors focus:border-accent"
            >
              {currencyOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {error && (
            <p className="rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-sm font-bold text-danger">
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="secondary" onClick={close} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={saving}>
            {saving ? <LoaderCircle size={16} className="animate-spin" /> : <Building2 size={16} />}
            <span className={cn(saving && "opacity-80")}>
              {saving ? "Creating" : "Create workspace"}
            </span>
          </Button>
        </div>
      </div>
    </div>
  );
}
