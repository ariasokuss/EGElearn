import assert from "node:assert/strict";
import test from "node:test";

import {
  getEffectiveReasoning,
  getReasoningToSend,
  getVisibleReasoningLevels,
} from "./reasoning-options";

test("getVisibleReasoningLevels removes default reasoning placeholder", () => {
  assert.deepEqual(
    getVisibleReasoningLevels(["default", "low", "medium"]),
    ["low", "medium"],
  );
});

test("getReasoningToSend returns null when selected reasoning is not visible", () => {
  assert.equal(getReasoningToSend(["low", "high"], "default"), null);
  assert.equal(getReasoningToSend([], "default"), null);
});

test("getReasoningToSend preserves a selected visible reasoning level", () => {
  assert.equal(getReasoningToSend(["low", "high"], "high"), "high");
});

test("getEffectiveReasoning keeps a visible user-selected reasoning level", () => {
  assert.equal(getEffectiveReasoning(["low", "high"], "high"), "high");
});

test("getEffectiveReasoning falls back to first visible level when user selection is stale", () => {
  assert.equal(getEffectiveReasoning(["low", "medium"], "high"), "low");
});

test("getEffectiveReasoning returns empty string when no visible reasoning exists", () => {
  assert.equal(getEffectiveReasoning([], "high"), "");
  assert.equal(getEffectiveReasoning([], null), "");
});
