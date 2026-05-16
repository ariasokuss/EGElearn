import assert from "node:assert/strict";
import test from "node:test";

import {
  FOLDER_TABS,
  getFolderTabIndex,
  normalizeFolderTabParam,
  resolveDisplayedFolderTab,
  resolveInitialFolderTab,
} from "./folder-ui-copy.ts";

test("normalizeFolderTabParam only accepts visible ege folder tabs", () => {
  assert.equal(normalizeFolderTabParam("feedback"), "feedback");
  assert.equal(normalizeFolderTabParam("practice"), "practice");
  assert.equal(normalizeFolderTabParam("lessons"), "lessons");
  assert.equal(normalizeFolderTabParam("past-papers"), null);
  assert.equal(normalizeFolderTabParam(""), null);
  assert.equal(normalizeFolderTabParam(null), null);
  assert.equal(normalizeFolderTabParam("feedback-hub"), null);
});

test("folder tabs are russian and hide past papers", () => {
  assert.deepEqual(
    FOLDER_TABS.map((tab) => tab.label),
    ["Подготовка", "Уроки", "Практика", "Ошибки"],
  );
  assert.equal(FOLDER_TABS.some((tab) => tab.param === "past-papers"), false);
});

test("resolveInitialFolderTab restores a saved tab only when the url has no tab", () => {
  assert.equal(resolveInitialFolderTab(null, "feedback"), "feedback");
  assert.equal(resolveInitialFolderTab("practice", "feedback"), "practice");
  assert.equal(resolveInitialFolderTab("past-papers", "feedback"), null);
  assert.equal(resolveInitialFolderTab("", "feedback"), null);
  assert.equal(resolveInitialFolderTab("feedback-hub", "feedback"), null);
  assert.equal(resolveInitialFolderTab(null, "feedback-hub"), null);
});

test("resolveDisplayedFolderTab stops using the saved fallback once roadmap is selected", () => {
  let fallbackTab = resolveInitialFolderTab(null, "feedback");
  assert.equal(resolveDisplayedFolderTab(null, fallbackTab), "feedback");

  fallbackTab = null;
  assert.equal(resolveDisplayedFolderTab(null, fallbackTab), null);
});

test("getFolderTabIndex falls back to roadmap for null or invalid params", () => {
  assert.equal(getFolderTabIndex(null), 0);
  assert.equal(getFolderTabIndex("feedback"), 3);
  assert.equal(getFolderTabIndex("past-papers"), 0);
  assert.equal(getFolderTabIndex("feedback-hub"), 0);
});
