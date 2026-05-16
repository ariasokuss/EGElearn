import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const featureRoot = join(here, "..");

const files = [
  "ui/practice-empty-state.tsx",
  "ui/practice-questions-view.tsx",
  "ui/topic-selection.tsx",
  "ui/questions-setup.tsx",
  "ui/test-generation.tsx",
  "ui/test-history.tsx",
  "ui/test-taking.tsx",
  "ui/generating-template-card.tsx",
  "ui/wizard-stepper.tsx",
];

test("practice surfaces use russian copy and theme tokens", () => {
  const source = files
    .map((file) => readFileSync(join(featureRoot, file), "utf8"))
    .join("\n");

  assert.doesNotMatch(source, /Test yourself|Create test|Test history|New chat|Close chat|Loading chat/);
  assert.doesNotMatch(source, /No roadmap available|Please create a roadmap first|Select the required topics|Loading question types|Select mode|Practice mode|Exam mode|Creating a test|Start test/);
  assert.doesNotMatch(source, /Loading questions|Could not load|Grading test|Loading results|Submitting answers|No questions found|Are you sure|Your progress will be saved|Open chat|Open test history/);
  assert.doesNotMatch(source, /"Confirm"|>Confirm<|"Cancel"|>Cancel</);
  assert.doesNotMatch(source, />\s*Back\s*</);
  assert.doesNotMatch(source, /Not started tests|Started tests|Completed tests|Untitled Test|not started/);
  assert.doesNotMatch(source, /bg-white|text-\[#242529\]|text-\[#71717A\]|border-\[#F4F4F5\]/);
});
