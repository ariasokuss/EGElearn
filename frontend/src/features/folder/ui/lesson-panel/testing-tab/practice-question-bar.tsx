"use client";

import { IdeaLampIcon } from "@/shared/assets/icons";
import { Button } from "@/shared";

import { QuestionReviewFeedbackCard } from "./question-review-feedback-card";

export type PracticeQuestionCheckResult = {
  isCorrect: boolean | null;
  /** MCQ only; null for open questions after check */
  correctOptionIndex: number | null;
  feedback: string | null;
  modelAnswer: string | null;
  recommendation: string | null;
  earnedMarks: number | null;
  totalMarks: number;
};

export type PracticeQuestionControls = {
  /** Pre-generated hint text; when set, "Show hint" button is shown. */
  hint: string | null;
  /** Whether hint was already shown for this question (disables button). */
  hintUsed?: boolean;
  /** Open the chat panel and show hint as a message. */
  onShowHintInChat?: () => void;
  onCheck: () => void;
  checkLoading: boolean;
  checkDisabled: boolean;
  checkResult: PracticeQuestionCheckResult | null;
  /** True when the current question is the last in the test. */
  isLast: boolean;
  /** Advance to next question (or submit on last). */
  onContinue: () => void;
};

export function PracticeQuestionBar({ controls }: { controls: PracticeQuestionControls }) {
  const checked = controls.checkResult;
  const hasCheckResult = checked != null;

  const buttonLabel = hasCheckResult
    ? controls.isLast
      ? "Завершить"
      : "Продолжить"
    : "Проверить";

  const buttonDisabled = hasCheckResult
    ? false
    : controls.checkDisabled || controls.checkLoading;

  const buttonAction = hasCheckResult ? controls.onContinue : controls.onCheck;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-6">
        <Button
          size="sm"
          type="button"
          onClick={buttonAction}
          disabled={buttonDisabled}
          isLoading={controls.checkLoading}
          className={buttonDisabled ? undefined : "cursor-pointer"}
        >
          {buttonLabel}
        </Button>
        {controls.hint ? (
          <button
            type="button"
            onClick={() => controls.onShowHintInChat?.()}
            disabled={controls.hintUsed}
            className="flex cursor-pointer items-center gap-1.5 nova-text-label-small text-[#242529] transition-colors hover:text-[#3F3C47] disabled:cursor-default disabled:text-[#71717A] disabled:opacity-100 disabled:hover:text-[#71717A]"
          >
            <IdeaLampIcon className="h-4 w-4 shrink-0" aria-hidden />
            {controls.hintUsed ? "Подсказка использована" : "Показать подсказку"}
          </button>
        ) : null}
      </div>

      {checked ? (
        <QuestionReviewFeedbackCard
          points={checked.earnedMarks ?? 0}
          totalPoints={checked.totalMarks}
          feedback={checked.feedback}
          recommendation={checked.recommendation}
          modelAnswer={checked.modelAnswer}
        />
      ) : null}
    </div>
  );
}
