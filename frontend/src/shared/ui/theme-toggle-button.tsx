"use client";

import { MoonIcon, SunIcon } from "@/shared/assets/icons";
import { useThemePreference } from "@/shared/lib/theme-provider";

export function ThemeToggleButton() {
  const { theme, toggleTheme } = useThemePreference();
  const isDark = theme === "dark";
  const label = isDark ? "Включить светлую тему" : "Включить темную тему";
  const Icon = isDark ? SunIcon : MoonIcon;

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
      className="flex h-[42px] w-[42px] items-center justify-center rounded-xl border border-[var(--ege-border)] bg-[var(--ege-surface)] text-[var(--ege-muted)] transition-colors hover:bg-[var(--ege-surface-raised)] hover:text-[var(--ege-text)]"
    >
      <Icon aria-hidden />
    </button>
  );
}
