import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
}

const variants: Record<ButtonVariant, string> = {
  primary:
    "border-accent bg-accent text-white shadow-sm shadow-accent/15 hover:border-accent-hover hover:bg-accent-hover",
  secondary:
    "border-line-strong bg-surface text-ink hover:border-accent hover:bg-accent-soft",
  ghost:
    "border-transparent bg-transparent text-ink-secondary hover:bg-surface-subtle hover:text-ink",
  danger: "border-danger bg-danger text-white hover:opacity-90",
};

export function Button({
  className,
  variant = "secondary",
  size = "md",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl border font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-9 px-3 text-xs" : "h-11 px-4 text-sm",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
