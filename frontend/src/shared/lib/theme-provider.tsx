"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  applyThemePreference,
  getNextThemePreference,
  getSystemTheme,
  resolveThemePreference,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./theme-preference";

type ThemeContextValue = {
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readInitialTheme(): ThemePreference {
  if (typeof window === "undefined") return "light";
  return resolveThemePreference(
    window.localStorage.getItem(THEME_STORAGE_KEY),
    getSystemTheme(window),
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(readInitialTheme);

  const setTheme = useCallback((nextTheme: ThemePreference) => {
    setThemeState(nextTheme);
    if (typeof window === "undefined") return;
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    applyThemePreference(document.documentElement, nextTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(getNextThemePreference(theme));
  }, [theme, setTheme]);

  useEffect(() => {
    applyThemePreference(document.documentElement, theme);
  }, [theme]);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemePreference(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useThemePreference must be used within ThemeProvider");
  return value;
}
