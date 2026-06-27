import type { ReactNode } from "react";
import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";

export function AuthFlowShell({
  eyebrow,
  title,
  description,
  children,
  backHref = "/login",
  backLabel = "Back to sign in",
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  backHref?: string;
  backLabel?: string;
}) {
  return (
    <main className="min-h-screen bg-canvas px-5 py-6 text-ink sm:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-6xl flex-col">
        <header className="flex items-center justify-between gap-4">
          <BrandMark size="lg" />
          <ThemeToggle />
        </header>
        <section className="grid flex-1 items-center gap-10 py-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(420px,500px)] lg:py-16">
          <div className="max-w-xl">
            <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-accent dark:text-cyan">
              {eyebrow}
            </p>
            <h1 className="mt-4 text-4xl font-black leading-tight text-ink sm:text-5xl">
              {title}
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-ink-secondary sm:text-lg">
              {description}
            </p>
            <Link
              href={backHref}
              className="mt-8 inline-flex text-sm font-extrabold text-accent transition hover:text-cyan"
            >
              {backLabel}
            </Link>
          </div>
          <div className="rounded-[28px] border border-line bg-surface p-5 shadow-[0_24px_80px_rgba(8,17,31,0.10)] sm:p-7 dark:shadow-[0_24px_80px_rgba(0,0,0,0.35)]">
            {children}
          </div>
        </section>
      </div>
    </main>
  );
}
