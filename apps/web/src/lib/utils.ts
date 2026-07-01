import { type ClassValue, clsx } from "clsx";

import type { ApiErrorPayload } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCurrency(value: number, currency = "USD") {
  const currencyCode = (currency || "USD").trim().toUpperCase();
  const locale = currencyCode === "INR" ? "en-IN" : "en-US";

  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currencyCode,
    maximumFractionDigits: 2,
  }).format(value || 0);
}

export function formatDate(value?: string) {
  if (!value) return "Not available";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const parsed = dateOnly
    ? new Date(
        Number(dateOnly[1]),
        Number(dateOnly[2]) - 1,
        Number(dateOnly[3]),
      )
    : new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

export function apiErrorMessage(
  payload: ApiErrorPayload | unknown,
  fallback: string,
) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return fallback;
  }
  const detail = (payload as ApiErrorPayload).detail;
  if (typeof detail === "string") return detail || fallback;
  if (!detail || typeof detail !== "object") return fallback;

  const message =
    "message" in detail && typeof detail.message === "string"
      ? detail.message
      : "";
  const issues =
    "issues" in detail && Array.isArray(detail.issues)
      ? detail.issues
          .map((issue) =>
            issue && typeof issue === "object" && "message" in issue
              ? String(issue.message || "")
              : "",
          )
          .filter(Boolean)
          .slice(0, 3)
          .join(" ")
      : "";
  return [message, issues].filter(Boolean).join(" ") || fallback;
}
