"use client";

import { cn } from "@/shared/lib";

import { Md } from "../block-renderer/md";
import { parseMcq, type DirectiveSegment } from "../block-renderer/parse-content";

type Props = {
  segment: DirectiveSegment;
  selected: string | null;
  onSelect: (key: string) => void;
};

export function TestMcqQuestion({ segment, selected, onSelect }: Props) {
  const data = parseMcq(segment.body);
  return (
    <div className="flex flex-col gap-4">
      <p className="nova-text-label-base text-[#242529]">
        <Md inline>{data.question}</Md>
      </p>
      <div className="flex flex-col gap-2">
        {data.options.map((opt) => (
          <button key={opt.key} type="button" onClick={() => onSelect(opt.key)}
            className={cn(
              "flex items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
              selected === opt.key ? "border-[#3F3C47] bg-[#FAFAF8]" : "border-[#E8E5E1] bg-white hover:bg-[#FAFAF8]"
            )}>
            <span className={cn(
              "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border nova-text-label-base",
              selected === opt.key ? "border-[#3F3C47] text-[#3F3C47]" : "border-[#D1CEC8] text-[#9B97A3]"
            )}>
              {opt.key}
            </span>
            <span className="nova-text-p-base text-[#242529]">
              <Md inline>{opt.text}</Md>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
