"use client";

import { useEffect, useState } from "react";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import {
  LightbulbIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  RetryIcon,
  CheckedIcon,
  SourceArrowIcon,
} from "@/shared/assets/icons";
import type { FeedbackNote } from "@/features/folder/api/feedback-api";
import { updateNoteStatus } from "@/features/folder/api/feedback-api";
import { FeedbackComplete } from "./feedback-complete";
import { Button } from "@/shared";
import { MarkdownContent } from "@/features/chat/ui/markdown-content";

const REMARK_PLUGINS = [remarkMath];
const REHYPE_PLUGINS = [rehypeKatex];

type FeedbackSeeProps = {
  notes: FeedbackNote[];
  onNoteCompleted: (noteId: string) => void;
  onRefresh: VoidFunction;
  completedCount: number;
  totalCount: number;
  onNavigateReview: VoidFunction;
  onCurrentNoteChange?: (note: FeedbackNote | null) => void;
};

export function FeedbackSee({ notes, onNoteCompleted, onRefresh, completedCount, totalCount, onNavigateReview, onCurrentNoteChange }: FeedbackSeeProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const safeIndex = notes.length > 0 ? Math.min(currentIndex, notes.length - 1) : 0;
  const note = notes[safeIndex] ?? null;

  useEffect(() => {
    onCurrentNoteChange?.(note);
  }, [note, onCurrentNoteChange]);

  if (notes.length === 0) {
    return (
      <FeedbackComplete
        message={"На сегодня все ошибки разобраны.\nОтличная работа!"}
        completedCount={completedCount}
        totalCount={totalCount}
        actionLabel="Закрепить ошибки"
        onAction={onNavigateReview}
      />
    );
  }

  if (!note) return null;

  // Keep this aligned with Review: count unresolved items, not distance to list end.
  const remaining = notes.length;

  const handleGotIt = async () => {
    setSubmitting(true);
    try {
      const updated = await updateNoteStatus(note.id, "review");
      if (updated) {
        onNoteCompleted(note.id);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handlePrev = () => setCurrentIndex((i) => Math.max(0, i - 1));
  const handleNext = () => setCurrentIndex((i) => Math.min(notes.length - 1, i + 1));

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="flex flex-col items-center px-4 pt-8 pb-4.25">
        <div className="w-full max-w-[640px]">
          <div className="rounded-[20px] border border-[#F2F2F4] p-1.5 nova-shadow-bottom">
            <p className="m-4 mb-6.5 nova-text-h-small-sb text-[#242529]">
              Ошибки, которые ещё нужно разобрать
            </p>
  
            <div className="rounded-[16px] border border-[#F2F2F4] p-3.5 pb-6 nova-shadow-bottom">
              <div className="mb-5 flex gap-x-3">
                <LightbulbIcon className="mt-0.5 shrink-0" />
                <div className="flex flex-col gap-y-2">
                  <MarkdownContent
                    content={note.mistake}
                    remarkPlugins={REMARK_PLUGINS}
                    rehypePlugins={REHYPE_PLUGINS}
                    className="nova-text-label-medium-regular text-[#6A6B6E]"
                  />
                  <div className="flex flex-wrap gap-1.5">
                    <div className="flex items-start gap-0 rounded-[12px] bg-[#F4F4F5] px-2 py-0.5 nova-text-label-tiny text-[#A1A1AA]">
                      <SourceArrowIcon className="size-4 shrink-0 translate-y-0.75 [&_path]:stroke-current" />
                      <MarkdownContent
                        content={`${note.source_type === "test" ? "Тест" : "Объяснение"} — ${note.topic}`}
                        remarkPlugins={REMARK_PLUGINS}
                        rehypePlugins={REHYPE_PLUGINS}
                        className="nova-text-label-tiny text-[#A1A1AA] [&_p]:m-0"
                      />
                    </div>
                  </div>
                </div>
              </div>
  
              <div className="border-t border-[#F4F4F5] pt-2.5">
                <p className="mb-2 nova-text-label-small text-[#242529]">
                  Объяснение
                </p>
                <MarkdownContent
                  content={note.correction}
                  remarkPlugins={REMARK_PLUGINS}
                  rehypePlugins={REHYPE_PLUGINS}
                  className="nova-text-label-small text-[#242529]"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center gap-3 pb-5">
        <div className="flex items-center gap-2 rounded-full border border-[#F2F2F4] px-1.5 py-1.5 nova-shadow-bottom">
          <Button
            variant="plain"
            iconOnly
            type="button"
            onClick={onRefresh}
            className="flex items-center justify-center"
            aria-label="Вернуться к последней ошибке"
          >
            <RetryIcon className="size-4" />
          </Button>

          <div className="h-3.5 w-px rounded-full bg-[#E8E5E1]" />

          <Button
            variant="plain"
            iconOnly
            type="button"
            onClick={handlePrev}
            disabled={safeIndex === 0}
            className="flex items-center justify-center"
            aria-label="Предыдущая ошибка"
          >
            <ChevronLeftIcon className="size-3.5" />
          </Button>

          <span className="px-2 nova-text-label-tiny text-[#71717A]">
            Осталось: {remaining}
          </span>

          <Button
            variant="plain"
            iconOnly
            type="button"
            onClick={handleNext}
            disabled={safeIndex >= notes.length - 1}
            className="flex items-center justify-center"
            aria-label="Следующая ошибка"
          >
            <ChevronRightIcon className="size-3.5" />
          </Button>
          
          <div className="h-5 w-px bg-[#E8E5E1]" />
  
          <Button
            variant="default"
            size="l"
            type="button"
            onClick={handleGotIt}
            disabled={submitting}
            isLoading={submitting}
            className="flex items-center gap-1"
          >
            Понял
            <CheckedIcon className="size-5.5" />
          </Button>

        </div>

      </div>
    </div>
  );
}
