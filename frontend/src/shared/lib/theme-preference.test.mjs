import assert from "node:assert/strict";
import test from "node:test";

import {
  getNextThemePreference,
  normalizeThemePreference,
  resolveThemePreference,
  THEME_STORAGE_KEY,
} from "./theme-preference.ts";

test("theme storage key is stable", () => {
  assert.equal(THEME_STORAGE_KEY, "novalearn:theme");
});

test("normalizeThemePreference accepts only supported themes", () => {
  assert.equal(normalizeThemePreference("light"), "light");
  assert.equal(normalizeThemePreference("dark"), "dark");
  assert.equal(normalizeThemePreference("system"), null);
  assert.equal(normalizeThemePreference(null), null);
});

test("resolveThemePreference prefers saved theme over system theme", () => {
  assert.equal(resolveThemePreference("dark", "light"), "dark");
  assert.equal(resolveThemePreference("light", "dark"), "light");
  assert.equal(resolveThemePreference(null, "dark"), "dark");
});

test("getNextThemePreference toggles light and dark", () => {
  assert.equal(getNextThemePreference("light"), "dark");
  assert.equal(getNextThemePreference("dark"), "light");
  assert.equal(getNextThemePreference(null), "dark");
});
