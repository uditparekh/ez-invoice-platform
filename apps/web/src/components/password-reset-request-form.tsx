"use client";

import type { FormEvent } from "react";
import { ArrowRight, LoaderCircle, Mail } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ApiErrorPayload, PasswordResetResponse } from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

export function PasswordResetRequestForm() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState<PasswordResetResponse | null>(null);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setResponse(null);
    try {
      const request = await fetch("/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const payload = (await request.json()) as
        | PasswordResetResponse
        | ApiErrorPayload;
      if (!request.ok) {
        setError(
          "detail" in payload
            ? apiErrorMessage(payload, "Reset could not be prepared.")
            : "Reset could not be prepared.",
        );
        return;
      }
      setResponse(payload as PasswordResetResponse);
    } catch {
      setError("The SiftEntry API is unavailable. Start FastAPI and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Work email
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <Mail size={17} className="shrink-0 text-ink-muted" />
          <input
            required
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
          />
        </span>
      </label>
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3 text-sm font-semibold text-danger"
        >
          {error}
        </p>
      )}
      {response && (
        <div className="rounded-xl border border-success/25 bg-success/10 px-3.5 py-3 text-sm font-semibold text-success">
          <p>{response.message}</p>
          {response.reset_token && (
            <Link
              className="mt-2 inline-flex break-all text-accent transition hover:text-cyan"
              href={`/reset-password?token=${encodeURIComponent(response.reset_token)}`}
            >
              Open local reset link
            </Link>
          )}
          {!response.reset_token && (
            <p className="mt-2 text-xs font-bold text-success">
              Check your inbox for the reset link.
            </p>
          )}
        </div>
      )}
      <Button
        type="submit"
        variant="primary"
        className="w-full"
        disabled={submitting}
      >
        {submitting ? (
          <LoaderCircle size={17} className="animate-spin" />
        ) : (
          <ArrowRight size={17} />
        )}
        {submitting ? "Preparing reset" : "Send reset link"}
      </Button>
    </form>
  );
}
