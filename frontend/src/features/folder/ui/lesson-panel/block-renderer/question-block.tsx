"use client";

import { useState } from "react";

import { cn } from "@/shared/lib";

import { Button, CheckboxChecked, CheckboxError } from "@/shared/ui";
import {
  PaperAirplaneIcon,
  ChevronDownIcon,
  EyeIcon,
  IdeaLampIcon,
  CheckedIcon,
} from "@/shared/assets/icons";
import { LessonCard } from "@/shared/ui/lesson-card";

import type { AnswerRecord } from "../use-inline-quiz";
import type { DirectiveSegment } from "./parse-content";
import { parseMcq, parseOpenQuestion } from "./parse-content";
import { Md } from "./md";

type QuestionBlockProps = {
  segment: DirectiveSegment;
  savedAnswer?: AnswerRecord;
  onSubmit?: (record: AnswerRecord) => void;
};

function QuestionWrapper({ children }: { children: React.ReactNode }) {
  return (
    <LessonCard className="p-px">
      <div className="rounded-[20px] bg-white pt-1.5 shadow-[0px_2px_4px_-2px_#00000005]">
        <div className="flex flex-col px-4 pb-4">
          <span className="nova-text-label-tiny-sb text-[#A1A1AA]">
            QUESTION
          </span>
          {children}
        </div>
      </div>
    </LessonCard>
  );
}

type ModelAnswerBlockProps = {
  isCorrect: boolean;
  marksEarned: number;
  marksTotal: number;
  feedback?: string;
  recommendations?: string;
  modelAnswer: string;
};

export function ModelAnswerBlock({
  isCorrect,
  marksEarned,
  marksTotal,
  feedback,
  recommendations,
  modelAnswer,
}: ModelAnswerBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const isPartial = !isCorrect && marksEarned > 0;

  return (
    <LessonCard className="p-px">
      <div className="rounded-[20px] bg-white shadow-[0px_2px_4px_-2px_#00000005]">
        {/* Header: icon + marks */}
        <div className="flex items-center gap-3 px-4 pt-3.5">
          {isCorrect ? (
            <CheckboxChecked color="#84B496" checkColor="white" />
          ) : isPartial ? (
            <CheckboxChecked />
          ) : (
            <CheckboxError />
          )}
          <span className="nova-text-label-medium text-[#242529]">
            {marksEarned}/{marksTotal} marks earned
          </span>
        </div>

        {/* Feedback row */}
        {feedback && (
          <div className="mt-3 flex gap-3 px-4">
            <CheckedIcon className="mt-0.5 h-4 w-4 shrink-0 text-[#A1A1AA]" />
            <span className="nova-text-p-base text-[#242529AD]">
              {feedback}
            </span>
          </div>
        )}

        {/* Recommendations row */}
        {recommendations && !isCorrect && (
          <div className="mt-3 flex gap-3 px-4">
            <IdeaLampIcon className="mt-0.5 h-4 w-4 shrink-0 text-[#A1A1AA]" />
            <span className="nova-text-p-base text-[#242529AD]">
              {recommendations}
            </span>
          </div>
        )}

        {/* Divider — full width */}
        <div className="mt-3.5 h-px w-full bg-[#F4F4F5]" />

        {/* Model answer toggle */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center px-4"
          style={{ padding: "12px 14px" }}
        >
          <EyeIcon className="h-4 w-4 shrink-0 text-[#A1A1AA]" />
          <span className="ml-3 nova-text-label-medium text-[#A1A1AA]">
            Model answer
          </span>
          <ChevronDownIcon
            className={cn(
              "ml-auto h-5 w-5 shrink-0 transition-transform text-[#A1A1AA]",
              expanded && "rotate-180",
            )}
          />
        </button>

        {/* Expanded answer content */}
        {expanded && (
          <>
            <div className="h-px w-full bg-[#F4F4F5]" />
            <div className="flex gap-3 p-3.5">
              <div
                className={cn(
                  "w-1 shrink-0 self-stretch rounded-full",
                  isCorrect ? "bg-[#84B496]" : isPartial ? "bg-[#E8DFD9]" : "bg-[#C77785]",
                )}
              />
              <div className="min-w-0 nova-text-p-base text-[#242529AD]">
                <Md>{modelAnswer}</Md>
              </div>
            </div>
          </>
        )}

        {/* Bottom spacing when collapsed */}
        {!expanded && <div className="pb-1" />}
      </div>
    </LessonCard>
  );
}

const INDEX_TO_KEY: Record<string, string> = { "0": "A", "1": "B", "2": "C", "3": "D" };

function McqQuestionBlock({ segment, savedAnswer, onSubmit }: QuestionBlockProps) {
  const data = parseMcq(segment.body);
  // savedAnswer.answer is stored as option index ("0","1",...), convert back to key
  const savedKey = savedAnswer ? (INDEX_TO_KEY[savedAnswer.answer] ?? savedAnswer.answer) : null;
  const [localSelected, setLocalSelected] = useState<string | null>(null);

  // Use savedAnswer as source of truth when available
  const confirmed = !!savedAnswer;
  const selected = savedKey ?? localSelected;

  function handleConfirm() {
    const sel = localSelected;
    if (!sel) return;
    const correct = sel === data.correct;
    const optionIndex = { A: 0, B: 1, C: 2, D: 3 }[sel] ?? 0;
    onSubmit?.({
      answer: String(optionIndex),
      questionType: "mcq",
      isCorrect: correct,
      earnedMarks: correct ? 1 : 0,
      totalMarks: 1,
      feedback: null,
      recommendations: null,
      grading: false,
    });
  }

  const isCorrect = confirmed && selected === data.correct;

  return (
    <div className="flex flex-col gap-1.5">
      <QuestionWrapper>
        <div className="mt-2.5 nova-text-p-large text-[#242529]">
          <Md>{data.question}</Md>
        </div>

        <div className="mt-6 flex flex-col gap-2">
          {data.options.map((opt) => {
            const isSelected = opt.key === selected;
            const isOptCorrect = confirmed && opt.key === data.correct;
            const isWrong = confirmed && opt.key === selected && opt.key !== data.correct;

            return (
              <button
                key={opt.key}
                type="button"
                disabled={confirmed}
                onClick={() => setLocalSelected(opt.key)}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-3 py-2 pl-3.5 text-left transition-all",
                  !confirmed && !isSelected &&
                  "border-[#E4E4E76B] bg-white backdrop-blur-xs hover:border-[#CCC] hover:shadow-[0px_2px_4px_0px_#1C28400F,0px_1px_2px_-1px_#1C28401A,0px_0px_0px_4px_#E8E5E138] cursor-pointer",
                  !confirmed && isSelected &&
                  "border-[#CCC] bg-white shadow-[0px_2px_4px_0px_#1C28400F,0px_1px_2px_-1px_#1C28401A,0px_0px_0px_4px_#E8E5E138]",
                  isOptCorrect &&
                  "border-[#84B496] bg-[#FFFFFF01] shadow-[0px_2px_4px_0px_#1C28400F,0px_1px_2px_-1px_#1C28401A,0px_0px_0px_4px_#84B4960F]",
                  isWrong &&
                  "border-[#F6627CA3] bg-[#FFFFFF01] shadow-[0px_2px_4px_0px_#1C28400F,0px_1px_2px_-1px_#1C28401A,0px_0px_0px_4px_#F6627C0F]",
                  confirmed && !isOptCorrect && !isWrong && "border-[#E4E4E76B] bg-white opacity-40",
                )}
              >
                <span className="nova-text-label-base text-[#242529]">
                  {opt.key}
                </span>
                <span className="flex-1 nova-text-p-base text-[#000000AD]">
                  <Md inline>{opt.text}</Md>
                </span>
                {isOptCorrect && (
                  <CheckboxChecked color="#84B496" checkColor="white" />
                )}
                {isWrong && (
                  <CheckboxError />
                )}
              </button>
            );
          })}
        </div>

        <div className="mx-auto mt-3.5 h-px w-full bg-[#F4F4F5]" />

        {!confirmed || !data.feedback ? (
          <Button
            size="l"
            type="button"
            disabled={!localSelected || !data.feedback}
            onClick={handleConfirm}
            isLoading={!data.feedback}
            className="mt-3.5 flex items-center gap-1 self-starttracking-[0px] hover:opacity-80"
          >
            Confirm
          </Button>
        ) : (
          <div className="mt-3.5 nova-text-p-base text-[#000000AD]">
            <Md>{data.feedback}</Md>
          </div>
        )}
      </QuestionWrapper>

      {confirmed && (
        <ModelAnswerBlock
          isCorrect={isCorrect}
          marksEarned={isCorrect ? 1 : 0}
          marksTotal={1}
          modelAnswer={data.feedback || "No model answer available."}
        />
      )}
    </div>
  );
}

function OpenQuestionBlock({ segment, savedAnswer, onSubmit }: QuestionBlockProps) {
  const [localAnswer, setLocalAnswer] = useState("");
  const data = parseOpenQuestion(segment.body, segment.label);

  // Use savedAnswer as source of truth when available
  const submitted = !!savedAnswer;
  const answer = savedAnswer?.answer ?? localAnswer;
  const isGrading = savedAnswer?.grading ?? false;
  const answerReady = submitted && !isGrading && (savedAnswer && savedAnswer.isCorrect !== null || data.modelAnswer)

  function handleSubmit() {
    if (!localAnswer.trim()) return;
    onSubmit?.({
      answer: localAnswer.trim(),
      questionType: "open",
      isCorrect: null,
      earnedMarks: 0,
      totalMarks: data.marks,
      feedback: null,
      recommendations: null,
      grading: false,
    });
  }

  return (
    <div className="flex flex-col gap-1.5">
      <QuestionWrapper>
        <div className="mt-2.5 nova-text-label-base text-[#242529]">
          <Md>{data.question}</Md>
        </div>

        <div className="mx-auto mt-2.5 h-px w-full bg-[#F4F4F5]" />

        {answerReady ? (
          <div className="mt-3 nova-text-p-base text-[#242529AD]">
            {answer}
          </div>
        ) : (
          <>
            <textarea
              value={localAnswer}
              onChange={(e) => setLocalAnswer(e.target.value)}
              disabled={submitted}
              placeholder="Write your answer..."
              rows={4}
              className="mt-3 w-full resize-none rounded-lg px-2 py-2 nova-text-label-medium text-[#242529] outline-none placeholder:text-[#A1A1AA]"
            />

            <Button
              iconOnly
              type="button"
              disabled={!localAnswer.trim() || submitted}
              isLoading={submitted}
              onClick={handleSubmit}
              className="mt-0 flex items-center gap-1 self-start hover:opacity-80"
            >
              <PaperAirplaneIcon />
            </Button>
          </>
        )}

      </QuestionWrapper>

      {submitted && !isGrading && (
        savedAnswer && savedAnswer.isCorrect !== null ? (
          <ModelAnswerBlock
            isCorrect={savedAnswer.isCorrect ?? false}
            marksEarned={savedAnswer.earnedMarks}
            marksTotal={data.marks}
            feedback={savedAnswer.feedback ?? undefined}
            recommendations={savedAnswer.recommendations ?? undefined}
            modelAnswer={data.modelAnswer || "No model answer available."}
          />
        ) : data.modelAnswer && (
          <ModelAnswerBlock
            isCorrect={false}
            marksEarned={0}
            marksTotal={data.marks}
            modelAnswer={data.modelAnswer}
          />
        )
      )}
    </div>
  );
}

export function QuestionBlock({ segment, savedAnswer, onSubmit }: QuestionBlockProps) {
  if (segment.subtype === "mcq") {
    return <McqQuestionBlock segment={segment} savedAnswer={savedAnswer} onSubmit={onSubmit} />;
  }
  return <OpenQuestionBlock segment={segment} savedAnswer={savedAnswer} onSubmit={onSubmit} />;
}
