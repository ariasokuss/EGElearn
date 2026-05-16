export type ThemePreference = "light" | "dark";

export const THEME_STORAGE_KEY = "novalearn:theme";

export function normalizeThemePreference(
  value: string | null | undefined,
): ThemePreference | null {
  return value === "light" || value === "dark" ? value : null;
}

export function resolveThemePreference(
  storedTheme: string | null | undefined,
  systemTheme: ThemePreference,
): ThemePreference {
  return normalizeThemePreference(storedTheme) ?? systemTheme;
}

export function getNextThemePreference(
  theme: ThemePreference | null | undefined,
): ThemePreference {
  return theme === "dark" ? "light" : "dark";
}

export function getSystemTheme(
  win: Pick<Window, "matchMedia"> | undefined,
): ThemePreference {
  if (!win?.matchMedia) return "light";
  return win.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyThemePreference(
  root: Pick<HTMLElement, "dataset">,
  theme: ThemePreference,
) {
  root.dataset.theme = theme;
}
