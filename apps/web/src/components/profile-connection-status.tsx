"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { useMasterNames } from "@/components/tally-master-provider";
import type {
  AccountingSystem,
  ClientProfile,
  TallyConnectorProfileStatus,
  TallyConnectorStatusResponse,
} from "@/lib/types";

/** Heartbeat display only. This component never claims jobs or contacts local Tally. */
export function ProfileConnectionStatus({
  profile,
  system,
  dirty,
}: {
  profile: ClientProfile | null;
  system: AccountingSystem;
  dirty: boolean;
}) {
  const { activeOrganizationId } = useAuth();
  const masters = useMasterNames("ledgers");
  const [state, setState] = useState<{
    key: string;
    status?: TallyConnectorProfileStatus;
    error?: string;
    checked?: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const profileId = profile?.id;
  const key = `${activeOrganizationId}:${profileId}`;
  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeOrganizationId || !profileId || system !== "tally") return;
      setLoading(true);
      try {
        const response = await fetch(
          `/api/organizations/${activeOrganizationId}/connectors/tally/status`,
          { cache: "no-store", signal },
        );
        if (!response.ok)
          throw new Error(
            `Status unavailable (HTTP ${response.status}). Try Refresh.`,
          );
        const payload = (await response.json()) as TallyConnectorStatusResponse;
        if (!signal?.aborted)
          setState({
            key,
            status: payload.statuses.find(
              (item) => item.client_profile_id === profileId,
            ),
            checked: new Date().toLocaleTimeString(),
          });
      } catch (error) {
        if (!signal?.aborted)
          setState({ key, error: (error as Error).message });
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [activeOrganizationId, profileId, system, key],
  );
  useEffect(() => {
    const controller = new AbortController();
    const start = window.setTimeout(() => void load(controller.signal), 0);
    const interval = window.setInterval(
      () => void load(controller.signal),
      15_000,
    );
    return () => {
      controller.abort();
      window.clearTimeout(start);
      window.clearInterval(interval);
    };
  }, [load]);
  const current = state?.key === key ? state : null;
  const status = current?.status;
  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h4 className="text-lg font-semibold text-ink">Connection overview</h4>
        {system === "tally" && profile && (
          <Button
            variant="secondary"
            size="sm"
            disabled={loading}
            onClick={() => void load()}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh status
          </Button>
        )}
      </div>
      {system === "tally" ? (
        <>
          {current?.error && (
            <p role="status" className="text-sm text-danger">
              {current.error}
            </p>
          )}
          <dl className="grid gap-3 sm:grid-cols-2">
            {[
              [
                "Cloud heartbeat",
                !profile
                  ? "Save the profile first"
                  : current?.error
                    ? "Unavailable"
                    : !current
                      ? "Checking…"
                      : status?.connected
                        ? "Connected"
                        : status?.last_seen_at
                          ? "Offline"
                          : "No check-in yet",
              ],
              [
                "Tally reachability",
                status?.connected
                  ? status.tally_detected === true
                    ? "Detected at last check-in"
                    : status.tally_detected === false
                      ? "Not detected at last check-in"
                      : "Not reported"
                  : "Not currently verified",
              ],
              [
                "Configured company",
                profile?.settings.company_name || "Not set",
              ],
              [
                "Accounting masters",
                masters.fresh
                  ? "Recent snapshot · review in Posting rules"
                  : "Unverified · sync from connector 0.7.0",
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className="min-w-0 rounded-xl border border-line bg-canvas p-3"
              >
                <dt className="text-xs font-medium text-ink-muted">{label}</dt>
                <dd className="mt-1 break-words text-sm font-semibold text-ink">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-sm leading-6 text-ink-secondary">
            This shows saved configuration and the last heartbeat, not a fresh
            connection test. On the Windows PC, use{" "}
            <strong>Test connection</strong> to check authentication, Tally and
            company availability without posting.
          </p>
          {dirty && (
            <p className="text-sm text-gold">
              Unsaved edits are not reflected in this status.
            </p>
          )}
          {current?.checked && (
            <p className="text-xs text-ink-muted">
              Refreshes every 15 seconds · Checked {current.checked}
            </p>
          )}
        </>
      ) : (
        <p className="text-sm leading-6 text-ink-secondary">
          Connection details belong to this accounting destination. Review its
          integration page for supported setup and connection checks.
        </p>
      )}
      <Link
        href={
          system === "excel" || system === "custom"
            ? "/app/integrations"
            : `/app/accounting/${system.replaceAll("_", "-")}`
        }
        className="inline-flex min-h-11 items-center text-sm font-semibold text-accent-ink underline underline-offset-4"
      >
        Open integration setup & downloads
      </Link>
    </div>
  );
}
