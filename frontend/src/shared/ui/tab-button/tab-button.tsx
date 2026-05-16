"use client"

import { ButtonHTMLAttributes } from "react";

interface TabButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isActive?: boolean;
}

export function TabButton({
  isActive = false,
  className = "",
  style,
  ...props
}: TabButtonProps) {
  return (
    <button
      className={`inline-flex cursor-pointer items-center justify-center rounded-full px-2 py-1 nova-text-label-small transition-all duration-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset border ${
        isActive
          ? "bg-[var(--ege-surface)] text-[var(--ege-text)] border-[var(--ege-border)]"
          : "border-transparent text-[var(--ege-muted)] hover:bg-[var(--ege-surface-raised)] hover:text-[var(--ege-text)] hover:nova-shadow-sm"
      } ${className}`}
      style={style}
      {...props}
    />
  );
}
