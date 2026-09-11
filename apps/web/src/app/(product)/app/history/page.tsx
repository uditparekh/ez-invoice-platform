"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, FileClock, FileDown } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { LoadingState } from "@/components/dashboard/loading-state";
import { EmptyState } from "@/components/dashboard/empty-state";
import {
  ReportControls,
  ReportError,
} from "@/components/dashboard/report-controls";
import { Button } from "@/components/ui/button";
import { useWorkspaceReport } from "@/hooks/use-workspace-report";
import { useAuth } from "@/components/auth-provider";
import {
  currentMonth,
  eventTitle,
  type EventPage,
  type WorkspaceEvent,
} from "@/lib/reporting";
import type { PostingResult } from "@/lib/types";

export default function HistoryPage() {
  const { activeOrganizationId } = useAuth();
  // Remount query state on workspace changes, so cursor/snapshot never cross tenants.
  return <HistoryWorkspace key={activeOrganizationId ?? "none"} />;
}

function HistoryWorkspace() {
  const [range, setRange] = useState(currentMonth);
  const [category, setCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [pages, setPages] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const query = new URLSearchParams({
    ...range,
    category,
    search,
    limit: "30",
  });
  if (pages.length) query.set("cursor", pages[pages.length - 1]);
  if (snapshot) query.set("snapshot", snapshot);
  const report = useWorkspaceReport<EventPage>("events", query.toString());
  const data = report.data;
  function reset() {
    setPages([]);
    setSnapshot("");
    setExportError("");
  }
  function refresh() {
    reset();
    report.reload();
  }
  async function exportHistory() {
    if (!data || !report.organizationId) return;
    setExporting(true);
    setExportError("");
    try {
      const params = new URLSearchParams({
        ...range,
        category,
        search,
        snapshot: data.snapshot,
      });
      const response = await fetch(
        `/api/organizations/${report.organizationId}/events/export?${params}`,
      );
      if (!response.ok)
        throw new Error(
          "Export could not be completed. Try again or choose a smaller date range.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `siftentry-history-${range.start}-${range.end}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError((error as Error).message);
    } finally {
      setExporting(false);
    }
  }
  return (
    <div className="bg-canvas">
      <PageHeader
        title="History"
        description="Recorded workspace events, from receipt to posting."
        action={
          <Button
            onClick={() => void exportHistory()}
            disabled={!data || exporting}
          >
            <FileDown size={16} />
            {exporting ? "Exporting…" : "Export CSV"}
          </Button>
        }
      />
      <main className="report-main">
        <ReportControls
          range={range}
          onChange={(value) => {
            setRange(value);
            reset();
          }}
          onRefresh={refresh}
          loading={report.loading}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            Events
            <select
              aria-label="Event category"
              className="h-11 rounded-lg border border-line-strong bg-surface px-3 text-ink"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                reset();
              }}
            >
              <option value="all">All events</option>
              <option value="invoice">Invoices</option>
              <option value="posting">Posting attempts</option>
              <option value="client_profile">Client profiles</option>
              <option value="organization">Workspace</option>
              <option value="job">Background jobs</option>
              <option value="digest">Email digests</option>
            </select>
          </label>
          <form
            className="flex w-full min-w-0 gap-2 sm:w-auto sm:flex-1 sm:max-w-sm"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(draftSearch.trim());
              reset();
            }}
          >
            <input
              aria-label="Search history"
              placeholder="Invoice number or event type"
              value={draftSearch}
              onChange={(e) => setDraftSearch(e.target.value)}
              className="h-11 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 text-sm"
              maxLength={120}
            />
            <Button type="submit">Search</Button>
          </form>
        </div>
        {exportError && (
          <ReportError
            message={exportError}
            retry={() => void exportHistory()}
          />
        )}
        {report.loading && <LoadingState label="Loading recorded events" />}
        {report.error && (
          <ReportError message={report.error} retry={report.reload} />
        )}
        {data && (
          <>
            <div
              className="flex flex-wrap justify-between gap-2 text-xs text-ink-secondary"
              aria-live="polite"
            >
              <span>
                {data.total.toLocaleString()} recorded events
                {search ? ` matching “${search}”` : ""}
              </span>
              <span>
                As of {new Date(data.snapshot).toLocaleString()} · refresh for
                newer events
              </span>
            </div>
            {!data.items.length ? (
              <EmptyState
                icon={FileClock}
                title="No recorded events in this view"
                description="Try a wider date range or different filter. History only shows saved events; it does not reconstruct missing activity from invoice status."
              />
            ) : (
              <section
                className="overflow-hidden rounded-xl border border-line bg-surface"
                aria-label="Recorded history"
              >
                <ol className="divide-y divide-line">
                  {data.items.map((event) => (
                    <EventRow
                      key={event.id}
                      event={event}
                      onRefresh={refresh}
                    />
                  ))}
                </ol>
              </section>
            )}
            {(pages.length > 0 || data.next_cursor) && (
              <div className="flex items-center justify-between gap-3 text-sm">
                <Button
                  disabled={!pages.length}
                  onClick={() => setPages((items) => items.slice(0, -1))}
                >
                  Previous
                </Button>
                <span>Page {pages.length + 1}</span>
                <Button
                  disabled={!data.next_cursor}
                  onClick={() => {
                    setSnapshot(data.snapshot);
                    setPages((items) => [...items, data.next_cursor!]);
                  }}
                >
                  Next
                </Button>
              </div>
            )}
            <p className="text-xs leading-5 text-ink-secondary">
              Times are shown in your local timezone; date filters use UTC.
              Export includes every matching recorded event, not just this page.
              Older events may have no recorded actor. This operational history
              is not a tamper-proof compliance archive; invoice deletion can
              remove associated records.
            </p>
          </>
        )}
      </main>
    </div>
  );
}

function EventRow({
  event,
  onRefresh,
}: {
  event: WorkspaceEvent;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const failed =
    event.event_type === "posting.failed" ||
    event.event_type === "invoice.failed";
  return (
    <li className="px-4 py-5 sm:px-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p
            className={`text-sm font-semibold ${failed ? "text-danger" : "text-ink"}`}
          >
            {eventTitle(event)}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-secondary">
            {event.invoice_id && (
              <Link
                className="inline-flex items-center gap-1 break-all text-accent-ink hover:underline"
                href={`/app/invoices/${event.invoice_id}`}
              >
                {event.invoice_number || event.invoice_id.slice(0, 8)}
                <ArrowUpRight size={13} />
              </Link>
            )}
            <span>{event.actor || "Actor not recorded"}</span>
            {event.details.target && (
              <span>{event.details.target.replace("PostingTarget.", "")}</span>
            )}
          </div>
          {event.details.fields?.length ? (
            <p className="mt-2 break-words text-xs text-ink-secondary">
              Changed fields: {event.details.fields.join(", ")}
            </p>
          ) : null}
        </div>
        <time
          className="shrink-0 text-xs text-ink-secondary"
          dateTime={event.created_at}
        >
          {new Date(event.created_at).toLocaleString()}
        </time>
      </div>
      <details className="mt-3 text-xs text-ink-secondary">
        <summary className="cursor-pointer">Event details</summary>
        <dl className="mt-2 space-y-1 break-all">
          <div>Type: {event.event_type}</div>
          <div>Event ID: {event.id}</div>
          <div>UTC: {event.created_at}</div>
          {event.details.status && (
            <div>Recorded status: {event.details.status}</div>
          )}
        </dl>
      </details>
      {event.details.posting_id && (
        <div className="mt-3">
          <Button
            size="sm"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            {expanded ? "Hide posting result" : "View posting result"}
          </Button>
          {expanded && (
            <PostingDetail
              id={event.details.posting_id}
              onRefresh={onRefresh}
            />
          )}
        </div>
      )}
    </li>
  );
}

function PostingDetail({
  id,
  onRefresh,
}: {
  id: string;
  onRefresh: () => void;
}) {
  const { user, activeOrganizationId } = useAuth();
  const role = user?.memberships.find(
    (item) => item.organization_id === activeOrganizationId,
  )?.role;
  const [result, setResult] = useState<PostingResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/postings/${encodeURIComponent(id)}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Posting result is unavailable.");
        const payload = (await response.json()) as PostingResult;
        if (!controller.signal.aborted) setResult(payload);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [id]);
  async function load(retry = false) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/postings/${id}${retry ? "/retry" : ""}`,
        retry ? { method: "POST" } : { cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok)
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "Posting result is unavailable.",
        );
      setResult(payload as PostingResult);
      if (retry) onRefresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mt-3 rounded-lg border border-line bg-surface-subtle p-4 text-sm">
      {!result && busy && <p role="status">Loading posting result…</p>}
      {!result && !busy && (
        <Button onClick={() => void load()} disabled={busy}>
          {busy ? "Loading…" : "Load recorded response"}
        </Button>
      )}
      {error && (
        <p role="alert" className="mt-2 text-danger">
          {error}
        </p>
      )}
      {result && (
        <>
          <p className="font-medium capitalize">
            {result.status} · {result.target}
            {result.dry_run ? " · dry run" : ""}
          </p>
          <p className="mt-2 break-words text-ink-secondary">
            {result.message}
          </p>
          {result.external_id && (
            <p className="mt-1 break-all text-ink-secondary">
              External reference: {result.external_id}
            </p>
          )}
          <details className="mt-3">
            <summary className="cursor-pointer">
              Recorded system response
            </summary>
            <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all text-xs">
              {JSON.stringify(result.response_payload, null, 2)}
            </pre>
          </details>
          {result.status === "failed" &&
            role &&
            ["owner", "admin", "accountant"].includes(role) && (
              <div className="mt-4">
                <p className="mb-2 text-xs text-ink-secondary">
                  Confirm the invoice is approved and reconcile uncertain
                  results in the accounting system before retrying.
                </p>
                <Button disabled={busy} onClick={() => void load(true)}>
                  {busy ? "Submitting…" : "Retry posting"}
                </Button>
              </div>
            )}
        </>
      )}
    </div>
  );
}
