"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "react-toastify";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { cn } from "@/shared/lib";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PaperAirplaneIcon,
  CheakIcon,
  XMarkIcon,
  EyeIcon,
  ChevronDownIcon,
} from "@/shared/assets/icons";
import type { FeedbackNote, NoteAnswerResult } from "@/features/folder/api/feedback-api";
import { answerNote, updateNoteStatus } from "@/features/folder/api/feedback-api";
import { FeedbackComplete } from "./feedback-complete";
import { Button } from "@/shared";
import { MarkdownContent } from "@/features/chat/ui/markdown-content";
import { FEEDBACK_REVIEW_SUBMIT_TOAST_ID } from "./feedback-review-constants";

const REMARK_PLUGINS = [remarkMath];
const REHYPE_PLUGINS = [rehypeKatex];

function SmallInfoIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M9 9L9.04149 8.97926C9.61461 8.6927 10.2599 9.21034 10.1045 9.83198L9.39549 12.668C9.24009 13.2897 9.88539 13.8073 10.4585 13.5207L10.5 13.5M18.75 9.75C18.75 14.7206 14.7206 18.75 9.75 18.75C4.77944 18.75 0.75 14.7206 0.75 9.75C0.75 4.77944 4.77944 0.75 9.75 0.75C14.7206 0.75 18.75 4.77944 18.75 9.75ZM9.75 6H9.7575V6.0075H9.75V6Z" stroke="#242529" strokeOpacity="0.68" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function reviewSubmitToast(message: string) {
  toast.error(message, { toastId: FEEDBACK_REVIEW_SUBMIT_TOAST_ID });
}

type ReviewCardProps = {
  note: FeedbackNote;
  onAnswered: (noteId: string, isCorrect: boolean) => void;
};

function ReviewCard({ note, onAnswered }: ReviewCardProps) {
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<NoteAnswerResult | null>(null);
  const [modelOpen, setModelOpen] = useState(false);

  useEffect(() => {
    toast.dismiss(FEEDBACK_REVIEW_SUBMIT_TOAST_ID);
  }, [note.id]);

  const question = note.review_question;
  if (!question) return null;

  const handleSubmit = async () => {
    if (!answer.trim() || submitting) return;
    setSubmitting(true);
    toast.dismiss(FEEDBACK_REVIEW_SUBMIT_TOAST_ID);
    try {
      const res = await answerNote(note.id, answer.trim());
      if (!res) {
        reviewSubmitToast("Could not submit your answer. Please try again.");
        return;
      }
      setResult(res);
      if (res.is_correct) {
        const updated = await updateNoteStatus(note.id, "complete");
        if (!updated) {
          setResult(null);
          reviewSubmitToast("Could not save your progress. Please try again.");
          return;
        }
      }
      onAnswered(note.id, res.is_correct);
    } catch {
      reviewSubmitToast("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const scoreTone: "red" | "green" | "amber" =
    result
      ? result.total_marks > 0
        ? (result.earned_marks / result.total_marks) * 100 < 30
          ? "red"
          : (result.earned_marks / result.total_marks) * 100 > 70
            ? "green"
            : "amber"
        : "amber"
      : "amber";

  const feedbackLines = result?.feedback
    ? result.feedback.split("\n").filter((l) => l.trim())
    : [];
  const recommendationLines = result?.recommendations
    ? result.recommendations.split("\n").filter((l) => l.trim())
    : [];

  return (
    <div className="w-full max-w-[640px]">
      <div className="rounded-[20px] border border-[#F2F2F4] p-1.5">
        <p className="mx-3.5 mt-2.5 mb-6.5 nova-text-h-small-sb text-[#242529]">
          Let&apos;s recall :)
        </p>

        <div className="rounded-[16px] border border-[#F2F2F4] px-3.5 pb-3.5 pt-2.5 nova-shadow-bottom">
          <MarkdownContent
            content={question.question}
            remarkPlugins={REMARK_PLUGINS}
            rehypePlugins={REHYPE_PLUGINS}
            className="pb-2.5 nova-text-label-small text-[#242529]"
          />

          <div className="border-t border-[#F4F4F5]" />

          <div className="pt-3">
            <textarea
              className="pl-2 max-h-[180px] min-h-[120px] w-full resize-none overflow-y-auto border-none bg-transparent nova-text-label-medium-regular text-[#242529] placeholder:text-[#A1A1AA] outline-none"
              placeholder="Write your answer..."
              value={answer}
              onChange={(e) => {
                toast.dismiss(FEEDBACK_REVIEW_SUBMIT_TOAST_ID);
                setAnswer(e.target.value);
              }}
              onKeyDown={handleKeyDown}
              disabled={!!result}
            />
            {!result && (
              <div className="pt-2">
                <Button
                  iconOnly
                  type="button"
                  onClick={handleSubmit}
                  disabled={!answer.trim() || submitting}
                  isLoading={submitting}
                  aria-label="Submit answer"
                  className="flex shrink-0 items-center justify-center rounded-full"
                >
                  <PaperAirplaneIcon />
                </Button>
              </div>
            )}
          </div>
        </div>

        {result && (
          <div className="mt-1.5 overflow-hidden rounded-[12px] border border-[#F4F4F5]">
            <div className="flex gap-3.5 border-b border-[#F4F4F5] p-3.5">
              <div
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-full",
                  scoreTone === "red" && "bg-[#C77785]",
                  scoreTone === "green" && "bg-[#84B496]",
                  scoreTone === "amber" && "bg-[#CEC397]",
                )}
              >
                {scoreTone === "red"
                  ? <XMarkIcon className="size-3 overflow-visible text-white stroke-[#FFF]" aria-hidden />
                  : <CheakIcon className="size-3 overflow-visible text-white" aria-hidden />
                }
              </div>
              <div>
                <p className="nova-text-label-tiny-sb text-[#242529]">
                  {result.earned_marks}/{result.total_marks} marks earned
                </p>
                <p className="nova-text-p-base text-[#71717A]">
                  {result.is_correct
                    ? "Well done, you corrected this mistake!"
                    : "This question needs more practice!"}
                </p>
              </div>
            </div>

            {(feedbackLines.length > 0 || recommendationLines.length > 0) && (
              <div className="p-3.5">
                {feedbackLines.map((line, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="mt-1 text-[#71717A]">
                      <CheakIcon className="size-4 overflow-visible" />
                    </div>
                    <MarkdownContent
                      content={line}
                      remarkPlugins={REMARK_PLUGINS}
                      rehypePlugins={REHYPE_PLUGINS}
                      className="nova-text-p-base text-[#3F3F47]"
                    />
                  </div>
                ))}
                {recommendationLines.map((line, i) => (
                  <div key={i} className="flex items-start gap-3 pt-3">
                    <div className="mt-0.5 text-[#71717A]">
                      <SmallInfoIcon />
                    </div>
                    <MarkdownContent
                      content={line}
                      remarkPlugins={REMARK_PLUGINS}
                      rehypePlugins={REHYPE_PLUGINS}
                      className="nova-text-p-base text-[#3F3F47]"
                    />
                  </div>
                ))}
              </div>
            )}

            {question.model_answer && (
              <div className="border-t border-[#F4F4F5]">
                <button
                  type="button"
                  onClick={() => setModelOpen((o) => !o)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-[#FAFAFA]"
                  aria-expanded={modelOpen}
                >
                  <span className="flex items-center justify-center gap-3">
                    <EyeIcon className="size-4 shrink-0 justify-center overflow-visible text-[#71717A]" />
                    <span className="nova-text-p-base">
                      Model answer
                    </span>
                  </span>
                  <ChevronDownIcon
                    className={cn(
                      "size-4 shrink-0 text-[#A1A1AA] transition-transform duration-200",
                      modelOpen && "-rotate-180",
                    )}
                  />
                </button>
                <div
                  className={cn(
                    "grid overflow-hidden transition-[grid-template-rows] duration-200 ease-out",
                    modelOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                  )}
                >
                  <div className="min-h-0 overflow-hidden">
                    <div className="border-t border-[#F4F4F5] p-3.5">
                      <div className="flex gap-3">
                        <div className="w-1 shrink-0 rounded-full bg-[#84B496]" />
                        <MarkdownContent
                          content={question.model_answer}
                          remarkPlugins={REMARK_PLUGINS}
                          rehypePlugins={REHYPE_PLUGINS}
                          className="nova-text-label-medium-regular text-[#242529]"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type FeedbackReviewProps = {
  notes: FeedbackNote[];
  onNoteCompleted: (noteId: string) => void;
  completedCount: number;
  totalCount: number;
  onCurrentNoteChange?: (note: FeedbackNote | null) => void;
};

export function FeedbackReview({ notes, onNoteCompleted, completedCount, totalCount, onCurrentNoteChange }: FeedbackReviewProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [localAnsweredIds, setLocalAnsweredIds] = useState<Set<string>>(new Set());
  const [isCorrectMap, setIsCorrectMap] = useState<Map<string, boolean>>(new Map());
  const [localOrder, setLocalOrder] = useState<string[]>(() => notes.map((n) => n.id));

  const orderedNotes = useMemo(() => {
    const idSet = new Set(notes.map((n) => n.id));
    const baseOrder = localOrder.filter((id) => idSet.has(id));
    const seen = new Set(baseOrder);
    for (const n of notes) {
      if (!seen.has(n.id)) {
        baseOrder.push(n.id);
        seen.add(n.id);
      }
    }
    return baseOrder.map((id) => notes.find((nn) => nn.id === id)).filter(Boolean) as FeedbackNote[];
  }, [notes, localOrder]);

  const safeIndex = Math.min(currentIndex, orderedNotes.length - 1);
  const note = orderedNotes[safeIndex] ?? null;
  const isCurrentAnswered = note ? localAnsweredIds.has(note.id) : false;
  const isCurrentCorrect = note ? (isCorrectMap.get(note.id) ?? false) : false;
  const remaining = orderedNotes.filter((n) => !isCorrectMap.get(n.id)).length;

  useEffect(() => {
    onCurrentNoteChange?.(note);
  }, [note, onCurrentNoteChange]);

  if (orderedNotes.length === 0) {
    return (
      <FeedbackComplete
        message="You corrected all your mistakes!"
        completedCount={completedCount}
        totalCount={totalCount}
        showWeekProgress={false}
      />
    );
  }

  if (!note) return null;

  const handleAnswered = (noteId: string, isCorrect: boolean) => {
    setLocalAnsweredIds((prev) => new Set(prev).add(noteId));
    setIsCorrectMap((prev) => new Map(prev).set(noteId, isCorrect));
  };

  const handlePrev = () => setCurrentIndex((i) => Math.max(0, i - 1));
  const handleNext = () => {
    if (isCurrentAnswered) {
      if (isCurrentCorrect) {
        // correct — remove from list permanently
        onNoteCompleted(note.id);
      } else {
        // wrong — move to end, reset answered state so it shows fresh
        setLocalOrder((prev) => [...prev.filter((id) => id !== note.id), note.id]);
        setLocalAnsweredIds((prev) => { const s = new Set(prev); s.delete(note.id); return s; });
        setIsCorrectMap((prev) => { const m = new Map(prev); m.delete(note.id); return m; });
        // index stays the same — next note shifts in
      }
    } else {
      setCurrentIndex((i) => Math.min(orderedNotes.length - 1, i + 1));
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="flex flex-col items-center px-4 pt-8 pb-3">
        <ReviewCard
          key={note.id}
          note={note}
          onAnswered={handleAnswered}
        />
      </div>

      <div className="flex items-center justify-center pb-5">
        <div className="flex items-center gap-1 rounded-full border border-[#F2F2F4] px-1.5 py-1.5 nova-shadow-bottom">
          <Button
            variant="plain"
            iconOnly
            type="button"
            onClick={handlePrev}
            disabled={currentIndex === 0}
            className="flex items-center justify-center"
            aria-label="Previous"
          >
            <ChevronLeftIcon className="size-3.5" />
          </Button>

          <span className="px-2 nova-text-label-tiny text-[#71717A]">
            {remaining} left
          </span>

          <Button
            variant="default"
            iconOnly
            type="button"
            onClick={handleNext}
            disabled={currentIndex >= orderedNotes.length - 1 && !isCurrentAnswered}
            className="flex items-center justify-center"
            aria-label="Next"
          >
            <ChevronRightIcon className="size-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
