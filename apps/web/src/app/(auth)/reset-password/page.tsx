import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthFlowShell } from "@/components/auth-flow-shell";
import { PasswordResetConfirmForm } from "@/components/password-reset-confirm-form";

export const metadata: Metadata = { title: "Choose new password" };

export default function ResetPasswordPage() {
  return (
    <AuthFlowShell
      eyebrow="Secure reset"
      title="Choose a new password."
      description="Reset links can only be used once. After a successful reset, old sessions are revoked automatically."
    >
      <Suspense fallback={<AuthFormSkeleton />}>
        <PasswordResetConfirmForm />
      </Suspense>
    </AuthFlowShell>
  );
}

function AuthFormSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-12 rounded-xl bg-surface-subtle" />
      <div className="h-12 rounded-xl bg-surface-subtle" />
      <div className="h-12 rounded-xl bg-surface-subtle" />
      <div className="h-11 rounded-xl bg-accent-soft" />
    </div>
  );
}
