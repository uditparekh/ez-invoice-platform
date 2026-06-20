"use client";

import { ArrowRight, LoaderCircle, LockKeyhole, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(formData: FormData) {
    setSubmitting(true);
    setError("");
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
        setError(payload.detail ?? "Unable to sign in.");
        return;
      }
      router.replace("/app/invoices");
      router.refresh();
    } catch {
      setError("The EZ-Invoice API is unavailable. Start FastAPI and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form action={submit} className="mt-8 space-y-5">
      <label className="block">
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Work email
        </span>
        <span className="flex h-12 items-center gap-3 rounded-[7px] border border-line-strong bg-surface px-3.5 focus-within:border-accent">
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
        <span className="mb-2 block text-xs font-bold text-ink-secondary">
          Password
        </span>
        <span className="flex h-12 items-center gap-3 rounded-[7px] border border-line-strong bg-surface px-3.5 focus-within:border-accent">
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
      {error && (
        <p
          role="alert"
          className="rounded-[7px] border border-danger/25 bg-danger-soft px-3.5 py-3 text-sm font-medium text-danger"
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
        {submitting ? "Signing in" : "Continue"}
      </Button>
    </form>
  );
}
