import { memo, useMemo } from "react";

import { LessonCard } from "@/shared/ui/lesson-card";

type LessonIntroProps = {
  content: string;
  title: string;
};

function extractDescription(content: string): string {
  const lines = content.split("\n");
  const result: string[] = [];
  let pastHeading = false;

  for (const line of lines) {
    if (/^#\s/.test(line)) {
      pastHeading = true;
      continue;
    }
    if (pastHeading) {
      result.push(line);
    }
  }

  return result.join("\n").trim();
}

export const LessonIntro = memo(function LessonIntro({ content, title }: LessonIntroProps) {
  const description = useMemo(() => extractDescription(content), [content]);

  return (
    <LessonCard className="pt-3.5 px-1.5 pb-1.5">
      <h1 className="nova-text-h-small text-[#242529] px-3.5">
        {title}
      </h1>

      {description && (
        <LessonCard className="mt-3 flex gap-3 p-3.5">
          <div className="w-1 shrink-0 self-stretch rounded-full bg-[#E7DFDA]" />
          <p className="nova-text-p-base text-[#242529AD]">
            {description}
          </p>
        </LessonCard>
      )}
    </LessonCard>
  );
});
