"use client";

import { cn } from "@/shared/lib";

import { Md } from "../block-renderer/md";
import {
  PracticeQuestionBar,
  type PracticeQuestionControls,
} from "./practice-question-bar";
import {
  OptionalQuestionSkip,
  type OptionalQuestionSkipProps,
} from "./optional-question-skip";
import { McqGradedTrailingIcon } from "./mcq-graded-trailing-icon";
import {
  MCQ_GRADED_CORRECT_ROW,
  MCQ_GRADED_LETTER_BADGE,
  MCQ_GRADED_NEUTRAL_ROW,
  MCQ_GRADED_WRONG_SELECTED_ROW,
} from "./mcq-graded-styles";

const OPTION_KEYS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const MCQ_SELECTED_SURFACE =
  "border-[#C0C0C0] bg-white shadow-[0_2px_4px_0_rgba(28,40,64,0.06),0_1px_2px_-1px_rgba(28,40,64,0.10),0_0_0_4px_rgba(232,229,225,0.22)]";

export type { PracticeQuestionControls as McqPracticeControls } from "./practice-question-bar";

type Props = {
  question: string;
  options: string[];
  selected: number | null;
  onSelect: (index: number) => void;
  practiceControls?: PracticeQuestionControls | null;
  optionalQuestionSkip?: OptionalQuestionSkipProps | null;
};

export function BackendMcqQuestion({
  question,
  options,
  selected,
  onSelect,
  practiceControls,
  optionalQuestionSkip = null,
}: Props) {
  const checked = practiceControls?.checkResult ?? null;
  const correctIdx = checked?.correctOptionIndex ?? null;
  const lockedAfterCheck = checked != null;

  return (
    <div className="flex min-w-0 max-w-full flex-col">
      <div className="min-w-0 text-[#242529]">
        <Md variant="testQuestion">{question}</Md>
      </div>
      <p className="mt-3.5 text-[#242529] nova-text-label-tiny-sb">Select one answer</p>
      <div className="mb-4 mt-3 flex flex-col gap-3">
        {options.map((opt, idx) => {
          const key = OPTION_KEYS[idx] ?? String(idx);
          const isSelected = selected === idx;
          const isCorrect = correctIdx !== null && correctIdx >= 0 && idx === correctIdx;
          const showGraded =
            checked != null && correctIdx !== null && correctIdx >= 0;

          const rowInner = (
            <>
              <span
                className={cn(
                  "flex h-6 min-w-5 shrink-0 items-center justify-center text-[16px] font-medium leading-6 tracking-[-0.32px] text-[#242529]",
                  showGraded && MCQ_GRADED_LETTER_BADGE,
                )}
              >
                {key}
              </span>
              <span className="min-w-0 flex-1 text-[14px] font-normal leading-[23.63px] text-[rgba(36,37,41,0.68)]">
                <Md inline>{opt}</Md>
              </span>
              {showGraded && (isCorrect || (!isCorrect && isSelected)) ? (
                <McqGradedTrailingIcon variant={isCorrect ? "correct" : "incorrect"} />
              ) : null}
            </>
          );

          if (showGraded) {
            return (
              <button
                key={idx}
                type="button"
                disabled={lockedAfterCheck}
                onClick={() => onSelect(idx)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-[12px] border border-solid px-4 py-3 text-left transition-[colors,box-shadow] disabled:cursor-default disabled:opacity-100",
                  isCorrect && MCQ_GRADED_CORRECT_ROW,
                  !isCorrect && isSelected && MCQ_GRADED_WRONG_SELECTED_ROW,
                  !isCorrect && !isSelected && MCQ_GRADED_NEUTRAL_ROW,
                )}
              >
                {rowInner}
              </button>
            );
          }

          return (
            <div
              key={idx}
              className={cn(
                "rounded-[12px] p-px backdrop-blur-[2px]")}
            >
              <button
                type="button"
                disabled={lockedAfterCheck}
                onClick={() => onSelect(idx)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-[11px] border border-solid px-4 py-3 text-left transition-[colors,box-shadow] disabled:cursor-default disabled:opacity-100",
                  isSelected
                    ? MCQ_SELECTED_SURFACE
                    : "border-[#E8E5E1] bg-white shadow-none hover:bg-[#FAFAF8]",
                )}
              >
                {rowInner}
              </button>
            </div>
          );
        })}
      </div>

      {optionalQuestionSkip ? (
        <OptionalQuestionSkip
          checked={optionalQuestionSkip.checked}
          onCheckedChange={optionalQuestionSkip.onCheckedChange}
          disabled={
            optionalQuestionSkip.disabled ?? lockedAfterCheck
          }
        />
      ) : null}

      {practiceControls ? (
        <div className="mt-6">
          <PracticeQuestionBar controls={practiceControls} />
        </div>
      ) : null}
    </div>
  );
}
