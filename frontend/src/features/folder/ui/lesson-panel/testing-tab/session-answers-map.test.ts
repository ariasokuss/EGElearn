import assert from "node:assert/strict";
import test from "node:test";

import { isTestSessionFinishedForResults } from "./session-answers-map";

function sessionWithStatus(status: string) {
  return {
    id: "session-id",
    template_id: "template-id",
    template_name: null,
    session_mode: "exam",
    status,
    earned_marks: null,
    total_marks: 10,
    score: null,
    started_at: null,
    submitted_at: null,
    graded_at: null,
    created_at: "2026-05-05T00:00:00Z",
    updated_at: "2026-05-05T00:00:00Z",
  };
}

test("isTestSessionFinishedForResults treats submitted states as results states", () => {
  for (const status of ["graded", "submitted", "completed", "grading"]) {
    assert.equal(isTestSessionFinishedForResults(sessionWithStatus(status)), true, status);
  }
});

test("isTestSessionFinishedForResults keeps active sessions in the test", () => {
  for (const status of ["not_started", "active", "aborted"]) {
    assert.equal(isTestSessionFinishedForResults(sessionWithStatus(status)), false, status);
  }
});
