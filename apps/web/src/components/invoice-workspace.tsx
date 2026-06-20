"use client";

import {
  ChevronDown,
  LoaderCircle,
  Search,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { InvoiceDetailPanel } from "@/components/invoices/invoice-detail";
import { InvoiceList } from "@/components/invoices/invoice-list";
import { QueueMetrics } from "@/components/invoices/queue-metrics";
import { Button } from "@/components/ui/button";
import type { ApiErrorPayload, Invoice, InvoiceStatus } from "@/lib/types";

const queueStatuses: { label: string; status?: InvoiceStatus }[] = [
  { label: "All invoices" },
  { label: "Needs review", status: "needs_review" },
  { label: "Validated", status: "validated" },
  { label: "Approved", status: "approved" },
  { label: "Posted", status: "posted" },
];

export function InvoiceWorkspace() {
  const { activeOrganizationId: organizationId } = useAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InvoiceStatus | undefined>();
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!organizationId) return;
    const orgId = organizationId;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams({
          organization_id: orgId,
          limit: "100",
        });
        if (status) query.set("status", status);
        const response = await fetch(`/api/invoices?${query}`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Unable to load invoices.");
        const nextInvoices = (await response.json()) as Invoice[];
        setInvoices(nextInvoices);
        setSelectedId((current) =>
          current && nextInvoices.some((invoice) => invoice.id === current)
            ? current
            : (nextInvoices[0]?.id ?? null),
        );
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setError((loadError as Error).message);
        }
      } finally {
        setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [organizationId, status]);

  const visibleInvoices = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return invoices;
    return invoices.filter((invoice) =>
      [
        invoice.invoice_number,
        invoice.supplier.name,
        invoice.source_file,
      ].some((value) => value.toLowerCase().includes(term)),
    );
  }, [invoices, search]);

  const selected =
    visibleInvoices.find((invoice) => invoice.id === selectedId) ??
    visibleInvoices[0] ??
    null;

  const counts = useMemo(
    () => ({
      total: invoices.length,
      review: invoices.filter((invoice) => invoice.status === "needs_review")
        .length,
      ready: invoices.filter((invoice) =>
        ["validated", "approved"].includes(invoice.status),
      ).length,
      posted: invoices.filter((invoice) => invoice.status === "posted").length,
    }),
    [invoices],
  );

  async function uploadFiles(files: FileList | null) {
    if (!files?.length || !organizationId) return;
    setUploading(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.set("file", file);
        const query = new URLSearchParams({
          organization_id: organizationId,
          parser_mode: "auto",
        });
        const response = await fetch(`/api/invoices/upload?${query}`, {
          method: "POST",
          body: formData,
        });
        if (!response.ok) {
          const payload = (await response.json()) as ApiErrorPayload;
          throw new Error(payload.detail ?? `Could not process ${file.name}.`);
        }
        const invoice = (await response.json()) as Invoice;
        setInvoices((current) => [invoice, ...current]);
        setSelectedId(invoice.id);
      }
    } catch (uploadError) {
      setError((uploadError as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="min-h-[calc(100vh-64px)]">
      <section className="border-b border-line bg-surface px-4 py-5 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center">
          <div className="min-w-[190px]">
            <p className="text-xs font-bold text-ink-muted">Workflow</p>
            <h1 className="mt-1 text-2xl font-bold text-ink">Invoice queue</h1>
          </div>
          <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center xl:justify-end">
            <label className="flex h-11 min-w-0 flex-1 items-center gap-2.5 rounded-[7px] border border-line-strong bg-canvas px-3.5 xl:max-w-[480px]">
              <Search size={17} className="shrink-0 text-ink-muted" />
              <input
                aria-label="Search invoices"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search invoice, supplier, or file"
                className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="text-ink-muted hover:text-ink"
                  aria-label="Clear search"
                >
                  <X size={15} />
                </button>
              )}
            </label>
            <label className="relative">
              <select
                aria-label="Filter invoice status"
                value={status ?? ""}
                onChange={(event) =>
                  setStatus((event.target.value || undefined) as
                    | InvoiceStatus
                    | undefined)
                }
                className="h-11 w-full appearance-none rounded-[7px] border border-line-strong bg-surface pl-3.5 pr-10 text-sm font-semibold text-ink outline-none hover:border-accent sm:w-[160px]"
              >
                {queueStatuses.map((item) => (
                  <option key={item.label} value={item.status ?? ""}>
                    {item.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={16}
                className="pointer-events-none absolute right-3 top-3.5 text-ink-muted"
              />
            </label>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf"
              multiple
              className="hidden"
              onChange={(event) => void uploadFiles(event.target.files)}
            />
            <Button
              variant="primary"
              className="shrink-0"
              onClick={() => fileInput.current?.click()}
              disabled={uploading || !organizationId}
            >
              {uploading ? (
                <LoaderCircle size={17} className="animate-spin" />
              ) : (
                <Upload size={17} />
              )}
              {uploading ? "Processing" : "Upload invoices"}
            </Button>
          </div>
        </div>
      </section>

      <QueueMetrics counts={counts} />

      {error && (
        <div className="border-b border-danger/25 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger sm:px-6 lg:px-8">
          {error}
        </div>
      )}

      <section className="grid min-h-[640px] lg:grid-cols-[minmax(330px,400px)_minmax(0,1fr)]">
        <InvoiceList
          invoices={visibleInvoices}
          selectedId={selected?.id ?? null}
          loading={loading}
          onSelect={setSelectedId}
        />
        <InvoiceDetailPanel invoice={selected} />
      </section>
    </div>
  );
}
