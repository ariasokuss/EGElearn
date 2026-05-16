import type {
  FeedbackItemOut,
  SessionResultsOut,
  TestQuestionOut,
} from "@/shared/api/generated/model";

export type GradedReviewRow = {
  question: string;
  relation: string;
  item: FeedbackItemOut;
  templateQuestion: TestQuestionOut | null;
};

export function buildReviewRowsFromFeedback(
  items: FeedbackItemOut[],
  summary: SessionResultsOut | null,
  templateByIndex: (TestQuestionOut | null)[],
): GradedReviewRow[] {
  return items.map((item, i) => ({
    question: summary?.questions[i]?.question ?? `Question ${i + 1}`,
    relation: summary?.questions[i]?.relation ?? "",
    item,
    templateQuestion: templateByIndex[i] ?? null,
  }));
}
