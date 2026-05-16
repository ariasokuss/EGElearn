"use client";

import { useRef } from "react";
import { ArrowsPointingInIcon, ChevronLeftIcon, ChevronRightIcon, HideBarIcon, XMarkIcon } from "@/shared/assets/icons";
import { cn, useAutoHideScrollbar } from "@/shared/lib";

import { Md } from "../block-renderer/md";
import { isMcqQuestion } from "./test-question-helpers";
import type { GradedReviewRow } from "./build-graded-review-rows";
import {
  MCQ_GRADED_CORRECT_ROW,
  MCQ_GRADED_LETTER_BADGE,
  MCQ_GRADED_NEUTRAL_ROW,
  MCQ_GRADED_WRONG_SELECTED_ROW,
} from "./mcq-graded-styles";
import { McqGradedTrailingIcon } from "./mcq-graded-trailing-icon";
import { QuestionReviewFeedbackCard } from "./question-review-feedback-card";
import { Button } from "@/shared";

const OPTION_KEYS = ["A", "B", "C", "D", "E", "F", "G", "H"];

type Props = {
  row: GradedReviewRow;
  questionIndex: number;
  total: number;
  onArrowsClick?: VoidFunction;
  onXClick?: VoidFunction;
  onBack: VoidFunction;
  onNext: VoidFunction;
  isLast: boolean;
  chatVisible?: boolean;
  onToggleChat?: VoidFunction;
};

function parseMcqIndex(userAnswer: string | null | undefined): number {
  if (userAnswer == null || userAnswer === "") return -1;
  const trimmed = String(userAnswer).trim();
  if (trimmed !== String(Number.parseInt(trimmed, 10))) return -1;
  const n = Number.parseInt(trimmed, 10);
  return n >= 0 && n < OPTION_KEYS.length ? n : -1;
}

function optionLetter(idx: number): string {
  if (idx < 0) return "—";
  return OPTION_KEYS[idx] ?? String(idx + 1);
}

export function GradedQuestionReviewView({
  row,
  questionIndex,
  total,
  onArrowsClick,
  onXClick,
  onBack,
  onNext,
  isLast,
  chatVisible,
  onToggleChat,
}: Props) {
  const contextScrollRef = useRef<HTMLDivElement>(null);
  const questionScrollRef = useRef<HTMLDivElement>(null);
  const singleColumnScrollRef = useRef<HTMLDivElement>(null);
  useAutoHideScrollbar(contextScrollRef);
  useAutoHideScrollbar(questionScrollRef);
  useAutoHideScrollbar(singleColumnScrollRef);

  const { question, item, templateQuestion } = row;
  const progress = ((questionIndex + 1) / total) * 100;
  const contextTrimmed = templateQuestion?.context?.trim() ?? "";
  const hasContext = contextTrimmed.length > 0;
  const showMcqGrid = templateQuestion != null && isMcqQuestion(templateQuestion);
  const selectedIdx = showMcqGrid ? parseMcqIndex(item.answer) : parseMcqIndex(item.answer);
  const correctIdx = item.correct_option_index ?? -1;
  const mcqFallback =
    !showMcqGrid && (item.type === "mcq" || correctIdx >= 0);
  const earned = item.points ?? 0;
  const maxPoints = item.total_points;
  const answerImageUrls = Array.from(
    new Set(
      item.image_urls && item.image_urls.length > 0
        ? item.image_urls
        : item.image_url
          ? [item.image_url]
          : [],
    ),
  );

  const reviewBody = (
    <>
      <div className="min-w-0 nova-text-label-base text-[#242529]">
        <Md variant="testQuestion">{question}</Md>
      </div>

      {showMcqGrid && templateQuestion.options ? (
        <div className="mt-6 flex flex-col gap-2">
          <p className="nova-text-label-small uppercase tracking-wider text-[#9B97A3]">
            Your answer
          </p>
          {templateQuestion.options.map((opt, idx) => {
            const key = OPTION_KEYS[idx] ?? String(idx);
            const isSelected = idx === selectedIdx;
            const isCorrect = idx === correctIdx;
            return (
              <div
                key={idx}
                className={cn(
                  "flex items-center gap-3 rounded-xl border border-solid px-4 py-3 text-left",
                  isCorrect && MCQ_GRADED_CORRECT_ROW,
                  !isCorrect && isSelected && MCQ_GRADED_WRONG_SELECTED_ROW,
                  !isCorrect && !isSelected && MCQ_GRADED_NEUTRAL_ROW,
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full nova-text-label-base",
                    MCQ_GRADED_LETTER_BADGE,
                  )}
                >
                  {key}
                </span>
                <span className="min-w-0 flex-1 nova-text-p-base text-[#242529]">
                  <Md inline>{opt}</Md>
                </span>
                {isCorrect || (!isCorrect && isSelected) ? (
                  <McqGradedTrailingIcon variant={isCorrect ? "correct" : "incorrect"} />
                ) : null}
              </div>
            );
          })}
        </div>
      ) : mcqFallback ? (
        <div className="mt-6 min-w-0 max-w-full space-y-3 break-words rounded-xl border border-[#E8E5E1] bg-white px-4 py-3 nova-text-label-small text-[#242529] [&_p]:min-w-0 [&_pre]:max-w-full [&_pre]:overflow-x-auto">
          <p>
            <span className="font-semibold text-[#9B97A3]">Your selection: </span>
            {optionLetter(selectedIdx)}
          </p>
          {correctIdx >= 0 ? (
            <p>
              <span className="font-semibold text-[#9B97A3]">Correct: </span>
              {optionLetter(correctIdx)}
            </p>
          ) : null}
          {item.answer?.trim() && parseMcqIndex(item.answer) < 0 ? (
            <div className="pt-1">
              <Md>{item.answer.trim()}</Md>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-6 min-w-0">
          <p className="nova-text-label-tiny-sb uppercase tracking-wider text-[#9B97A3]">
            Your answer
          </p>
          {answerImageUrls.length > 0 ? (
            <div className="mt-2 overflow-hidden rounded-xl border border-[#E8E5E1] bg-white">
              {item.answer?.trim() ? (
                <div className="px-4 py-3 nova-text-label-small text-[#242529]">
                  <Md>{item.answer.trim()}</Md>
                </div>
              ) : null}
              {answerImageUrls.map((url, i) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={url}
                  src={url}
                  alt={`Student answer${answerImageUrls.length > 1 ? ` ${i + 1}` : ""}`}
                  className={`w-full object-contain${item.answer?.trim() || i > 0 ? " border-t border-[#E8E5E1]" : ""}`}
                />
              ))}
            </div>
          ) : (
            <div className="mt-2 min-w-0 max-w-full break-words rounded-xl border border-[#E8E5E1] bg-white px-4 py-3 nova-text-label-small text-[#242529] [&_p]:min-w-0 [&_pre]:max-w-full [&_pre]:overflow-x-auto">
              {item.answer?.trim() ? (
                <Md>{item.answer.trim()}</Md>
              ) : (
                <span className="text-[#A1A1AA]">No answer submitted</span>
              )}
            </div>
          )}
        </div>
      )}

      <QuestionReviewFeedbackCard
        points={earned}
        totalPoints={maxPoints}
        feedback={item.feedback}
        recommendation={item.recommendation}
        modelAnswer={item.model_answer}
      />
    </>
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-4 border-b border-[#E8E5E1] px-5 py-3">
        <div className="flex shrink-0">
          {onXClick &&
            <Button
              iconOnly
              rounded={false}
              variant="plain"
              type="button"
              onClick={onXClick}
              className="flex shrink-0 items-center justify-center"
              aria-label="Exit test"
            >
              <XMarkIcon className="size-4.5" />
            </Button>
          }
          {onArrowsClick &&
            <Button
              iconOnly
              rounded={false}
              variant="plain"
              type="button"
              onClick={onArrowsClick}
              className="flex shrink-0 items-center justify-center"
              aria-label="Back to summary"
            >
              <ArrowsPointingInIcon />
            </Button>
          }
        </div>

        <div className="flex flex-1 flex-col items-center gap-1.5">
          <span className="nova-text-label-small text-[#71717A]">
            {(() => {
              const qn =
                templateQuestion?.question_number ??
                (item as { question_number?: string | null }).question_number;
              return qn
                ? `Review ${qn} · ${questionIndex + 1} of ${total}`
                : `Review ${questionIndex + 1} of ${total}`;
            })()}
          </span>
          <div className="h-1 w-full max-w-xs rounded-full bg-[#E8E5E1]">
            <div
              className="h-1 rounded-full bg-[#242529] transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onToggleChat && !chatVisible && (
            <Button
              iconOnly
              size="sm"
              variant="outline"
              type="button"
              onClick={onToggleChat}
              className="flex shrink-0 items-center justify-center"
              aria-label="Open chat"
              title="Open chat"
            >
              <HideBarIcon className="h-4 w-4 rotate-180" />
            </Button>
          )}
          <Button
            size="sm"
            variant="plain"
            type="button"
            disabled={questionIndex === 0}
            onClick={onBack}
            className="flex items-center justify-center gap-1 text-[#71717A] opacity-50 hover:opacity-100"
          >
            <ChevronLeftIcon className="h-3.5 w-3.5" />
            Back
          </Button>
          <Button
            size="sm"
            type="button"
            onClick={onNext}
            className="flex items-center justify-center gap-1"
          >
            {isLast ? "Summary" : "Next"}
            {!isLast && <ChevronRightIcon className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {hasContext ? (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col px-[24px] pt-[48px]">
          <div className="flex min-h-0 min-w-0 flex-1">
            <div
              ref={contextScrollRef}
              className="auto-hide-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto border-r border-[#E8E5E1] px-8 py-6"
            >
              <h3 className="mb-4 nova-text-label-small uppercase tracking-wider text-[#9B97A3]">
                Context
              </h3>
              <div className="min-w-0 text-[#242529]">
                <Md variant="testContext">{contextTrimmed}</Md>
              </div>
            </div>
            <div
              ref={questionScrollRef}
              className="auto-hide-scrollbar flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto px-8 py-6"
            >
              {reviewBody}
            </div>
          </div>
        </div>
      ) : (
        <div
          ref={singleColumnScrollRef}
          className="auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto px-[24px] pt-[48px]"
        >
          <div className="flex justify-center">
            <div className="flex w-full max-w-[640px] flex-col px-8 py-6">{reviewBody}</div>
          </div>
        </div>
      )}
    </div>
  );
}
