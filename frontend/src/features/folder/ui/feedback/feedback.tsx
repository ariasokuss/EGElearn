"use client";

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "react-toastify";
import { ArrowsPointingInIcon, ArrowsPointingOutIcon, XMarkIcon } from "@/shared/assets/icons";
import {
  listFeedbackNotes,
  type FeedbackNote,
  type FeedbackSummary,
} from "@/features/folder/api/feedback-api";
import { FeedbackMain } from "./feedback-main";
import { FeedbackSee } from "./feedback-see";
import { FeedbackReview } from "./feedback-review";
import { Button } from "@/shared";
import {
  invalidateFeedbackCache,
  readCachedFeedback,
  subscribeFeedbackCacheInvalidation,
  writeCachedFeedback,
} from "../../model/feedback-cache";
import { FEEDBACK_REVIEW_SUBMIT_TOAST_ID } from "./feedback-review-constants";

function FeedbackSkeleton() {
  return (
    <div className="flex flex-col gap-y-5 py-4" aria-hidden>
      <div className="flex gap-x-2">
        <div className="h-8 w-38 animate-pulse rounded-full bg-[#E4E4E7]" />
        <div className="h-8 w-38 animate-pulse rounded-full bg-[#E4E4E7]" />
      </div>
      <div className="flex max-w-176 flex-col gap-y-1.5 rounded-[16px] border border-[#F2F2F4] p-1.5">
        <div className="mb-2.5 ml-2.5 mt-1 h-7 w-44 animate-pulse rounded-lg bg-[#E4E4E7]" />
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="flex flex-col gap-y-6 rounded-[16px] border border-[#F2F2F4] p-4">
            <div className="flex gap-x-3">
              <div className="mt-0.5 size-5 shrink-0 animate-pulse rounded bg-[#E4E4E7]" />
              <div className="flex flex-1 flex-col gap-y-2">
                <div className="h-4 w-full animate-pulse rounded bg-[#E4E4E7]" />
                <div className="h-4 w-4/5 animate-pulse rounded bg-[#E4E4E7]" />
                <div className="h-5 w-28 animate-pulse rounded-full bg-[#E4E4E7]" />
              </div>
            </div>
            <div className="flex items-center gap-x-2 border-t border-[#F4F4F5] pt-2.5 pl-3">
              <div className="size-3 animate-pulse rounded bg-[#E4E4E7]" />
              <div className="h-4 w-20 animate-pulse rounded bg-[#E4E4E7]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

type TabWithHeaderProps = {
  children?: ReactNode;
  isArrowIn: boolean;
  onXClick: VoidFunction;
  onArrowsClick: VoidFunction;
};

function TabWithHeader({ children, onArrowsClick, onXClick, isArrowIn }: TabWithHeaderProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-4 py-2">
        <div className="flex">
          <Button
            variant="plain"
            iconOnly
            rounded={false}
            type="button"
            onClick={onXClick}
            className="flex shrink-0 items-center justify-center"
            aria-label="Back"
          >
            <XMarkIcon className="size-4.5" />
          </Button>
          <Button
            variant="plain"
            iconOnly
            rounded={false}
            type="button"
            onClick={onArrowsClick}
            className="flex shrink-0 items-center justify-center"
            aria-label="Toggle fullscreen"
          >
            {isArrowIn ? <ArrowsPointingInIcon /> : <ArrowsPointingOutIcon />}
          </Button>
        </div>
      </div>
      {children}
    </div>
  );
}

type FeedbackTab = "main" | "see" | "review";

function feedbackTabKey(folderId: string) {
  return `novalearn:feedback-subtab:${folderId}`;
}
function loadFeedbackTab(folderId: string): FeedbackTab {
  try {
    const saved = localStorage.getItem(feedbackTabKey(folderId));
    if (saved === "see" || saved === "review" || saved === "main") return saved;
  } catch { /* ignore */ }
  return "main";
}
function saveFeedbackTab(folderId: string, tab: FeedbackTab) {
  try { localStorage.setItem(feedbackTabKey(folderId), tab); } catch { /* ignore */ }
}

type FeedbackProps = {
  folderId: string;
  toggleFullscreen: VoidFunction;
  isFullscreen: boolean;
};

const EMPTY_SUMMARY: FeedbackSummary = { see: 0, review: 0, complete: 0, total: 0 };

function summaryFromNoteLists(
  see: FeedbackNote[],
  review: FeedbackNote[],
  covered: FeedbackNote[],
): FeedbackSummary {
  return {
    see: see.length,
    review: review.length,
    complete: covered.length,
    total: see.length + review.length + covered.length,
  };
}

export function Feedback({ folderId, toggleFullscreen, isFullscreen }: FeedbackProps) {
  const [tab, setTab] = useState<FeedbackTab>(() =>
    typeof window !== "undefined" ? loadFeedbackTab(folderId) : "main"
  );
  const tabRef = useRef<FeedbackTab>(tab);
  const [reviewMountKey, setReviewMountKey] = useState(0);

  useEffect(() => {
    tabRef.current = tab;
  }, [tab]);

  const [loading, setLoading] = useState(() => readCachedFeedback(folderId) == null);
  const [summary, setSummary] = useState<FeedbackSummary>(
    () => readCachedFeedback(folderId)?.summary ?? EMPTY_SUMMARY,
  );
  const [seeNotes, setSeeNotes] = useState<FeedbackNote[]>(
    () => readCachedFeedback(folderId)?.seeNotes ?? [],
  );
  const [reviewNotes, setReviewNotes] = useState<FeedbackNote[]>(
    () => readCachedFeedback(folderId)?.reviewNotes ?? [],
  );
  const [coveredNotes, setCoveredNotes] = useState<FeedbackNote[]>(
    () => readCachedFeedback(folderId)?.coveredNotes ?? [],
  );

  const optimisticCompleteNotesRef = useRef<Map<string, FeedbackNote>>(new Map());
  /** Monotonic generation so stale in-flight loadData responses cannot overwrite newer UI. */
  const loadDataGenRef = useRef(0);

  const loadData = useCallback(async (options?: { force?: boolean; backgroundRevalidate?: boolean }) => {
    const force = options?.force ?? false;
    const backgroundRevalidate = options?.backgroundRevalidate ?? false;
    const cached = readCachedFeedback(folderId);

    if (!force && cached) {
      setSummary(cached.summary);
      setSeeNotes(cached.seeNotes);
      setReviewNotes(cached.reviewNotes);
      setCoveredNotes(cached.coveredNotes);
      setLoading(false);
      return;
    }

    const blockUi = !backgroundRevalidate;
    if (blockUi) {
      setLoading(true);
    }

    const gen = ++loadDataGenRef.current;
    try {
      const [see, review, covered] = await Promise.all([
        listFeedbackNotes({ folder_id: folderId, status: "see", limit: 200 }),
        listFeedbackNotes({ folder_id: folderId, status: "review", limit: 200 }),
        listFeedbackNotes({ folder_id: folderId, status: "complete", limit: 200 }),
      ]);
      if (gen !== loadDataGenRef.current) return;

      let reviewMerged = review;
      let coveredMerged = covered;
      const opt = optimisticCompleteNotesRef.current;
      if (opt.size > 0) {
        const optIds = new Set(opt.keys());
        reviewMerged = review.filter((n) => !optIds.has(n.id));
        for (const c of covered) {
          if (opt.has(c.id)) opt.delete(c.id);
        }
        coveredMerged = [...covered];
        for (const [, note] of opt) {
          coveredMerged.push(note);
        }
      }
      const nextSummary = summaryFromNoteLists(see, reviewMerged, coveredMerged);
      writeCachedFeedback(folderId, {
        summary: nextSummary,
        seeNotes: see,
        reviewNotes: reviewMerged,
        coveredNotes: coveredMerged,
      });
      setSummary(nextSummary);
      setSeeNotes(see);
      setReviewNotes(reviewMerged);
      setCoveredNotes(coveredMerged);
    } catch {
      /* network or parse failure — keep existing UI; loading cleared in finally */
    } finally {
      if (gen === loadDataGenRef.current) {
        setLoading(false);
      }
    }
  }, [folderId]);

  const changeTab = useCallback(
    (next: FeedbackTab) => {
      const prev = tabRef.current;
      if (prev === "review" && next !== "review") {
        toast.dismiss(FEEDBACK_REVIEW_SUBMIT_TOAST_ID);
        setReviewMountKey((k) => k + 1);
        void loadData({ force: true, backgroundRevalidate: true });
      }
      if (next === "review" && prev !== "review") {
        setReviewMountKey((k) => k + 1);
      }
      setTab(next);
      saveFeedbackTab(folderId, next);
    },
    [folderId, loadData],
  );

  useEffect(() => {
    const hadCacheOnMount = readCachedFeedback(folderId) != null;
    queueMicrotask(() => {
      void loadData({ force: true, backgroundRevalidate: hadCacheOnMount });
    });
  }, [folderId, loadData]);

  useEffect(() => {
    return subscribeFeedbackCacheInvalidation((id) => {
      if (id !== folderId) return;
      void loadData({ force: true, backgroundRevalidate: true });
    });
  }, [folderId, loadData]);

  const onXClick = () => {
    if (isFullscreen) toggleFullscreen();
    changeTab("main");
  };

  const handleSeeNoteCompleted = (noteId: string) => {
    // see -> review pipeline
    const movedNote = seeNotes.find((n) => n.id === noteId);
    const nextSeeNotes = seeNotes.filter((n) => n.id !== noteId);
    const nextReviewNotes = movedNote
      ? [...reviewNotes, { ...movedNote, status: "review" as const }]
      : reviewNotes;
    const nextSummary = {
      ...summary,
      see: Math.max(0, summary.see - 1),
      review: summary.review + 1,
    };
    setSeeNotes(nextSeeNotes);
    setReviewNotes(nextReviewNotes);
    setSummary(nextSummary);
    invalidateFeedbackCache(folderId);
  };

  const handleReviewNoteCompleted = (noteId: string) => {
    // review -> complete pipeline (after Next when answer was correct — idempotent)
    const movedNote = reviewNotes.find((n) => n.id === noteId);
    if (!movedNote) return;
    optimisticCompleteNotesRef.current.set(noteId, { ...movedNote, status: "complete" });
    const nextReviewNotes = reviewNotes.filter((n) => n.id !== noteId);
    const nextCoveredNotes = [...coveredNotes, { ...movedNote, status: "complete" as const }];
    const nextSummary = {
      ...summary,
      review: Math.max(0, summary.review - 1),
      complete: summary.complete + 1,
    };
    setReviewNotes(nextReviewNotes);
    setCoveredNotes(nextCoveredNotes);
    setSummary(nextSummary);
    invalidateFeedbackCache(folderId);
  };

  if (loading) {
    return <FeedbackSkeleton />;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {tab === "main" ? (
        <div className="flex-1 overflow-y-auto">
          <FeedbackMain
            seeCount={summary.see}
            reviewCount={summary.review}
            coveredNotes={coveredNotes}
            navigateSee={() => changeTab("see")}
            navigateReview={() => changeTab("review")}
          />
        </div>
      ) : (
        <div className="flex h-full">
          <div className="min-w-0 flex-1">
            <TabWithHeader
              onArrowsClick={toggleFullscreen}
              onXClick={onXClick}
              isArrowIn={isFullscreen}
            >
              {tab === "see" ? (
                <FeedbackSee
                  notes={seeNotes}
                  onNoteCompleted={handleSeeNoteCompleted}
                  onRefresh={() => { void loadData({ force: true, backgroundRevalidate: true }); }}
                  completedCount={summary.total - summary.see}
                  totalCount={summary.total}
                  onNavigateReview={() => changeTab("review")}
                />
              ) : (
                <FeedbackReview
                  key={reviewMountKey}
                  notes={reviewNotes}
                  onNoteCompleted={handleReviewNoteCompleted}
                  completedCount={summary.complete}
                  totalCount={summary.total}
                />
              )}
            </TabWithHeader>
          </div>
        </div>
      )}
    </div>
  );
}
