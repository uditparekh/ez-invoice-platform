"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  useEffect(() => {
    const saved = window.localStorage.getItem("ez-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle(
      "dark",
      saved ? saved === "dark" : prefersDark,
    );
  }, []);

  function toggleTheme() {
    const root = document.documentElement;
    const nextDark = !root.classList.contains("dark");
    root.classList.toggle("dark", nextDark);
    window.localStorage.setItem("ez-theme", nextDark ? "dark" : "light");
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      className="size-9 px-0"
      onClick={toggleTheme}
      aria-label="Toggle color theme"
      title="Toggle color theme"
    >
      <Moon size={16} className="dark:hidden" />
      <Sun size={16} className="hidden dark:block" />
    </Button>
  );
}
