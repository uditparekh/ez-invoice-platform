"use client";

import type { FormEvent } from "react";
import { ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

export function PasswordResetConfirmForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          new_password: password,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        setError(apiErrorMessage(payload, "Password could not be reset."));
        return;
      }
      router.replace("/app");
      router.refresh();
    } catch {
      setError(
        "The SiftEntry API is unavailable. Start FastAPI and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Reset token
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <LockKeyhole size={17} className="shrink-0 text-ink-muted" />
          <input
            required
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
            placeholder="Paste reset token"
          />
        </span>
      </label>
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          New password
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <LockKeyhole size={17} className="shrink-0 text-ink-muted" />
          <input
            required
            minLength={12}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none"
          />
        </span>
      </label>
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Confirm password
        </span>
        <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <LockKeyhole size={17} className="shrink-0 text-ink-muted" />
          <input
            required
            minLength={12}
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none"
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
        {submitting ? "Resetting password" : "Reset password"}
      </Button>
    </form>
  );
}
