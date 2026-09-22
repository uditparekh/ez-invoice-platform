"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useState,
} from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth-provider";
import type { ClientProfile, ClientProfilePayload } from "@/lib/types";

export type MasterKind =
  | "ledgers"
  | "stock_items"
  | "units"
  | "godowns"
  | "voucher_types";
type MasterRow = {
  name: string;
  guid: string;
  parent: string;
  base_units: string;
};
type MasterView = {
  state: "fresh" | "stale" | "not_synced";
  snapshot: {
    id: string;
    company: { name: string; guid: string };
    synced_at: string;
    masters: Record<MasterKind, MasterRow[]>;
  } | null;
  profile_fingerprint: string;
  mapping_confirmed: boolean;
  confirmation: { confirmed_at: string } | null;
  checks: { field: string; name: string; kind: MasterKind; found: boolean }[];
};
type MasterContext = {
  view: MasterView | null;
  loading: boolean;
  error: string;
  dirty: boolean;
  sourceMatches: boolean;
  canEdit: boolean;
  hasProfile: boolean;
  refresh: () => void;
  confirm: () => Promise<void>;
};
const Context = createContext<MasterContext | null>(null);

export function TallyMasterProvider({
  profile,
  draft,
  dirty,
  canEdit,
  children,
}: {
  profile: ClientProfile | null;
  draft: ClientProfilePayload;
  dirty: boolean;
  canEdit: boolean;
  children: React.ReactNode;
}) {
  const { activeOrganizationId } = useAuth();
  const key = `${activeOrganizationId}:${profile?.id}:${profile?.updated_at}`;
  const [state, setState] = useState<{
    key: string;
    view?: MasterView;
    error?: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const profileId = profile?.id;
  const system = profile?.accounting_system;
  const url = `/api/organizations/${activeOrganizationId}/client-profiles/${profileId}/tally-masters`;
  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!profileId || !activeOrganizationId || system !== "tally") return;
      setLoading(true);
      try {
        const response = await fetch(url, { cache: "no-store", signal });
        if (!response.ok)
          throw new Error(
            `Master snapshot unavailable (HTTP ${response.status}). Try again.`,
          );
        const view = (await response.json()) as MasterView;
        if (!signal?.aborted) setState({ key, view });
      } catch (error) {
        if (!signal?.aborted)
          setState({ key, error: (error as Error).message });
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [profileId, activeOrganizationId, system, url, key],
  );
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void load(controller.signal), 0);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [load]);
  const current = state?.key === key ? state : null;
  const view = current?.view ?? null;
  useEffect(() => {
    if (view?.state !== "fresh" || !view.snapshot) return;
    const delay = Math.max(
      0,
      new Date(view.snapshot.synced_at).getTime() + 86400000 - Date.now(),
    );
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => void load(controller.signal),
      delay + 1000,
    );
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [view, load]);
  const connection = draft.settings.connection_settings;
  const savedConnection = profile?.settings.connection_settings;
  const sourceMatches = Boolean(
    profile &&
      draft.accounting_system === "tally" &&
      draft.settings.company_name === profile.settings.company_name &&
      ["workspace_id", "tally_url", "url", "connector_enabled"].every(
        (field) => connection[field] === savedConnection?.[field],
      ),
  );
  async function confirm() {
    if (!view?.snapshot || dirty || !canEdit || !sourceMatches) return;
    setLoading(true);
    try {
      const response = await fetch(`${url}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          snapshot_id: view.snapshot.id,
          profile_fingerprint: view.profile_fingerprint,
        }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Could not confirm mappings. Refresh and try again.",
        );
      setState({ key, view: result as MasterView });
    } catch (error) {
      setState({ key, error: (error as Error).message });
    } finally {
      setLoading(false);
    }
  }
  return (
    <Context.Provider
      value={{
        view,
        loading,
        error: current?.error ?? "",
        dirty,
        sourceMatches,
        canEdit,
        hasProfile: Boolean(profile),
        refresh: () => void load(),
        confirm,
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useMasterNames(kind?: MasterKind) {
  const context = useContext(Context);
  const fresh = context?.sourceMatches && context.view?.state === "fresh";
  const rows =
    kind && fresh ? (context?.view?.snapshot?.masters[kind] ?? []) : [];
  return {
    rows,
    fresh: Boolean(fresh),
    confirmed: Boolean(
      fresh && context?.view?.mapping_confirmed && !context.dirty,
    ),
  };
}

export function MasterSnapshotPanel() {
  const context = useContext(Context);
  const checkboxId = useId();
  const [acceptedKey, setAcceptedKey] = useState("");
  if (!context) return null;
  const {
    view,
    loading,
    error,
    dirty,
    sourceMatches,
    canEdit,
    hasProfile,
    refresh,
    confirm,
  } = context;
  const snapshot = sourceMatches ? view?.snapshot : null;
  const acceptanceKey = `${snapshot?.id}:${view?.profile_fingerprint}:${dirty}`;
  const accepted = acceptedKey === acceptanceKey;
  const missing = view?.checks.filter((check) => !check.found) ?? [];
  return (
    <section
      className="space-y-4 rounded-2xl border border-line bg-surface p-4"
      aria-label="Tally master snapshot"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-lg font-semibold text-ink">
            Tally master snapshot
          </h4>
          <p className="mt-1 text-sm text-ink-secondary">
            Read-only discovery · no invoices claimed or posted
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={!hasProfile || loading}
          onClick={refresh}
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />{" "}
          Refresh snapshot
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {snapshot ? (
        <>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs text-ink-muted">Company</dt>
              <dd className="break-words text-sm font-semibold text-ink">
                {snapshot.company.name}
              </dd>
              <dd className="mt-1 break-all text-xs text-ink-muted">
                GUID {snapshot.company.guid}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Last successful sync</dt>
              <dd className="text-sm text-ink">
                {new Date(snapshot.synced_at).toLocaleString()}
              </dd>
              <dd className="mt-1 text-xs text-ink-muted">
                {view?.state === "fresh"
                  ? "Recent snapshot · not a live guarantee"
                  : "Stale · sync again before confirming"}
              </dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-2">
            {Object.entries(snapshot.masters).map(([kind, rows]) => (
              <span
                key={kind}
                className="rounded-lg border border-line bg-canvas px-2.5 py-1.5 text-xs text-ink-secondary"
              >
                {rows.length.toLocaleString()} {kind.replaceAll("_", " ")}
              </span>
            ))}
          </div>
          <details className="rounded-xl border border-line p-3">
            <summary className="cursor-pointer text-sm font-semibold text-ink">
              Saved mapping checks ·{" "}
              {missing.length
                ? `${missing.length} missing`
                : "all configured names found"}
            </summary>
            <ul className="mt-3 space-y-2">
              {view?.checks.map((check) => (
                <li
                  key={check.field}
                  className="flex flex-wrap justify-between gap-2 text-sm"
                >
                  <span className="min-w-0 break-words text-ink-secondary">
                    {check.field}: {check.name}
                  </span>
                  <span
                    className={
                      check.found ? "text-ink-secondary" : "text-danger"
                    }
                  >
                    {check.found ? "Found in snapshot" : "Not found"}
                  </span>
                </li>
              ))}
            </ul>
          </details>
          {view?.mapping_confirmed && !dirty ? (
            <p
              role="status"
              className="rounded-xl border border-line bg-canvas p-3 text-sm text-ink"
            >
              Mapping confirmed ·{" "}
              {view.confirmation &&
                new Date(view.confirmation.confirmed_at).toLocaleString()}
              . Invoice approval is still required.
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-ink-secondary">
                Found in Tally means the name exists. Only an accountant can
                confirm it is the right destination. Supplier ledgers,
                invoice-specific allocations and tax correctness still need
                invoice review.
              </p>
              {canEdit && (
                <>
                  <label
                    htmlFor={checkboxId}
                    className="flex min-h-11 items-start gap-3 text-sm text-ink-secondary"
                  >
                    <input
                      id={checkboxId}
                      type="checkbox"
                      checked={accepted}
                      onChange={(event) =>
                        setAcceptedKey(
                          event.target.checked ? acceptanceKey : "",
                        )
                      }
                      className="mt-1 h-4 w-4 shrink-0 accent-[var(--accent)]"
                    />
                    I reviewed the saved rules and confirm these are the
                    intended accounting mappings.
                  </label>
                  <Button
                    variant="secondary"
                    disabled={
                      !accepted ||
                      dirty ||
                      loading ||
                      view?.state !== "fresh" ||
                      missing.length > 0
                    }
                    onClick={() => void confirm()}
                  >
                    Confirm saved mappings
                  </Button>
                </>
              )}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-ink-secondary">
          {!hasProfile
            ? "Save this profile first."
            : !sourceMatches
              ? "Save the new company/connection details, then sync its masters."
              : loading
                ? "Loading master snapshot…"
                : "No master snapshot yet. Manual names remain Unverified."}
        </p>
      )}
      {dirty && (
        <p className="text-sm text-gold">
          Save your changes before confirming mappings. Checks above refer to
          saved settings.
        </p>
      )}
      <p className="text-sm leading-6 text-ink-secondary">
        On the client’s PC, install connector 0.7.0, open the correct Tally
        company, click <strong>Stop</strong>, then{" "}
        <strong>Sync Tally masters</strong>. When it finishes, refresh here.
        Restart polling separately when ready. Snapshots older than 24 hours
        need a new sync.
      </p>
    </section>
  );
}
