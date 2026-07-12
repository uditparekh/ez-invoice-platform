"use client";

import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  LoaderCircle,
  LockKeyhole,
  Mail,
  UserRound,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

export function AcceptInvitationForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [fullName, setFullName] = useState("");
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
      const response = await fetch("/api/auth/invitations/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          full_name: fullName,
          password,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json()) as ApiErrorPayload;
        setError(apiErrorMessage(payload, "Invitation could not be accepted."));
        return;
      }
      router.replace("/app");
      router.refresh();
    } catch {
      setError("The SiftEntry API is unavailable. Start FastAPI and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <FieldShell label="Invite token" icon={<Mail size={17} />}>
        <input
          required
          value={token}
          onChange={(event) => setToken(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none"
          placeholder="Paste invite token"
        />
      </FieldShell>
      <FieldShell label="Full name" icon={<UserRound size={17} />}>
        <input
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none"
          placeholder="Your name"
        />
      </FieldShell>
      <FieldShell label="Password" icon={<LockKeyhole size={17} />}>
        <input
          required
          minLength={12}
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none"
        />
      </FieldShell>
      <FieldShell label="Confirm password" icon={<LockKeyhole size={17} />}>
        <input
          required
          minLength={12}
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none"
        />
      </FieldShell>
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
        {submitting ? "Creating workspace access" : "Accept invitation"}
      </Button>
    </form>
  );
}

function FieldShell({
  label,
  icon,
  children,
}: {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold text-ink-secondary">
        {label}
      </span>
      <span className="flex h-12 items-center gap-3 rounded-xl border border-line-strong bg-surface px-3.5 text-ink-muted focus-within:border-accent">
        {icon}
        {children}
      </span>
    </label>
  );
}
