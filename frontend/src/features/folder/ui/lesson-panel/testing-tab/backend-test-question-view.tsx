"use client";

import { useRef } from "react";
import { ArrowsPointingInIcon, ArrowsPointingOutIcon, ChevronLeftIcon, ChevronRightIcon, XMarkIcon } from "@/shared/assets/icons";
import type { TestQuestionOut } from "@/shared/api/generated/model";

import { Md } from "../block-renderer/md";
import { BackendMcqQuestion } from "./backend-mcq-question";
import type { PracticeQuestionControls } from "./practice-question-bar";
import type { OptionalQuestionSkipProps } from "./optional-question-skip";
import type { PastPaperAnswerImageAttachProps } from "./past-paper-answer-image-attach";
import { BackendOpenQuestion } from "./backend-open-question";
import { isMcqQuestion } from "./test-question-helpers";
import { Button } from "@/shared";
import { useAutoHideScrollbar } from "@/shared/lib";

type Props = {
  question: TestQuestionOut | undefined;
  questionIndex: number;
  total: number;
  mcqAnswer: number | null;
  onMcqSelect: (index: number) => void;
  openAnswer: string;
  onOpenAnswer: (value: string) => void;
  onArrowsClick?: VoidFunction;
  onXClick?: VoidFunction;
  onBack: VoidFunction;
  onNext: VoidFunction;
  isLast: boolean;
  headerExtra?: React.ReactNode;
  isExpanded?: boolean;
  examMode?: boolean;
  notice?: string;
  practiceControls?: PracticeQuestionControls | null;
  optionalQuestionSkip?: OptionalQuestionSkipProps | null;
  answerImageAttach?: PastPaperAnswerImageAttachProps | null;
};

export function BackendTestQuestionView({
  question,
  questionIndex,
  total,
  mcqAnswer,
  onMcqSelect,
  openAnswer,
  onOpenAnswer,
  onArrowsClick,
  onXClick,
  onBack,
  onNext,
  isLast,
  headerExtra,
  isExpanded,
  examMode = false,
  notice,
  practiceControls = null,
  optionalQuestionSkip = null,
  answerImageAttach = null,
}: Props) {
  const contextScrollRef = useRef<HTMLDivElement>(null);
  const questionScrollRef = useRef<HTMLDivElement>(null);
  const singleColumnScrollRef = useRef<HTMLDivElement>(null);
  useAutoHideScrollbar(contextScrollRef);
  useAutoHideScrollbar(questionScrollRef);
  useAutoHideScrollbar(singleColumnScrollRef);

  if (!question) {
    return (
      <div className="flex h-full items-center justify-center px-7">
        <p className="text-center nova-text-p-base text-[#71717A]">Вопрос не найден.</p>
      </div>
    );
  }

  const progress = ((questionIndex + 1) / total) * 100;
  const hint = examMode ? null : (question.hint ?? null);
  const contextTrimmed = question.context?.trim() ?? "";
  const hasContext = contextTrimmed.length > 0;

  const questionBody = isMcqQuestion(question) ? (
    <BackendMcqQuestion
      question={question.question}
      options={question.options!}
      selected={mcqAnswer}
      onSelect={onMcqSelect}
      practiceControls={!examMode ? practiceControls : null}
      optionalQuestionSkip={optionalQuestionSkip}
    />
  ) : (
    <BackendOpenQuestion
      context={null}
      question={question.question}
      points={question.points}
      hint={hint}
      answer={openAnswer}
      onAnswerChange={onOpenAnswer}
      practiceControls={!examMode ? practiceControls : null}
      answerImageAttach={answerImageAttach}
      optionalQuestionSkip={optionalQuestionSkip}
    />
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 overflow-x-auto border-b border-[#E8E5E180]">
        <div className="grid w-full min-w-full grid-cols-[auto_1fr_auto] items-center gap-4 px-5 py-3">
          <div className="flex shrink-0">
            <Button
              iconOnly
              size="sm"
              variant="plain"
              rounded={false}
              type="button"
              onClick={onXClick ?? onArrowsClick ?? undefined}
              className="flex shrink-0 items-center justify-center"
              aria-label="Выйти из теста"
            >
              <XMarkIcon className="size-4.5" />
            </Button>
            {onArrowsClick && (
              <Button
                iconOnly
                size="sm"
                variant="plain"
                rounded={false}
                type="button"
                onClick={onArrowsClick}
                className="flex shrink-0 items-center justify-center"
                aria-label="Переключить полноэкранный режим"
              >
                {isExpanded ? <ArrowsPointingInIcon /> : <ArrowsPointingOutIcon />}
              </Button>
            )}
          </div>

          <div className="flex max-w-[400px] shrink-0 items-center gap-3 justify-self-center">
            <span className="shrink-0 overflow-hidden text-ellipsis nova-text-label-small text-[#72706F]">
              {question.question_number
                ? `Вопрос ${question.question_number} · ${questionIndex + 1} из ${total}`
                : `Вопрос ${questionIndex + 1} из ${total}`}
            </span>
            <div className="h-1 w-48 rounded-full" style={{ backgroundColor: "rgba(235, 225, 218, 0.36)" }}>
              <div
                className="h-1 rounded-full transition-all duration-300"
                style={{ width: `${progress}%`, backgroundColor: "#EBE1DA" }}
              />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 justify-self-end">
            <Button
              size="sm"
              variant="plain"
              type="button"
              disabled={questionIndex === 0}
              onClick={onBack}
              className="flex items-center justify-center gap-1 text-[#71717A] opacity-50 hover:opacity-100"
            >
              <ChevronLeftIcon className="h-3.5 w-3.5" />
              Назад
            </Button>
            <Button
              size="sm"
              type="button"
              onClick={onNext}
              className="flex items-center justify-center gap-1"
            >
              {isLast ? "Завершить" : "Далее"}
              {!isLast && <ChevronRightIcon className="h-3.5 w-3.5" />}
            </Button>
            {headerExtra}
          </div>
        </div>
      </div>

      {notice && questionIndex === 0 && (
        <div className="shrink-0 border-b border-[#E8E5E180] bg-[#FAF8F7] px-5 py-2">
          <p className="text-center nova-text-label-tiny text-[#9B97A3]">
            {notice}
          </p>
        </div>
      )}

      {hasContext ? (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col px-[24px]">
          <div className="flex min-h-0 min-w-0 flex-1">
            <div
              ref={contextScrollRef}
              className="auto-hide-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto border-r border-[#E8E5E1]"
            >
              <div className="h-[72px] w-full shrink-0" aria-hidden />
              <div className="flow-root px-8 pb-6">
                <h3 className="mb-4 font-(family-name:--font-inter) text-[18px] font-semibold leading-[26px] text-[#242529]">
                  Context
                </h3>
                <div className="min-w-0 text-[#242529]">
                  <Md variant="testContext">{contextTrimmed}</Md>
                </div>
              </div>
            </div>
            <div
              ref={questionScrollRef}
              className="auto-hide-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto"
            >
              <div className="h-[72px] w-full shrink-0" aria-hidden />
              <div className="flow-root px-8 pb-6">{questionBody}</div>
            </div>
          </div>
        </div>
      ) : (
        <div
          ref={singleColumnScrollRef}
          className="auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto px-[24px]"
        >
          <div className="h-[72px] w-full shrink-0" aria-hidden />
          <div className="flex justify-center">
            <div className="flow-root flex w-full max-w-[640px] flex-col px-8 pb-6">
              {questionBody}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
