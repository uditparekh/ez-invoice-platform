"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { ExtractionEvidence, InvoiceReviewField } from "@/lib/types";
import { cn } from "@/lib/utils";

/** True coordinate highlighting — UI wow, unlocked by parse-time evidence.
 *
 *  Renders the PDF with pdf.js onto canvases and overlays the bounding boxes
 *  located in the document's text layer by the backend (normalized 0..1, so
 *  they scale with any zoom). The active field's box glows; clicking a field
 *  in the review rail scrolls its evidence into view. If the PDF can't be
 *  rendered (or has no located evidence), the caller's fallback is shown —
 *  behavior degrades to exactly what shipped before. */

type PageBox = {
  fieldPath: string;
  evidence: ExtractionEvidence;
};

export function hasLocatedEvidence(fields: InvoiceReviewField[]): boolean {
  return fields.some((field) =>
    field.evidence.some(
      (item) => item.x0 != null && item.y0 != null && item.page != null,
    ),
  );
}

export function PdfEvidenceViewer({
  url,
  fields,
  activeFieldPath,
  fallback,
}: {
  url: string;
  fields: InvoiceReviewField[];
  activeFieldPath: string | null;
  fallback: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [pages, setPages] = useState<
    { pageNumber: number; dataUrl: string; aspect: number }[]
  >([]);
  const [failed, setFailed] = useState(false);

  const boxesByPage = useMemo(() => {
    const map = new Map<number, PageBox[]>();
    for (const field of fields) {
      for (const item of field.evidence) {
        if (
          item.page != null &&
          item.x0 != null &&
          item.y0 != null &&
          item.x1 != null &&
          item.y1 != null
        ) {
          const list = map.get(item.page) ?? [];
          list.push({ fieldPath: field.field_path, evidence: item });
          map.set(item.page, list);
        }
      }
    }
    return map;
  }, [fields]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        const doc = await pdfjs.getDocument({ url }).promise;
        const rendered: { pageNumber: number; dataUrl: string; aspect: number }[] =
          [];
        const pageCount = Math.min(doc.numPages, 12); // guardrail for huge docs
        for (let n = 1; n <= pageCount; n += 1) {
          const page = await doc.getPage(n);
          const viewport = page.getViewport({ scale: 1.6 });
          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const context = canvas.getContext("2d");
          if (!context) throw new Error("canvas 2d unavailable");
          await page.render({ canvasContext: context, viewport, canvas }).promise;
          rendered.push({
            pageNumber: n,
            dataUrl: canvas.toDataURL("image/png"),
            aspect: viewport.height / viewport.width,
          });
        }
        if (!cancelled) setPages(rendered);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  // Scroll the active field's evidence page into view.
  useEffect(() => {
    if (!activeFieldPath) return;
    for (const [pageNumber, boxes] of boxesByPage.entries()) {
      if (boxes.some((box) => box.fieldPath === activeFieldPath)) {
        pageRefs.current
          .get(pageNumber)
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        return;
      }
    }
  }, [activeFieldPath, boxesByPage]);

  if (failed) return <>{fallback}</>;
  if (!pages.length)
    return (
      <div className="grid h-[620px] place-items-center rounded-xl border border-line bg-surface">
        <p className="text-sm font-bold text-ink-muted">Rendering document…</p>
      </div>
    );

  return (
    <div
      ref={containerRef}
      className="h-[620px] space-y-3 overflow-y-auto rounded-xl border border-line bg-surface-subtle p-3"
    >
      {pages.map(({ pageNumber, dataUrl, aspect }) => (
        <div
          key={pageNumber}
          ref={(node) => {
            if (node) pageRefs.current.set(pageNumber, node);
          }}
          className="relative w-full overflow-hidden rounded-lg border border-line bg-white shadow-card"
          style={{ aspectRatio: `${1 / aspect}` }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={dataUrl}
            alt={`Invoice page ${pageNumber}`}
            className="absolute inset-0 h-full w-full"
          />
          {(boxesByPage.get(pageNumber) ?? []).map(({ fieldPath, evidence }) => {
            const active = fieldPath === activeFieldPath;
            return (
              <span
                key={`${fieldPath}-${evidence.field}`}
                aria-hidden
                className={cn(
                  "absolute rounded-[3px] transition-all duration-300",
                  active
                    ? "z-10 animate-pulse border-2 border-cyan bg-cyan/25 shadow-[0_0_0_4px_rgba(34,211,238,0.25)]"
                    : "border border-accent/50 bg-accent/10",
                )}
                style={{
                  left: `${(evidence.x0 ?? 0) * 100}%`,
                  top: `${(evidence.y0 ?? 0) * 100}%`,
                  width: `${((evidence.x1 ?? 0) - (evidence.x0 ?? 0)) * 100}%`,
                  height: `${((evidence.y1 ?? 0) - (evidence.y0 ?? 0)) * 100}%`,
                  padding: "3px",
                }}
              />
            );
          })}
          <span className="absolute bottom-2 right-2 rounded-md bg-ink/70 px-2 py-0.5 text-[10px] font-black text-white">
            p.{pageNumber}
          </span>
        </div>
      ))}
    </div>
  );
}
