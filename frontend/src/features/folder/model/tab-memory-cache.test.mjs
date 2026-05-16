import assert from "node:assert/strict";
import test from "node:test";

import {
  invalidateFeedbackCache,
  readCachedFeedback,
  writeCachedFeedback,
} from "./feedback-cache.ts";
import {
  readCachedTestLists,
  writeCachedTestSessions,
  writeCachedTestTemplates,
} from "../../practice-questions/model/test-list-cache.ts";

test("feedback cache stores data per folder", () => {
  assert.equal(readCachedFeedback("folder-a"), null);

  const payload = {
    summary: { see: 1, review: 2, complete: 3, total: 6 },
    seeNotes: [{ id: "see-1" }],
    reviewNotes: [{ id: "review-1" }],
    coveredNotes: [{ id: "covered-1" }],
  };

  writeCachedFeedback("folder-a", payload);

  assert.deepEqual(readCachedFeedback("folder-a"), payload);
  assert.equal(readCachedFeedback("folder-b"), null);
});

test("invalidateFeedbackCache removes only the given folder", () => {
  writeCachedFeedback("folder-a", {
    summary: { see: 1, review: 0, complete: 0, total: 1 },
    seeNotes: [{ id: "n1" }],
    reviewNotes: [],
    coveredNotes: [],
  });
  writeCachedFeedback("folder-b", {
    summary: { see: 0, review: 1, complete: 0, total: 1 },
    seeNotes: [],
    reviewNotes: [{ id: "n2" }],
    coveredNotes: [],
  });
  invalidateFeedbackCache("folder-a");
  assert.equal(readCachedFeedback("folder-a"), null);
  assert.notEqual(readCachedFeedback("folder-b"), null);
});

test("test list cache stores sessions and templates independently per folder and type", () => {
  assert.equal(readCachedTestLists("folder-a", "past_paper"), null);

  writeCachedTestSessions("folder-a", "past_paper", [{ id: "session-1" }]);
  assert.deepEqual(readCachedTestLists("folder-a", "past_paper"), {
    sessions: [{ id: "session-1" }],
  });

  writeCachedTestTemplates("folder-a", "past_paper", [{ id: "template-1" }]);
  assert.deepEqual(readCachedTestLists("folder-a", "past_paper"), {
    sessions: [{ id: "session-1" }],
    templates: [{ id: "template-1" }],
  });

  writeCachedTestSessions("folder-a", "practice_questions", [{ id: "session-2" }]);
  assert.deepEqual(readCachedTestLists("folder-a", "practice_questions"), {
    sessions: [{ id: "session-2" }],
  });
  assert.deepEqual(readCachedTestLists("folder-a", "past_paper"), {
    sessions: [{ id: "session-1" }],
    templates: [{ id: "template-1" }],
  });
});
