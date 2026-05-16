import { memo } from "react";

import { LessonCard } from "@/shared/ui/lesson-card";

import { Md } from "./md";

type ContentBlockProps = {
  title?: string;
  body: string;
};

export const ContentBlock = memo(function ContentBlock({ title, body }: ContentBlockProps) {
  return (
    <LessonCard className="flex gap-3 p-3.5">
      <div className="w-1 shrink-0 self-stretch rounded-full bg-[#E7DFDA]" />
      <div className="flex min-w-0 flex-col gap-1">
        {title && (
          <span className="nova-text-label-tiny-sb text-[#242529]">
            {title}
          </span>
        )}
        <div className="nova-text-p-base text-[#242529AD]">
          <Md>{body}</Md>
        </div>
      </div>
    </LessonCard>
  );
});
