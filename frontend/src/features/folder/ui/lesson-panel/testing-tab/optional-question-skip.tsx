"use client";

import { cn } from "@/shared/lib";

export type OptionalQuestionSkipProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
};

export function OptionalQuestionSkip({
  checked,
  onCheckedChange,
  disabled = false,
}: OptionalQuestionSkipProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "flex items-center gap-2.5 self-start px-3 py-2 rounded-full nova-text-label-small transition-all select-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          checked
            ? "bg-[#F4F0EE] text-[#242529]"
            : "text-[#72706F] hover:bg-[#F9F7F6] hover:text-[#242529]"
        )}
      >
        <div className={cn(
          "flex items-center justify-center size-4 shrink-0 rounded border transition-all",
          checked
            ? "bg-[#242529] border-[#242529]"
            : "border-[#D4D4D8]"
        )}>
          {checked && (
            <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
              <path d="M1 3L3.5 5.5L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </div>
        Пропустить дополнительный вопрос
      </button>
      <p className="nova-text-label-tiny text-[#71717A] pl-3 select-none">
        Этот вопрос не будет учитываться в итоговом балле.
      </p>
    </div>
  );
}
