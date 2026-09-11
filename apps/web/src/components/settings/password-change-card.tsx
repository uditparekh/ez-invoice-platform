"use client";

import { KeyRound, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { ContentCard } from "@/components/dashboard/content-card";
import { Button } from "@/components/ui/button";
import type { ApiErrorPayload } from "@/lib/types";
import { apiErrorMessage } from "@/lib/utils";

export function PasswordChangeCard() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const validation = useMemo(() => {
    if (!newPassword) return "";
    if (newPassword.length < 12) return "Use at least 12 characters.";
    if (confirmPassword && newPassword !== confirmPassword) {
      return "New passwords do not match.";
    }
    return "";
  }, [confirmPassword, newPassword]);

  async function updatePassword() {
    if (!currentPassword || !newPassword || validation) return;
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      if (!response.ok) {
        const payload = (await response
          .json()
          .catch(() => ({}))) as ApiErrorPayload;
        throw new Error(
          apiErrorMessage(payload, "Password could not be updated."),
        );
      }
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password updated.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Password could not be updated.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <ContentCard
      title="Password"
      subtitle="Update the password used for this SiftEntry workspace login."
      action={
        <span className="inline-flex h-9 items-center gap-2 rounded-full border border-success/25 bg-success/10 px-3 text-xs font-semibold text-success">
          <ShieldCheck size={14} />
          Protected
        </span>
      }
    >
      <div className="grid gap-4">
        <PasswordField
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
        />
        <PasswordField
          label="New password"
          value={newPassword}
          onChange={setNewPassword}
        />
        <PasswordField
          label="Confirm"
          value={confirmPassword}
          onChange={setConfirmPassword}
        />
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-h-6">
          {validation && (
            <p className="text-sm font-semibold text-gold">{validation}</p>
          )}
          {message && (
            <p className="text-sm font-semibold text-success">{message}</p>
          )}
          {error && (
            <p className="text-sm font-semibold text-danger">{error}</p>
          )}
        </div>
        <Button
          variant="primary"
          onClick={updatePassword}
          disabled={
            saving ||
            !currentPassword ||
            !newPassword ||
            !confirmPassword ||
            !!validation
          }
        >
          <KeyRound size={15} />
          {saving ? "Updating..." : "Update password"}
        </Button>
      </div>
    </ContentCard>
  );
}

function PasswordField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold uppercase text-ink-muted">
        {label}
      </span>
      <input
        className="mt-2 h-11 w-full rounded-xl border border-line bg-canvas px-3 text-sm font-semibold text-ink outline-none transition focus:border-accent"
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="new-password"
      />
    </label>
  );
}
