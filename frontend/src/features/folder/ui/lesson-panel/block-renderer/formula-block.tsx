import { memo } from "react";

import { LessonCard } from "@/shared/ui/lesson-card";

import { Md } from "./md";

type FormulaBlockProps = {
  title?: string;
  body: string;
};

export const FormulaBlock = memo(function FormulaBlock({ title, body }: FormulaBlockProps) {
  return (
    <LessonCard className="flex min-w-0 flex-col items-stretch px-3.5 py-4">
      {title && (
        <span className="mb-2 self-start nova-text-label-tiny-sb text-[#A1A1AA]">
          {title}
        </span>
      )}
      <div className="min-w-0 max-w-full nova-text-label-base text-[#242529]">
        <Md>{body}</Md>
      </div>
    </LessonCard>
  );
});
