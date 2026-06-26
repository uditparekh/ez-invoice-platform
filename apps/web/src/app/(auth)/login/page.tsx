import type { Metadata } from "next";
import { CheckCircle2 } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { LoginForm } from "@/components/login-form";
import { ThemeToggle } from "@/components/theme-toggle";

export const metadata: Metadata = { title: "Sign in" };

const assurances = [
  "Organization-isolated invoice data",
  "Role-based review and approval",
  "TallyPrime, QuickBooks, and Zoho Books ready",
];

export default function LoginPage() {
  return (
    <main className="grid min-h-screen bg-canvas lg:grid-cols-[minmax(0,1fr)_minmax(460px,0.72fr)]">
      <section className="hidden border-r border-line bg-accent-soft px-12 py-10 lg:flex lg:flex-col dark:bg-surface">
        <BrandMark size="lg" />
        <div className="my-auto max-w-xl py-16">
          <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-accent dark:text-cyan">
            Invoice-to-ledger automation
          </p>
          <h1 className="mt-5 text-5xl font-black leading-[1.08] text-ink">
            Move every supplier invoice from inbox to ledger.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-ink-secondary">
            Capture PDFs, validate fields and taxes, approve exceptions, and
            post clean entries to the accounting system your client already
            uses.
          </p>
          <ul className="mt-10 space-y-4">
            {assurances.map((assurance) => (
              <li
                key={assurance}
                className="flex items-center gap-3 text-sm font-semibold text-ink-secondary"
              >
                <CheckCircle2 size={18} className="text-cyan" />
                {assurance}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-ink-muted">
          Secure multi-tenant SaaS foundation · API v0.2
        </p>
      </section>

      <section className="flex min-h-screen flex-col bg-surface px-6 py-6 sm:px-10 lg:px-16">
        <div className="flex items-center justify-between lg:justify-end">
          <div className="lg:hidden">
            <BrandMark size="lg" />
          </div>
          <ThemeToggle />
        </div>
        <div className="my-auto w-full max-w-[430px] self-center py-12">
          <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-accent dark:text-cyan">
            Welcome back
          </p>
          <h2 className="mt-3 text-3xl font-black text-ink">
            Sign in to SiftEntry
          </h2>
          <p className="mt-3 text-sm leading-6 text-ink-secondary">
            Use the account created for your organization workspace.
          </p>
          <LoginForm />
        </div>
      </section>
    </main>
  );
}
