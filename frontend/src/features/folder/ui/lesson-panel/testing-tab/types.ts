import type { DirectiveSegment } from "../block-renderer/parse-content";

export type QuestionWithContext = {
  type: "mcq" | "short_answer" | "calculation";
  segment: DirectiveSegment;
  context: string | null;
};

export type QuestionResult = {
  type: QuestionWithContext["type"];
  questionText: string;
  label: string | null;
  earned: number;
  total: number;
};

export type TestRecord = {
  id: string;
  date: Date;
  results: QuestionResult[];
  earned: number;
  total: number;
  percent: number;
};
