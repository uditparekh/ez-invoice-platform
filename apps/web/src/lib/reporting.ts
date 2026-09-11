export interface WorkspaceAnalytics {
  start: string;
  end: string;
  timezone: string;
  generated_at: string;
  received_count: number;
  supplier_count: number;
  currencies: {
    currency: string;
    count: number;
    total: string;
    tax: string;
    posted_total: string;
  }[];
  suppliers: {
    supplier: string;
    currency: string;
    count: number;
    total: string;
  }[];
  daily: { date: string; count: number }[];
  cohort_statuses: Record<string, number>;
  queue: Record<string, number>;
  posting_outcomes: Record<string, number>;
}
export interface WorkspaceEvent {
  id: string;
  event_type: string;
  created_at: string;
  invoice_id: string | null;
  invoice_number: string | null;
  actor: string | null;
  details: {
    status?: string;
    fields?: string[];
    target?: string;
    dry_run?: boolean;
    posting_id?: string;
    deleted?: number;
  };
}
export interface EventPage {
  items: WorkspaceEvent[];
  next_cursor: string | null;
  snapshot: string;
  total: number;
}
export type ReportRange = { start: string; end: string };
export function currentMonth(): ReportRange {
  const today = new Date().toISOString().slice(0, 10);
  return { start: `${today.slice(0, 7)}-01`, end: today };
}
export function rangeQuery(range: ReportRange) {
  return new URLSearchParams(range).toString();
}
export function reportMoney(value: string | number, currency: string) {
  const number = Number(value);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      currencyDisplay: "code",
    }).format(number);
  } catch {
    return `${currency} ${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
}
export function downloadCsv(name: string, rows: (string | number)[][]) {
  const csv = rows
    .map((row) =>
      row
        .map((value) => {
          let text = String(value);
          if (/^[\s]*[=+@\-\t\r]/.test(text)) text = `'${text}`;
          return `"${text.replaceAll('"', '""')}"`;
        })
        .join(","),
    )
    .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
export function eventTitle(event: WorkspaceEvent) {
  const titles: Record<string, string> = {
    "invoice.created": "Invoice received",
    "invoice.corrected": "Invoice corrected",
    "invoice.approved": "Invoice approved",
    "invoice.posted": "Invoice marked posted",
    "invoice.failed": "Invoice marked failed",
    "invoice.posting": "Posting started",
    "invoice.validated":
      event.details.status === "needs_review"
        ? "Validation flagged issues"
        : "Validation completed",
    "invoice.needs_review": "Sent for review",
    "invoice.extracted": "Extraction completed",
    "posting.started": "Posting attempt started",
    "posting.completed": "Posting succeeded",
    "posting.failed": "Posting failed",
    "invoice.queue_cleared": "Invoice queue cleared",
    "invoice.file_retained": "Source document retained",
    "invoice.file_deleted": "Source document removed",
    "digest.sent": "Weekly digest sent",
  };
  return (
    (event.details.dry_run ? "Dry run · " : "") +
    (titles[event.event_type] ?? event.event_type.replaceAll(/[._]/g, " "))
  );
}
