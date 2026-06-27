import type { Metadata } from "next";
import { Suspense } from "react";

import { AcceptInvitationForm } from "@/components/accept-invitation-form";
import { AuthFlowShell } from "@/components/auth-flow-shell";

export const metadata: Metadata = { title: "Accept invitation" };

export default function InvitePage() {
  return (
    <AuthFlowShell
      eyebrow="Workspace invitation"
      title="Create your SiftEntry access."
      description="Use the invitation prepared by your workspace admin to join the client account with the right role."
    >
      <Suspense fallback={<AuthFormSkeleton />}>
        <AcceptInvitationForm />
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
