import type { Metadata } from "next";

import { AuthFlowShell } from "@/components/auth-flow-shell";
import { PasswordResetRequestForm } from "@/components/password-reset-request-form";

export const metadata: Metadata = { title: "Reset password" };

export default function ForgotPasswordPage() {
  return (
    <AuthFlowShell
      eyebrow="Account recovery"
      title="Reset your workspace password."
      description="Enter your work email. If the account exists, SiftEntry prepares a reset link for that user."
    >
      <PasswordResetRequestForm />
    </AuthFlowShell>
  );
}
