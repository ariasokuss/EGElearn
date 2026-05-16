import type {
  QuestionWithAnswerOut,
  SessionAnswerOut,
  TestQuestionOut,
  TestSessionOut,
} from "@/shared/api/generated/model";

import { isMcqQuestion } from "./test-question-helpers";

export function backendAnswersToLocal(
  answers: SessionAnswerOut[],
  questions: (TestQuestionOut | QuestionWithAnswerOut)[],
) {
  const mcq: Record<number, number> = {};
  const open: Record<number, string> = {};
  for (const answer of answers) {
    const qIdx = questions.findIndex((q) => q.id === answer.question_id);
    if (qIdx === -1) continue;
    const question = questions[qIdx];
    if (!question) continue;
    if (isMcqQuestion(question)) {
      const parsed = parseInt(answer.answer, 10);
      if (!Number.isNaN(parsed)) mcq[qIdx] = parsed;
    } else {
      open[qIdx] = answer.answer;
    }
  }
  return { mcq, open };
}

export function computeResumeQuestionIndex(
  questions: TestQuestionOut[],
  mcq: Record<number, number>,
  open: Record<number, string>,
): number {
  if (questions.length === 0) return 0;
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    if (!q) continue;
    if (isMcqQuestion(q)) {
      const v = mcq[i];
      if (v === undefined || v < 0) return i;
    } else if ((open[i] ?? "").trim() === "") {
      return i;
    }
  }
  return questions.length - 1;
}

export function isTestStatusReadyForResultsSurface(status: string | null | undefined): boolean {
  return status === "graded" || status === "submitted" || status === "completed" || status === "grading";
}

export function isTestSessionFinishedForResults(session: TestSessionOut): boolean {
  return isTestStatusReadyForResultsSurface(session.status);
}
