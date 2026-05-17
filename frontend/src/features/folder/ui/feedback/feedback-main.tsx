"use client";

import { useState } from "react";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { cn } from "@/shared/lib";
import { ChevronRightIcon, LightbulbIcon, SourceArrowIcon } from "@/shared/assets/icons";
import type { FeedbackNote } from "@/features/folder/api/feedback-api";
import { Button } from "@/shared";
import { MarkdownContent } from "@/features/chat/ui/markdown-content";

const REMARK_PLUGINS = [remarkMath];
const REHYPE_PLUGINS = [rehypeKatex];

type CoveredMistakeProps = {
  note: FeedbackNote;
};

function CoveredMistake({ note }: CoveredMistakeProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="flex flex-col gap-y-7 rounded-[16px] border border-[#F2F2F4] p-4 nova-shadow-bottom">
      <div className="flex gap-x-3">
        <LightbulbIcon className="mt-0.5 shrink-0" />
        <div className="flex flex-col gap-y-2">
          <MarkdownContent
            content={note.correction}
            remarkPlugins={REMARK_PLUGINS}
            rehypePlugins={REHYPE_PLUGINS}
            className="nova-text-label-medium-regular text-[#6A6B6E]"
          />
          <div className="flex flex-wrap gap-1.5">
            {note.source_type && (
              <div className="flex items-start gap-0 rounded-[12px] bg-[#F4F4F5] px-2 py-0.5 nova-text-label-tiny text-[#A1A1AA]">
                <SourceArrowIcon className="size-4 shrink-0 translate-y-0.75 [&_path]:stroke-current" />
                <MarkdownContent
                  content={`${note.source_type === "test" ? "Тест" : "Объяснение"} — ${note.topic}`}
                  remarkPlugins={REMARK_PLUGINS}
                  rehypePlugins={REHYPE_PLUGINS}
                  className="nova-text-label-tiny text-[#A1A1AA] [&_p]:m-0"
                />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-[#F4F4F5] nova-text-label-small text-[#242529]">
        <button
          type="button"
          className="flex w-full gap-x-2 py-2.5 pl-3"
          onClick={() => setIsOpen((p) => !p)}
        >
          <div className="flex size-5 items-center justify-center">
            <ChevronRightIcon
              className={cn(
                "size-3 stroke-[2.5] stroke-[#242529] transition-all",
                isOpen && "rotate-90",
              )}
            />
          </div>
          Моя ошибка
        </button>

        <div
          className={cn(
            "grid transition-all",
            isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <MarkdownContent
              content={note.mistake}
              remarkPlugins={REMARK_PLUGINS}
              rehypePlugins={REHYPE_PLUGINS}
              className="pl-3 pb-2 font-normal text-[#6A6B6E]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

type FeedbackMainProps = {
  seeCount: number;
  reviewCount: number;
  coveredNotes: FeedbackNote[];
  navigateSee: VoidFunction;
  navigateReview: VoidFunction;
};

export function FeedbackMain({
  seeCount,
  reviewCount,
  coveredNotes,
  navigateSee,
  navigateReview,
}: FeedbackMainProps) {
  return (
    <div className="flex flex-col gap-y-5 py-4">
      <div className="flex gap-x-2 nova-text-label-small text-[#242529]">
        <Button
          onClick={navigateSee}
        >
          Посмотреть ошибки ({seeCount})
        </Button>
        <Button
          variant="plain"
          onClick={navigateReview}
        >
          Закрепить ошибки ({reviewCount})
        </Button>
      </div>

      <div className="flex max-w-176 flex-col gap-y-1.5 rounded-[16px] border border-[#F2F2F4] p-1.5">
        <p className="mb-2.5 ml-2.5 nova-text-h-small-sb text-[#242529]">
          Уже разобрали
        </p>
        {coveredNotes.length === 0 ? (
          <p className="pb-2 px-2.5 nova-text-label-medium text-[#A1A1AA]">
            Когда разберёшь ошибку и закрепишь её, она появится здесь.
          </p>
        ) : (
          coveredNotes.map((note) => (
            <CoveredMistake key={note.id} note={note} />
          ))
        )}
      </div>
    </div>
  );
}
