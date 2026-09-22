"use client";

import { useSyncExternalStore } from "react";

export type ThemePreference = "light" | "dark" | "system";
const key = "siftentry-theme";
const eventName = "siftentry:theme";
let volatilePreference: ThemePreference | undefined;

function preference(): ThemePreference {
  if (volatilePreference) return volatilePreference;
  try {
    const saved = localStorage.getItem(key) ?? localStorage.getItem("ez-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

function resolved(value: ThemePreference) {
  return value === "system"
    ? matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
    : value;
}

function apply() {
  const theme = resolved(preference());
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

export function setTheme(value: ThemePreference) {
  volatilePreference = value;
  try {
    localStorage.setItem(key, value);
    volatilePreference = undefined;
  } catch {
    /* Appearance remains usable when storage is unavailable. */
  }
  apply();
  window.dispatchEvent(new Event(eventName));
}

function subscribe(notify: () => void) {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const update = () => {
    apply();
    notify();
  };
  const storage = (event: StorageEvent) => {
    if (event.key === key || event.key === "ez-theme" || event.key === null) {
      volatilePreference = undefined;
      update();
    }
  };
  window.addEventListener(eventName, update);
  window.addEventListener("storage", storage);
  media.addEventListener("change", update);
  apply();
  return () => {
    window.removeEventListener(eventName, update);
    window.removeEventListener("storage", storage);
    media.removeEventListener("change", update);
  };
}

export function useTheme() {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => `${preference()}:${resolved(preference())}`,
    () => "system:light",
  );
  const [theme, resolvedTheme] = snapshot.split(":");
  return { theme: theme as ThemePreference, resolvedTheme, setTheme };
}
