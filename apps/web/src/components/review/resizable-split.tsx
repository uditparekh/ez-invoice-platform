"use client";

import { Children, useCallback, useRef, useState } from "react";
import type {
  CSSProperties,
  KeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from "react";

/**
 * Two-pane resizable split (UI Spec §6/§8).
 * - Drag the slim handle to resize · double-click to reset · position remembered per user.
 * - Keyboard accessible: focus the handle, Arrow keys nudge by 2%.
 * - Below the xl breakpoint the panes stack vertically and the handle hides.
 * Expects exactly two children: [leftPane, rightPane].
 */
export function ResizableSplit({
  children,
  storageKey,
  defaultLeftPct = 38,
  minLeftPct = 24,
  maxLeftPct = 58,
}: {
  children: ReactNode;
  storageKey: string;
  defaultLeftPct?: number;
  minLeftPct?: number;
  maxLeftPct?: number;
}) {
  const [leftPct, setLeftPct] = useState(() => {
    if (typeof window === "undefined") return defaultLeftPct;
    const stored = window.localStorage.getItem(storageKey);
    const parsed = stored ? Number(stored) : NaN;
    return Number.isFinite(parsed)
      ? Math.min(maxLeftPct, Math.max(minLeftPct, parsed))
      : defaultLeftPct;
  });
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftChild, rightChild] = Children.toArray(children);

  const clamp = useCallback(
    (pct: number) => Math.min(maxLeftPct, Math.max(minLeftPct, pct)),
    [minLeftPct, maxLeftPct],
  );

  const persist = useCallback(
    (pct: number) => {
      window.localStorage.setItem(storageKey, pct.toFixed(1));
    },
    [storageKey],
  );

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    setLeftPct(clamp(((event.clientX - rect.left) / rect.width) * 100));
  }

  function handlePointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(false);
    setLeftPct((current) => {
      persist(current);
      return current;
    });
  }

  function handleDoubleClick() {
    setLeftPct(defaultLeftPct);
    persist(defaultLeftPct);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    setLeftPct((current) => {
      const next = clamp(current + (event.key === "ArrowLeft" ? -2 : 2));
      persist(next);
      return next;
    });
  }

  return (
    <div
      ref={containerRef}
      className={`flex flex-col gap-4 xl:flex-row xl:items-stretch xl:gap-0 ${
        dragging ? "select-none xl:cursor-col-resize" : ""
      }`}
      style={{ "--split": `${leftPct}%` } as CSSProperties}
    >
      <div className="min-w-0 xl:w-[var(--split)] xl:shrink-0">{leftChild}</div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panes — drag, arrow keys, or double-click to reset"
        tabIndex={0}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onDoubleClick={handleDoubleClick}
        onKeyDown={handleKeyDown}
        className="group hidden shrink-0 cursor-col-resize items-center justify-center outline-none xl:flex xl:w-4 focus-visible:bg-accent-soft/40"
        title="Drag to resize · double-click to reset"
      >
        <span
          className={`h-14 w-1.5 rounded-full transition-colors ${
            dragging
              ? "bg-accent"
              : "bg-line-strong group-hover:bg-accent group-focus-visible:bg-accent"
          }`}
        />
      </div>
      <div className="min-w-0 flex-1">{rightChild}</div>
    </div>
  );
}
