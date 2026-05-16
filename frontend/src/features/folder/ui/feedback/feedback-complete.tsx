"use client";

import { Button } from "@/shared";
import { CircleCheckIcon } from "@/shared/assets/icons";

type FeedbackCompleteProps = {
  message: string;
  completedCount: number;
  totalCount: number;
  actionLabel?: string;
  onAction?: VoidFunction;
  /** When false, hides the weekly progress bar and “n of m” (e.g. Review empty state). */
  showWeekProgress?: boolean;
};

export function FeedbackComplete({
  message,
  completedCount,
  totalCount,
  actionLabel,
  onAction,
  showWeekProgress = true,
}: FeedbackCompleteProps) {
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 100;

  return (
    <div className="flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-[640px]">
        <div className="rounded-[20px] border border-[#F2F2F4] p-1.5">
          <p className="m-2.5 mb-6.5 nova-text-h-small-sb text-[#242529]">
            Collected feedback for the week
          </p>

          <div className="flex flex-col items-center rounded-[12px] border border-[#F2F2F4] px-6 py-4 nova-shadow-bottom">
            <CircleCheckIcon className="size-20 text-white" />

            <p className="mt-3 whitespace-pre-line text-center nova-text-p-base text-[#6A6B6E]">
              {message}
            </p>

            {actionLabel && onAction && (
              <Button
                variant="outline"
                type="button"
                onClick={onAction}
                className="mt-3 mb-7.5"
              >
                {actionLabel}
              </Button>
            )}
          </div>
        </div>
        {showWeekProgress ? (
          <div className="flex items-center gap-3 px-4 py-5">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-[#E8E5E1]">
              <div
                className="h-full rounded-full bg-[#D7C8C0] transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="shrink-0 nova-text-label-tiny text-[#A1A1AA]">
              {completedCount} of {totalCount}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
