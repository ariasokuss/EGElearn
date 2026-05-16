import type {
  CheckAnswerOut,
  QuestionWithAnswerOut,
  SessionAnswerOut,
  TestQuestionOut,
} from "@/shared/api/generated/model";

/**
 * Build per-question check payloads from GET session (merged questions + graded_question_ids + answers).
 */
export function buildPracticeChecksFromSession(
  questions: (TestQuestionOut | QuestionWithAnswerOut)[],
  gradedQuestionIds: string[] | undefined,
  answers: SessionAnswerOut[] | undefined,
): Record<string, CheckAnswerOut> {
  const out: Record<string, CheckAnswerOut> = {};
  const gradedSet = new Set(gradedQuestionIds ?? []);
  const answersByQid = new Map((answers ?? []).map((a) => [a.question_id, a]));

  for (const q of questions) {
    const sa = answersByQid.get(q.id);
    const graded =
      gradedSet.has(q.id) || (sa?.graded_at != null && String(sa.graded_at).length > 0);
    if (!graded) continue;

    const qw = q as QuestionWithAnswerOut;
    const answerStr = sa?.answer ?? qw.user_answer ?? "";
    out[q.id] = {
      question_id: q.id,
      type: q.type,
      answer: answerStr,
      answered_at: sa?.answered_at ?? "",
      graded_at: sa?.graded_at ?? null,
      is_correct: sa?.is_correct ?? qw.is_correct ?? null,
      earned_marks: sa?.earned_marks ?? qw.earned_marks ?? null,
      total_marks: qw.points ?? 0,
      score: sa?.score ?? qw.score ?? null,
      model_answer: qw.model_answer ?? null,
      correct_option_index: qw.correct_option_index,
      feedback: sa?.feedback ?? qw.feedback ?? null,
      recommendations: sa?.recommendations ?? qw.recommendations ?? null,
    };
  }
  return out;
}
