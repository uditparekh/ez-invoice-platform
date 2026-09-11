"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type ThemeMode = "light" | "dark";

export function ThemeToggle() {
  const [theme, setThemeState] = useState<ThemeMode>("light");

  useEffect(() => {
    const saved =
      window.localStorage.getItem("siftentry-theme") ??
      window.localStorage.getItem("ez-theme");
    const prefersDark = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;
    const nextTheme: ThemeMode = saved
      ? saved === "dark"
        ? "dark"
        : "light"
      : prefersDark
        ? "dark"
        : "light";
    setTheme(nextTheme);
  }, []);

  function setTheme(nextTheme: ThemeMode) {
    setThemeState(nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
    window.localStorage.setItem("siftentry-theme", nextTheme);
  }

  return (
    <div
      className="inline-flex h-9 shrink-0 items-center rounded-full border border-line bg-surface-subtle p-1 shadow-sm shadow-black/[0.03] dark:shadow-black/20"
      aria-label="Color theme"
      role="group"
    >
      <ThemeButton
        active={theme === "light"}
        icon={<Sun size={14} />}
        label="Light"
        onClick={() => setTheme("light")}
      />
      <ThemeButton
        active={theme === "dark"}
        icon={<Moon size={14} />}
        label="Dark"
        onClick={() => setTheme("dark")}
      />
    </div>
  );
}

function ThemeButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 min-w-8 items-center justify-center gap-1.5 rounded-full px-2.5 text-xs font-semibold transition-colors",
        active
          ? "bg-accent text-white shadow-sm"
          : "text-ink-muted hover:bg-surface hover:text-ink",
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
