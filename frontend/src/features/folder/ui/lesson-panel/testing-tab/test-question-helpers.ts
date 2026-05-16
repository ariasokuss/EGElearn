import type { TestQuestionOut } from "@/shared/api/generated/model";

/** True when the UI should use MCQ controls (backend may send type mcq without options). */
export function isMcqQuestion(q: Pick<TestQuestionOut, "type" | "options">): boolean {
  return q.type === "mcq" && Array.isArray(q.options) && q.options.length > 0;
}
