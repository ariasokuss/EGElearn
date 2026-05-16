"use client";

import { CheakIcon } from "@/shared/assets/icons";
import { cn } from "@/shared/lib";

/** Same circle + icon sizes as `QuestionReviewFeedbackCard` marks header. */
const MARKS_ICON_WRAP = "flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full";

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
  variant: "correct" | "incorrect";
};

export function McqGradedTrailingIcon({ variant }: Props) {
  return (
    <span
      className={cn(
        MARKS_ICON_WRAP,
        variant === "correct" ? "bg-[#83B496]" : "bg-[#C77785]",
      )}
      aria-hidden
    >
      {variant === "correct" ? (
        <CheakIcon className="h-[12px] w-[12px] overflow-visible text-white" aria-hidden />
      ) : (
        <SmallXIcon className="text-white" />
      )}
    </span>
  );
}
