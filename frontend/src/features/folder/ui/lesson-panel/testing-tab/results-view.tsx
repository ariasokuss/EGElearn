"use client";

import { useRef } from "react";
import { CircularProgressbar } from "react-circular-progressbar";
import { scoreMessage } from "./utils";
import { CheckIcon, XMarkIcon } from "@/shared/assets/icons";
import { SessionResultsOut } from "@/shared/api/generated/model";
import { Button, cn } from "@/shared";
import { useAutoHideScrollbar } from "@/shared/lib";
import { Md } from "../block-renderer/md";

type Props = {
  results: SessionResultsOut;
  primaryButtonText?: string;
  secondaryButtonText?: string;
  onPrimaryClick: VoidFunction;
  onSecondaryClick: VoidFunction;
  onXClick?: VoidFunction;
  onGoToQuestion?: (questionIndex: number) => void;
  resultsCloseInsetPastPaper?: boolean;
};

export function ResultsView({
  results,
  onPrimaryClick,
  onSecondaryClick,
  primaryButtonText,
  secondaryButtonText,
  onXClick,
  onGoToQuestion,
  resultsCloseInsetPastPaper,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useAutoHideScrollbar(scrollRef);

  const totalMarks = results.total_marks
  const earnedMarks = results.marks ?? 0;
  const percent = totalMarks > 0 ? Math.round((earnedMarks / totalMarks) * 100) : 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {onXClick &&
        <div
          className={cn(
            "shrink-0 pb-2 border-[#E8E5E180]",
            resultsCloseInsetPastPaper
              ? "overflow-visible pt-3"
              : "overflow-x-auto",
          )}
        >
          <div className="grid w-full min-w-full grid-cols-[auto_1fr_auto] items-center gap-4 ">
            <Button
              variant="plain"
              iconOnly
              rounded={false}
              type="button"
              onClick={onXClick}
              className="flex shrink-0 items-center justify-center"
              style={
                resultsCloseInsetPastPaper ? { marginLeft: 20 } : undefined
              }
              aria-label="Выйти из теста"
            >
              <XMarkIcon className="size-4.5" />
            </Button>
          </div>
        </div>
      }
      <div
        ref={scrollRef}
        className="auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto"
      >
        <div className="w-full max-w-177 mx-auto py-6">
          <div className="flex flex-col gap-y-6 justify-center items-center w-full py-6 border border-[#F4F4F5] rounded-[16px]">
            <div className="w-full max-w-58 flex flex-col gap-y-3 items-center">
              <CircularProgressbar
                value={percent}
                text={`${percent}%`}
                className="size-27"
                strokeWidth={8}
                styles={{
                  path: {
                    stroke: "#D1C1B7",
                    strokeLinecap: "round",
                  },
                  trail: {
                    stroke: "#F1ECE9",
                  },
                  text: {
                    textAnchor: "middle",
                    dominantBaseline: "middle",
                    fontFamily: "var(--font-inter)",
                    fontSize: 16,
                    fontWeight: 600,
                    lineHeight: 24,
                    color: "#242529"
                  }
                }}
              />

              <p className="nova-text-h-small text-[#242529]">{scoreMessage(percent)}</p>
              <p className="text-center nova-text-label-medium text-[#6A6B6E]">
                {earnedMarks} / {totalMarks} баллов
              </p>
            </div>

            <div className="flex gap-x-2 nova-text-label-small text-[#242529]">
              <Button
                onClick={onPrimaryClick}
              >
                {primaryButtonText ?? "Посмотреть ответы"}
              </Button>
              <Button
                variant="plain"
                onClick={onSecondaryClick}
              >
                {secondaryButtonText ?? "Пройти заново"}
              </Button>
            </div>
          </div>

          <div className="mt-3 border border-[#F4F4F5] rounded-[16px] divide-y divide-[#F4F4F5]">
            <p className="px-[14px] py-[14px] nova-text-label-tiny-sb text-[#242529]">Разбор вопросов</p>
            {results.questions.map((result, i) => {
              const isSkipped = result.is_skipped === true;
              const qPercent = result.max_points > 0 ? Math.round(((result.points ?? 0) / result.max_points) * 100) : 0;
              return (
                <div
                  key={i}
                  className={`flex w-full items-center justify-between gap-x-3 px-[14px] py-[14px]${isSkipped ? " opacity-60" : ""}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className={`nova-text-label-tiny-sb text-[#242529] whitespace-nowrap text-ellipsis overflow-x-hidden overflow-y-hidden min-w-0${isSkipped ? " line-through" : ""}`}>
                      Вопрос {i + 1}.&#32;
                      <Md oneLine>{result.question}</Md>
                    </p>
                    <p className="mt-[4px] nova-text-p-base text-[#6A6B6E]">{result.relation}</p>
                  </div>
                  <div className="flex w-[172px] justify-between gap-2">
                    {onGoToQuestion ? (
                      <button
                        type="button"
                        onClick={() => onGoToQuestion(i)}
                        className="flex gap-x-1.5 items-center rounded-full px-2.5 py-1.5 nova-text-label-small transition-colors hover:bg-[#F9F9F9] nova-shadow-sm"
                      >
                        К вопросу
                      </button>
                    ) : null}
                    {isSkipped ? (
                      <div className="flex gap-x-1.5 items-center">
                        <span className="rounded-full bg-[#F4F4F5] px-2 py-0.5 nova-text-label-tiny text-[#71717A]">
                          Пропущено
                        </span>
                      </div>
                    ) : (
                      <div className="flex gap-x-1.5 items-center">
                        <p className="nova-text-label-small text-[#242529]">{result.points ?? 0}/{result.max_points}</p>
                        {qPercent === 100
                          ? <CheckIcon />
                          : <CircularProgressbar
                            value={qPercent}
                            strokeWidth={14}
                            className="size-5"
                            styles={{
                              path: {
                                stroke: "#C1B1A6"
                              },
                              trail: {
                                stroke: "#E8DFD9",
                              },
                            }}
                          />
                        }
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
