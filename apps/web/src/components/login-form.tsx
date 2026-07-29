"use client";

import {
  ArrowRight,
  Eye,
  LoaderCircle,
  LockKeyhole,
  Mail,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

export function LoginForm() {
  const router = useRouter();
  const requestInFlight = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [openingDemo, setOpeningDemo] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(() => {
    if (typeof window === "undefined") return "";
    const reason = new URLSearchParams(window.location.search).get("reason");
    return reason === "inactive"
      ? "You were signed out after inactivity on this device."
      : "";
  });

  function releaseRequest() {
    requestInFlight.current = false;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (requestInFlight.current) return;

    requestInFlight.current = true;
    const formData = new FormData(event.currentTarget);
    setSubmitting(true);
    setError("");
    setNotice("");

    // Let React commit the busy state before authentication begins. Function
    // form actions can otherwise defer this paint until after the request,
    // making a responsive login feel frozen on slower connections.
    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password"),
        }),
      });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        setError(apiErrorMessage(payload, "Unable to sign in."));
        releaseRequest();
        setSubmitting(false);
        return;
      }
      // The middleware appends ?next=<path> when redirecting a signed-out
      // visitor to /login. Only follow internal app paths — never external
      // URLs or protocol-relative //host values.
      const requested = new URLSearchParams(window.location.search).get("next");
      const destination =
        requested && requested.startsWith("/app") && !requested.startsWith("//")
          ? requested
          : "/app";
      router.replace(destination);
      router.refresh();
      // Deliberately keep `submitting` true on success: this page unmounts
      // when navigation completes, and resetting the button early leaves the
      // user staring at an idle form while the app loads — the exact "laggy"
      // feeling this state exists to prevent.
    } catch {
      setError("The SiftEntry API is unavailable. Start FastAPI and try again.");
      releaseRequest();
      setSubmitting(false);
    }
  }

  async function openDemo() {
    if (requestInFlight.current) return;

    requestInFlight.current = true;
    setOpeningDemo(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/auth/demo", { method: "POST" });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        setError(apiErrorMessage(payload, "Unable to open the demo workspace."));
        releaseRequest();
        setOpeningDemo(false);
        return;
      }
      router.replace("/app");
      router.refresh();
    } catch {
      setError("The SiftEntry demo is temporarily unavailable.");
      releaseRequest();
      setOpeningDemo(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-busy={submitting || openingDemo}
      className="mt-8 space-y-5"
    >
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Work email
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <Mail size={17} className="shrink-0 text-ink-muted" />
          <input
            name="email"
            type="email"
            autoComplete="email"
            required
            placeholder="name@company.com"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
          />
        </span>
      </label>
      <label className="block">
        <span className="mb-2 flex items-center justify-between gap-3 text-xs font-bold text-ink-secondary">
          <span>Password</span>
          <Link
            href="/forgot-password"
            className="text-accent transition hover:text-cyan"
          >
            Forgot password?
          </Link>
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <LockKeyhole size={17} className="shrink-0 text-ink-muted" />
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none"
          />
        </span>
      </label>
      {notice && (
        <p
          role="status"
          className="rounded-xl border border-accent/20 bg-accent-soft px-3.5 py-3 text-sm font-semibold text-accent"
        >
          {notice}
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3 text-sm font-semibold text-danger"
        >
          {error}
        </p>
      )}
      <Button
        type="submit"
        variant="primary"
        className="w-full aria-disabled:cursor-wait aria-disabled:opacity-80"
        aria-busy={submitting}
        aria-disabled={submitting || openingDemo}
      >
        {submitting ? (
          <LoaderCircle
            size={17}
            className="animate-spin"
            aria-hidden="true"
          />
        ) : (
          <ArrowRight size={17} aria-hidden="true" />
        )}
        {submitting ? "Signing in…" : "Continue"}
      </Button>
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {submitting ? "Signing in and opening your workspace." : ""}
      </span>
      <div className="flex items-center gap-3 text-[11px] font-bold uppercase tracking-[0.12em] text-ink-muted">
        <span className="h-px flex-1 bg-line" />
        Or
        <span className="h-px flex-1 bg-line" />
      </div>
      <Button
        type="button"
        variant="secondary"
        className="w-full aria-disabled:cursor-wait aria-disabled:opacity-80"
        aria-disabled={submitting || openingDemo}
        onClick={openDemo}
      >
        {openingDemo ? (
          <LoaderCircle size={17} className="animate-spin" />
        ) : (
          <Eye size={17} />
        )}
        {openingDemo ? "Preparing demo" : "Explore demo workspace"}
      </Button>
      <p className="-mt-2 text-center text-xs leading-5 text-ink-muted">
        Read-only access · two synthetic processed invoices · no signup
      </p>
    </form>
  );
}
