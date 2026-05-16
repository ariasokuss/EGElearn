"use client";

import { useState } from "react";

import { CheakIcon, ChevronDownIcon, EyeBigIcon, IdeaLampIcon } from "@/shared/assets/icons";
import { cn } from "@/shared/lib";

import { Md } from "../block-renderer/md";

function SmallXIcon({ className }: { className?: string }) {
  return (
    <svg
      className={cn(className)}
      width="10"
      height="10"
      viewBox="0 0 10 10"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M2.5 2.5L7.5 7.5M7.5 2.5L2.5 7.5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

type Props = {
  points: number;
  totalPoints: number;
  feedback?: string | null;
  recommendation?: string | null;
  modelAnswer?: string | null;
};

export function QuestionReviewFeedbackCard({
  points,
  totalPoints,
  feedback,
  recommendation,
  modelAnswer,
}: Props) {
  const [modelOpen, setModelOpen] = useState(false);
  const feedbackTrim = feedback?.trim() ?? "";
  const recTrim = recommendation?.trim() ?? "";
  const modelTrim = modelAnswer?.trim() ?? "";
  const hasModel = modelTrim.length > 0;

  const pct =
    totalPoints > 0 ? Math.min(100, Math.max(0, (points / totalPoints) * 100)) : 50;
  const showRecommendation = recTrim.length > 0;
  const hasMiddle = feedbackTrim.length > 0 || showRecommendation;
  const scoreTone: "red" | "green" | "amber" =
    pct < 30 ? "red" : pct > 70 ? "green" : "amber";

  if (!hasMiddle && !hasModel && totalPoints <= 0) {
    return null;
  }

  return (
    <div className="mt-6 rounded-2xl border border-[#F4F4F5] bg-white">
      <div className="flex items-center gap-3 border-b border-[#F4F4F5] px-[16px] py-[16px]">
        <div
          className={cn(
            "flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full",
            scoreTone === "red" && "bg-[#C77785]",
            scoreTone === "green" && "bg-[#83B496]",
            scoreTone === "amber" && "bg-[#D1C1B7]",
          )}
        >
          {scoreTone === "red" ? (
            <SmallXIcon className=" text-white" />
          ) : (
            <CheakIcon className="h-[12px] w-[12px] overflow-visible text-white" aria-hidden />
          )}
        </div>
        <p className="nova-text-label-tiny-sbd text-[#242529]">
          {points} / {totalPoints} marks earned
        </p>
      </div>

      {hasMiddle ? (
        <div className="divide-y divide-[#F4F4F5] px-[16px]">
          {feedbackTrim ? (
            <div className="flex items-start gap-6 py-4">
              <CheakIcon
                className="mt-0.5 h-[16px] w-[17px] shrink-0 overflow-visible text-[#242529]/68"
                aria-hidden
              />
              <div className="min-w-0 flex-1 nova-text-p-base text-[#242529]/68">
                <Md>{feedbackTrim}</Md>
              </div>
            </div>
          ) : null}
          {showRecommendation ? (
            <div className="flex items-start gap-6 py-4">
              <IdeaLampIcon
                className="mt-0.5 h-[23px] w-[17px] shrink-0 overflow-visible text-[#242529]/68"
                aria-hidden
              />
              <div className="min-w-0 flex-1 nova-text-label-medium-regular text-[#242529]/68">
                <Md>{recTrim}</Md>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasModel ? (
        <div className="border-t border-[#F4F4F5]">
          <button
            type="button"
            onClick={() => setModelOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-3 px-[16px] py-[16px] text-left transition-colors hover:bg-[#FAFAFA]"
            aria-expanded={modelOpen}
          >
            <span className="flex items-center gap-4.5">
              <EyeBigIcon
                className="shrink-0 overflow-visible text-[#242529]/68"
                aria-hidden
              />
              <span className="nova-text-p-base text-[#242529]/68">
                Model answer
              </span>
            </span>
            <ChevronDownIcon
              className={cn(
                "h-4 w-4 shrink-0 text-[#A1A1AA] transition-transform duration-300",
                modelOpen && "-rotate-180",
              )}
            />
          </button>
          <div
            className={cn(
              "grid overflow-hidden transition-[grid-template-rows] duration-300 ease-out",
              modelOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
            )}
          >
            <div className="min-h-0 overflow-hidden">
              <div
                className={cn(
                  "border-t border-[#F4F4F5] px-[16px] py-[16px] transition-all duration-300 ease-out",
                  modelOpen
                    ? "opacity-100 translate-y-0"
                    : "opacity-0 -translate-y-1",
                )}
              >
                <div className="pr-4 pb-4 pt-1">
                  <div className="flex gap-4">
                    <span
                      aria-hidden
                      className="w-[4px] shrink-0 self-stretch rounded-full bg-[#84B496]"
                    />
                    <div className="min-w-0 flex-1 break-words nova-text-label-medium-regular text-[#242529] [&_p]:min-w-0 [&_pre]:max-w-full [&_pre]:overflow-x-auto">
                      <Md>{modelTrim}</Md>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
