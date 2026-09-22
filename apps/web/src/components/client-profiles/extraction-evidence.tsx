"use client";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import {
  FlaskConical,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const fields = [
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"],
  ["due_date", "Due date"],
  ["supplier_name", "Supplier name"],
  ["supplier_tax_id", "Supplier tax ID"],
  ["currency", "Currency"],
  ["subtotal", "Subtotal"],
  ["tax_total", "Tax total"],
  ["total", "Total"],
] as const;
const lineFields = [
  ["description", "Description"],
  ["quantity", "Quantity"],
  ["uom", "Unit"],
  ["unit_price", "Unit price"],
  ["net_amount", "Net amount"],
  ["tax_amount", "Tax amount"],
  ["total_amount", "Line total"],
  ["hsn_sac", "HSN / SAC"],
] as const;
const numeric = new Set([
  "subtotal",
  "tax_total",
  "total",
  "quantity",
  "unit_price",
  "net_amount",
  "tax_amount",
  "total_amount",
]);
const inputClass =
  "min-h-11 w-full min-w-0 rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent";
type Check = {
  field: string;
  expected: unknown;
  actual: unknown;
  match: boolean;
};
type Score = {
  matches: number;
  checked: number;
  passed: boolean;
  checks: Check[];
  error?: string;
};
type Sample = {
  id: string;
  filename: string;
  split: "learning" | "held_out";
  scope: { supplier_key: string; currency: string };
  expected: Record<string, unknown>;
  review_seconds: number | null;
};
type Lesson = {
  id: string;
  field: string;
  anchor: string;
  relation: string;
  sample_id: string;
};
type Result = {
  samples: {
    sample_id: string;
    filename: string;
    split: string;
    error?: string;
    baseline?: Score;
    ai?: Score;
    elapsed_ms: number;
  }[];
  source_commit: string;
  include_ai: boolean;
};
type View = {
  pending_pdf_deletions: number;
  revision: number;
  samples: Sample[];
  lessons: Lesson[];
  ai_available: boolean;
  job: {
    id: string;
    status: string;
    current: boolean;
    error: string;
    result: Result | Record<string, never>;
  } | null;
};

export function ExtractionEvidence({
  organizationId,
  profileId,
  canEdit,
  dirty,
}: {
  organizationId: string;
  profileId: string;
  canEdit: boolean;
  dirty: boolean;
}) {
  const id = useId();
  const url = `/api/organizations/${organizationId}/client-profiles/${profileId}/extraction-evidence`;
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [lineCount, setLineCount] = useState(1);
  const [includeAi, setIncludeAi] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    kind: "sample" | "lesson";
    id: string;
    label: string;
  } | null>(null);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const response = await fetch(url, { cache: "no-store", signal });
        if (!response.ok)
          throw new Error(
            "Extraction checks could not be loaded. Refresh to try again.",
          );
        const value = (await response.json()) as View;
        if (!signal?.aborted) {
          setView(value);
          setError("");
          if (value.job?.status === "done")
            setNotice((previous) =>
              previous.startsWith("Check queued.")
                ? "Check complete. Expand each sample to inspect field-level results."
                : previous,
            );
        }
      } catch (err) {
        if (!signal?.aborted) setError((err as Error).message);
      }
    },
    [url],
  );
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => void load(controller.signal), 0);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load]);
  const running =
    view?.job?.status === "queued" || view?.job?.status === "running";
  useEffect(() => {
    if (!running) return;
    const controller = new AbortController();
    const timer = setInterval(() => void load(controller.signal), 4000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [load, running]);
  async function mutate(
    path: string,
    method: string,
    body?: FormData | object,
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${url}/${path}`, {
        method,
        headers:
          body instanceof FormData
            ? undefined
            : { "Content-Type": "application/json" },
        body:
          body instanceof FormData
            ? body
            : body
              ? JSON.stringify(body)
              : undefined,
      });
      const value = await response.json();
      if (!response.ok)
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "Check the entered values and try again.",
        );
      await load();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function addSample(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const expected: Record<string, unknown> = {};
    for (const [key] of fields)
      expected[key] = numeric.has(key)
        ? Number(form.get(key))
        : String(form.get(key) ?? "").trim();
    expected.lines = Array.from({ length: lineCount }, (_, index) =>
      Object.fromEntries(
        lineFields.map(([key]) => [
          key,
          numeric.has(key)
            ? Number(form.get(`line-${index}-${key}`))
            : String(form.get(`line-${index}-${key}`) ?? "").trim(),
        ]),
      ),
    );
    const payload = new FormData();
    payload.set("file", form.get("file")!);
    payload.set(
      "confirmation",
      JSON.stringify({
        expected,
        split: form.get("split"),
        confirmed: true,
        retain_for_checks: true,
        review_seconds: form.get("review_seconds")
          ? Number(form.get("review_seconds"))
          : null,
      }),
    );
    if (await mutate("samples", "POST", payload)) {
      setAdding(false);
      setLineCount(1);
      setNotice(
        "Confirmed sample saved. It is not a live invoice and cannot be posted.",
      );
    }
  }
  async function addLesson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    if (
      await mutate("lessons", "POST", {
        sample_id: data.get("sample_id"),
        field: data.get("field"),
        anchor: data.get("anchor"),
        relation: data.get("relation"),
        confirmed: true,
      })
    ) {
      form.reset();
      setNotice(
        "Label hint saved for this supplier, layout, currency and profile only.",
      );
    }
  }
  const disabled = !canEdit || dirty || busy || running;
  const learning = view?.samples.filter((s) => s.split === "learning") ?? [];
  const results = view?.job?.result.samples ?? [];
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="min-w-0 space-y-5 border-t border-line py-5 sm:rounded-2xl sm:border sm:bg-surface sm:p-6"
    >
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div className="min-w-0 flex-1">
          <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent-ink">
            <FlaskConical size={16} /> Measured extraction
          </p>
          <h3 id={`${id}-title`} className="text-lg font-semibold text-ink">
            Extraction quality checks
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-secondary">
            Confirm the answers from the original PDF, then rerun the parser
            against them. Learning samples can supply label hints; held-out
            samples test unseen documents. Neither approves or posts an invoice.
          </p>
        </div>
        <Button
          className="self-end sm:self-start"
          onClick={() => void load()}
          disabled={busy}
          aria-label="Refresh extraction checks"
        >
          <RefreshCw size={16} />
        </Button>
      </div>
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger-soft p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-success">
          {notice}
        </p>
      )}
      {!!view?.pending_pdf_deletions && (
        <p
          role="status"
          className="rounded-xl bg-gold-soft p-3 text-sm text-gold-ink"
        >
          {view.pending_pdf_deletions} PDF removal(s) are awaiting storage
          confirmation. These samples and their hints are already inactive. The
          worker retries removal automatically.
        </p>
      )}
      {dirty && (
        <p className="text-sm text-gold-ink">
          Save your profile changes before editing evidence or running checks.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ["Confirmed PDFs", view?.samples.length ?? 0],
          [
            "Held-out PDFs",
            view?.samples.filter((s) => s.split === "held_out").length ?? 0,
          ],
          ["Scoped label hints", view?.lessons.length ?? 0],
        ].map(([label, count]) => (
          <div
            key={label}
            className="rounded-xl border border-line bg-canvas p-4"
          >
            <p className="text-xs text-ink-secondary">{label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">
              {count}
            </p>
          </div>
        ))}
      </div>
      {!view && !error && (
        <p role="status" className="text-sm text-ink-secondary">
          Loading extraction evidence…
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={disabled} onClick={() => setAdding(!adding)}>
          <Plus size={16} />{" "}
          {adding ? "Close sample form" : "Add confirmed sample"}
        </Button>
        <Button
          variant="primary"
          disabled={disabled || !view?.samples.length}
          onClick={async () => {
            if (await mutate("runs", "POST", { include_ai: includeAi }))
              setNotice(
                "Check queued. The worker will replay the confirmed PDFs; no live invoices are changed.",
              );
          }}
        >
          {busy || running ? (
            <LoaderCircle size={16} className="animate-spin" />
          ) : (
            <FlaskConical size={16} />
          )}{" "}
          {running ? "Check in progress" : "Run extraction checks"}
        </Button>
        {running && (
          <Button
            disabled={!canEdit || busy}
            onClick={async () => {
              if (await mutate("cancel", "POST"))
                setNotice(
                  "Check cancelled. No further samples will start; an in-flight provider request may finish.",
                );
            }}
          >
            Cancel check
          </Button>
        )}
      </div>
      <label className="flex min-h-11 items-start gap-3 text-sm text-ink-secondary">
        <input
          type="checkbox"
          className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
          checked={includeAi}
          disabled={disabled || !view?.ai_available}
          onChange={(e) => setIncludeAi(e.target.checked)}
        />
        Also evaluate AI suggestions. This sends sample text to your configured
        provider and may incur usage charges. Parser-only checks make no
        external AI calls.
      </label>
      {running && (
        <p role="status" className="text-sm text-ink-secondary">
          {view?.job?.status === "queued"
            ? "Waiting for the background worker."
            : "Replaying samples."}{" "}
          Results refresh automatically. You can leave this page.
        </p>
      )}
      {adding && (
        <form
          onSubmit={addSample}
          className="min-w-0 space-y-5 border-y border-line-strong py-4 sm:rounded-xl sm:border sm:bg-canvas sm:p-4"
        >
          <fieldset disabled={disabled} className="min-w-0 space-y-5">
            <legend className="text-base font-semibold text-ink">
              Confirm a benchmark PDF
            </legend>
            <p className="text-sm text-ink-secondary">
              Read the original PDF, not the extracted result. Values are
              immutable after saving. Use a different invoice for held-out
              testing—not another copy of a learning invoice.
            </p>
            <label className="block text-sm text-ink">
              Original PDF
              <input
                name="file"
                type="file"
                accept="application/pdf"
                required
                className={`${inputClass} mt-1`}
              />
            </label>
            <label className="block text-sm text-ink">
              Purpose
              <select
                name="split"
                defaultValue="held_out"
                className={`${inputClass} mt-1`}
              >
                <option value="held_out">
                  Held-out test — never used to create hints
                </option>
                <option value="learning">
                  Learning sample — can supply label hints
                </option>
              </select>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              {fields.map(([key, label]) => (
                <label
                  key={key}
                  className={`block min-w-0 text-sm text-ink ${key === "supplier_name" ? "sm:col-span-2" : ""}`}
                >
                  {label}
                  <input
                    name={key}
                    required={!["due_date", "supplier_tax_id"].includes(key)}
                    type={
                      key.endsWith("date")
                        ? "date"
                        : numeric.has(key)
                          ? "number"
                          : "text"
                    }
                    step="any"
                    maxLength={key === "currency" ? 3 : 500}
                    placeholder={key === "currency" ? "USD" : undefined}
                    pattern={key === "currency" ? "[A-Z]{3}" : undefined}
                    className={`${inputClass} mt-1`}
                  />
                </label>
              ))}
            </div>
            <div className="space-y-4">
              <h4 className="font-semibold text-ink">Confirmed line items</h4>
              {Array.from({ length: lineCount }, (_, index) => (
                <fieldset
                  key={index}
                  className="min-w-0 rounded-xl border border-line p-3"
                >
                  <legend className="px-1 text-sm font-semibold text-ink">
                    Line {index + 1}
                  </legend>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {lineFields.map(([key, label]) => (
                      <label
                        key={key}
                        className={`min-w-0 text-sm text-ink-secondary ${key === "description" ? "sm:col-span-2" : ""}`}
                      >
                        {label}
                        <input
                          name={`line-${index}-${key}`}
                          required={key !== "hsn_sac" && key !== "uom"}
                          type={numeric.has(key) ? "number" : "text"}
                          step="any"
                          maxLength={500}
                          className={`${inputClass} mt-1`}
                        />
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={lineCount >= 100}
                  onClick={() => setLineCount(lineCount + 1)}
                >
                  Add line
                </Button>
                {lineCount > 1 && (
                  <Button onClick={() => setLineCount(lineCount - 1)}>
                    Remove last line
                  </Button>
                )}
              </div>
            </div>
            <label className="block text-sm text-ink">
              Review time in seconds (optional)
              <input
                type="number"
                name="review_seconds"
                min={1}
                max={86400}
                className={`${inputClass} mt-1`}
              />
              <span className="mt-1 block text-xs text-ink-muted">
                Record actual time spent. We do not estimate time saved from
                confidence scores.
              </span>
            </label>
            <label className="flex items-start gap-3 text-sm text-ink-secondary">
              <input
                type="checkbox"
                required
                className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
              />
              I checked every value against the original PDF. Retain this
              benchmark PDF until I delete it; it is separate from the
              live-invoice retention window. Historical check results remain in
              the audit record.
            </label>
            <Button type="submit" variant="primary" disabled={disabled}>
              {busy && <LoaderCircle size={16} className="animate-spin" />}Save
              confirmed sample
            </Button>
          </fieldset>
        </form>
      )}
      <div className="space-y-3">
        {view?.samples.map((sample) => (
          <div
            key={sample.id}
            className="flex flex-col items-start justify-between gap-3 rounded-xl border border-line p-4 sm:flex-row"
          >
            <div className="min-w-0 flex-1">
              <p className="break-words font-semibold text-ink">
                {sample.filename}
              </p>
              <p className="mt-1 break-words text-xs text-ink-secondary">
                {sample.split === "held_out"
                  ? "Held-out test"
                  : "Learning sample"}{" "}
                · {String(sample.expected.supplier_name)} ·{" "}
                {sample.scope.currency}
              </p>
              <p className="mt-1 text-xs text-ink-muted">
                {sample.review_seconds
                  ? `${sample.review_seconds}s reviewer-recorded review time`
                  : "Review time not recorded"}
              </p>
            </div>
            <Button
              disabled={disabled}
              aria-label={`Delete sample ${sample.filename}`}
              onClick={() =>
                setDeleteTarget({
                  kind: "sample",
                  id: sample.id,
                  label: sample.filename,
                })
              }
            >
              <Trash2 size={15} />
            </Button>
          </div>
        ))}
      </div>
      {deleteTarget && (
        <div
          role="alert"
          className="space-y-3 rounded-xl border border-danger/30 bg-danger-soft p-4"
        >
          <p className="break-words text-sm text-ink">
            Delete {deleteTarget.label}?{" "}
            {deleteTarget.kind === "sample"
              ? "The retained PDF and its active hints will be removed. Past check results remain; this document cannot later be relabeled as held-out."
              : "Future extraction will stop using this hint."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="danger"
              disabled={disabled}
              onClick={async () => {
                if (
                  await mutate(
                    `${deleteTarget.kind}/${deleteTarget.id}`,
                    "DELETE",
                  )
                ) {
                  setDeleteTarget(null);
                  setNotice(
                    "Item removed. Earlier qualification is now stale.",
                  );
                }
              }}
            >
              Confirm deletion
            </Button>
            <Button onClick={() => setDeleteTarget(null)}>Keep it</Button>
          </div>
        </div>
      )}
      <details className="rounded-xl border border-line p-4">
        <summary className="cursor-pointer font-semibold text-ink">
          Supplier-specific label hints
        </summary>
        <p className="my-3 text-sm leading-6 text-ink-secondary">
          Example: invoice number appears after “Document No.” Save the label
          and position—not the invoice number itself. Hints cannot choose
          ledgers, approve invoices or change posting rules.
        </p>
        {learning.length ? (
          <form onSubmit={addLesson}>
            <fieldset
              disabled={disabled}
              className="grid min-w-0 gap-3 sm:grid-cols-2"
            >
              <label className="min-w-0 text-sm text-ink sm:col-span-2">
                Learning sample
                <select
                  name="sample_id"
                  required
                  className={`${inputClass} mt-1`}
                >
                  {learning.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.filename}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-ink">
                Field
                <select name="field" className={`${inputClass} mt-1`}>
                  {fields.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-ink">
                Position
                <select name="relation" className={`${inputClass} mt-1`}>
                  <option value="after_label">After label</option>
                  <option value="below_label">Below label</option>
                  <option value="same_row">On same row</option>
                </select>
              </label>
              <label className="text-sm text-ink sm:col-span-2">
                Exact printed label
                <input
                  name="anchor"
                  required
                  minLength={2}
                  maxLength={80}
                  placeholder="Document No."
                  className={`${inputClass} mt-1`}
                />
              </label>
              <label className="flex items-start gap-3 text-sm text-ink-secondary sm:col-span-2">
                <input
                  type="checkbox"
                  required
                  className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
                />
                I verified this label and position in the selected PDF.
              </label>
              <Button type="submit" disabled={disabled}>
                Save label hint
              </Button>
            </fieldset>
          </form>
        ) : (
          <p className="text-sm text-ink-muted">
            Add a learning sample to create a hint. Held-out PDFs are never
            eligible.
          </p>
        )}
        <ul className="mt-4 space-y-3">
          {view?.lessons.map((l) => (
            <li
              key={l.id}
              className="flex items-start justify-between gap-3 rounded-xl bg-canvas p-3"
            >
              <p className="min-w-0 break-words text-sm text-ink">
                {l.field.replaceAll("_", " ")} ·{" "}
                {l.relation.replaceAll("_", " ")} “{l.anchor}”
              </p>
              <Button
                disabled={disabled}
                aria-label={`Remove hint ${l.anchor}`}
                onClick={() =>
                  setDeleteTarget({ kind: "lesson", id: l.id, label: l.anchor })
                }
              >
                <Trash2 size={15} />
              </Button>
            </li>
          ))}
        </ul>
      </details>
      {view?.job && (
        <div className="space-y-3 border-t border-line pt-5">
          <h4 className="font-semibold text-ink">
            Latest check{" "}
            <span className="ml-2 text-xs font-normal text-ink-secondary">
              {view.job.status}
            </span>
          </h4>
          {!view.job.current && (
            <p className="text-sm text-gold-ink">
              Out of date: samples, hints, corrections or extraction
              configuration changed. Run checks again.
            </p>
          )}
          {view.job.error && (
            <p role="alert" className="break-words text-sm text-danger">
              {view.job.error}
            </p>
          )}
          {results.map((row) => (
            <details
              key={row.sample_id}
              className="rounded-xl border border-line p-4"
            >
              <summary className="cursor-pointer break-words text-sm font-semibold text-ink">
                {row.filename} ·{" "}
                {row.split === "held_out" ? "Held-out" : "Learning"} ·{" "}
                {row.error
                  ? "Could not evaluate"
                  : row.baseline?.passed
                    ? "Parser: all checked values match"
                    : "Parser: corrections needed"}
              </summary>
              {row.error && (
                <p className="mt-3 text-sm text-danger">{row.error}</p>
              )}
              {(
                [
                  ["Parser", row.baseline],
                  ["AI suggestions", row.ai],
                ] as const
              ).map(
                ([name, score]) =>
                  score && (
                    <div key={name} className="mt-4">
                      <p className="text-sm font-semibold text-ink">
                        {name}: {score.matches}/{score.checked} values match
                      </p>
                      {score.error && (
                        <p className="text-sm text-danger">
                          Provider returned an error; missing suggestions count
                          as mismatches.
                        </p>
                      )}
                      <ul className="mt-2 space-y-2">
                        {score.checks
                          .filter((c) => !c.match)
                          .map((c) => (
                            <li
                              key={c.field}
                              className="min-w-0 rounded-lg bg-canvas p-3 text-xs"
                            >
                              <p className="break-words font-semibold text-ink">
                                {c.field}
                              </p>
                              <p className="mt-1 break-words text-ink-secondary">
                                Expected: {String(c.expected ?? "—")}
                              </p>
                              <p className="break-words text-danger">
                                Observed: {String(c.actual ?? "missing")}
                              </p>
                            </li>
                          ))}
                      </ul>
                    </div>
                  ),
              )}
              <p className="mt-3 text-xs text-ink-muted">
                Replay duration: {row.elapsed_ms}ms. This is not human review
                time.
              </p>
            </details>
          ))}
          <p className="text-xs leading-5 text-ink-muted">
            Results apply only to the checked fields and documents. Five
            distinct, passing held-out PDFs of the same supplier/layout, a
            current report (under 7 days), and clean per-invoice checks are
            required to bypass AI. This never bypasses human approval. Model
            confidence is not accuracy.
          </p>
        </div>
      )}
    </section>
  );
}
