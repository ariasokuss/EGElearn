"use client";

import { memo } from "react";
import TextareaAutosize from "react-textarea-autosize";

import { cn } from "@/shared/lib";

import { Md } from "../block-renderer/md";

import {
  OPEN_ANSWER_MAX_LENGTH,
  OPEN_ANSWER_TEXTAREA_MAX_ROWS,
} from "./open-answer-constants";
import {
  PracticeQuestionBar,
  type PracticeQuestionControls,
} from "./practice-question-bar";
import {
  OptionalQuestionSkip,
  type OptionalQuestionSkipProps,
} from "./optional-question-skip";
import {
  PastPaperAnswerImageAttach,
  type PastPaperAnswerImageAttachProps,
} from "./past-paper-answer-image-attach";

type StemProps = {
  context?: string | null;
  question: string;
  points: number;
  hint: string | null;
  practiceMode: boolean;
};

const BackendOpenQuestionStem = memo(function BackendOpenQuestionStem({
  context,
  question,
  points,
  hint,
  practiceMode,
}: StemProps) {
  const marksLabel = `${points} ${points === 1 ? "балл" : points >= 2 && points <= 4 ? "балла" : "баллов"}`;

  return (
    <>
      {context?.trim() ? (
        <div className="rounded-xl border border-[#E8E5E1] bg-[#FAFAF8] px-4 py-3 nova-text-label-small text-[#3F3C47]">
          <Md>{context.trim()}</Md>
        </div>
      ) : null}
      <div className="flex items-start justify-between gap-3">
        <div className="text-[#242529]">
          <Md variant="testQuestion">{question}</Md>
        </div>
        <span className="mt-0.5 shrink-0 rounded-full border border-[#E8E5E1] bg-[#FAFAF8] px-2.5 py-0.5 nova-text-label-tiny text-[#71717A]">
          {marksLabel}
        </span>
      </div>

      {hint && !practiceMode ? (
        <p className="nova-text-label-tiny italic text-[#9B97A3]">Подсказка: {hint}</p>
      ) : null}
    </>
  );
});

type Props = {
  context?: string | null;
  question: string;
  points: number;
  hint: string | null;
  answer: string;
  onAnswerChange: (value: string) => void;
  practiceControls?: PracticeQuestionControls | null;
  answerImageAttach?: PastPaperAnswerImageAttachProps | null;
  optionalQuestionSkip?: OptionalQuestionSkipProps | null;
};

export function BackendOpenQuestion({
  context,
  question,
  points,
  hint,
  answer,
  onAnswerChange,
  practiceControls,
  answerImageAttach = null,
  optionalQuestionSkip = null,
}: Props) {
  const practiceMode = practiceControls != null;
  const lockedAfterCheck = practiceControls?.checkResult != null;

  return (
    <div className="flex flex-col gap-4">
      <BackendOpenQuestionStem
        context={context}
        question={question}
        points={points}
        hint={hint}
        practiceMode={practiceMode}
      />

      <TextareaAutosize
        readOnly={lockedAfterCheck}
        value={answer}
        onChange={(e) =>
          onAnswerChange(e.target.value.slice(0, OPEN_ANSWER_MAX_LENGTH))
        }
        placeholder="Напиши ответ здесь…"
        minRows={6}
        maxRows={OPEN_ANSWER_TEXTAREA_MAX_ROWS}
        maxLength={OPEN_ANSWER_MAX_LENGTH}
        className={cn(
          "w-full resize-none rounded-xl border border-[#E8E5E1] px-4 py-3 nova-text-label-small text-[#242529] placeholder-[#A1A1AA] outline-none transition-colors focus:border-[#3F3C47] focus:ring-0",
          lockedAfterCheck
            ? "cursor-default bg-[#FAFAF8] text-[#242529]"
            : "bg-white",
        )}
      />

      {answerImageAttach ? (
        <PastPaperAnswerImageAttach
          files={answerImageAttach.files}
          onAddFiles={answerImageAttach.onAddFiles}
          onRemoveAt={answerImageAttach.onRemoveAt}
          disabled={answerImageAttach.disabled ?? lockedAfterCheck}
        />
      ) : null}

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
        <div className="mt-2">
          <PracticeQuestionBar controls={practiceControls} />
        </div>
      ) : null}
    </div>
  );
}
