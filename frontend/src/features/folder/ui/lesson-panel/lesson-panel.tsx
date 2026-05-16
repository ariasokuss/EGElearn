"use client";

import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "motion/react";

import { useNotes } from "../../model/notes-context";
import { LessonSelectionOverlay } from "./lesson-selection-overlay";
import { LessonSelectionToolbar } from "./lesson-selection-toolbar";
import { SavedHighlights } from "./saved-highlights";
import { useLessonSelection } from "./use-lesson-selection";
import { useSavedHighlights, findTextRange } from "./use-saved-highlights";

import type {
  FeynmanBlockRead,
  LessonBlockSchema,
  LessonSchema,
  RoadmapLessonOut,
  SessionHistoryItem,
} from "@/shared/api/generated/model";
import {
  ArrowsPointingInIcon,
  ArrowsPointingOutIcon,
  ChevronRightIcon,
  HideBarIcon,
  LoaderIcon,
  StarFilledColoredIcon,
  StarIcon,
  XMarkIcon,
} from "@/shared/assets/icons";

import { LessonCard } from "@/shared/ui/lesson-card";
import { TabsNav, type TabItem } from "@/shared/ui/tabs-nav/tabs-nav";

import { Button, cn } from "@/shared";
import { useAutoHideScrollbar, useTestGuard } from "@/shared/lib";

import { getLessonDetailApi } from "../../api/lessons-api";
import {
  cacheFeynmanHistory,
  cacheLesson,
  clearLessonCaches,
  getCachedFeynmanHistory,
  getCachedLesson,
  getMemoryFeynmanHistory,
  getMemoryLesson,
} from "../../lib/lesson-db";
import {
  clearLessonUiForLesson,
  isExplanationStage,
  isLessonTab,
  isLessonTestFullscreenUi,
  lessonUiStorageKey,
  readLessonUi,
  readLessonUiForLesson,
  writeLessonUi,
  writeLessonUiForLesson,
} from "../../lib/lesson-ui-state";
import { getFeynmanHistory } from "./block-renderer/feynman-api";
import { BlockRenderer } from "./block-renderer";
import { Explanation } from "./explanation";
import { LessonResults } from "./results";
import { TestingTab } from "./testing-tab/testing-tab";
import { useLessonTabPrefetch } from "./use-lesson-tab-prefetch";
import type { ExplanationStage } from "./types";
import { parseContent, type Segment } from "./block-renderer/parse-content";
import { LessonIntro } from "./lesson-intro";
import { Scroller } from "./scroller/scroller";
import { extractBlockNav } from "./scroller/extract-block-nav";
import { useActiveBlock } from "./scroller/use-active-block";
import { type AnswerRecord, useInlineQuiz } from "./use-inline-quiz";
import { resetLesson } from "../../api/lesson-test-api";
import { lessonStepDisplayFlags, progressReadToLessonUpdate, useLessons } from "../../model/lessons-context";
import { Tippy } from "@/shared/ui";
import { STAR_TOOLTIP } from "../../lib/tooltip-content";

const LESSON_TAB_KEYS = ["Study", "Explanation", "Testing", "Results"] as const;
type LessonTab = (typeof LESSON_TAB_KEYS)[number];

const TESTING_TAB_INDEX = LESSON_TAB_KEYS.indexOf("Testing");

type LessonPanelProps = {
  lesson: RoadmapLessonOut;
  folderId: string;
  lessonsListVisible: boolean;
  chatVisible: boolean;
  onSelectLesson: (id: string) => void;
  onToggleLessonsList: VoidFunction;
  onToggleChat: VoidFunction;
  onCloseChat: VoidFunction;
  onClosePanel?: VoidFunction;
  onAskNova?: (text: string) => void;
  onMarkNote?: VoidFunction;
  onActiveBlockChange?: (blockId: string | null) => void;
  onScrollToHighlightRef?: React.MutableRefObject<((text: string) => void) | null>;
  onInlineQuizAnswersChange?: (answers: Map<string, AnswerRecord>) => void;
};

type State = {
  lessonMeta: LessonSchema | null;
  blocks: LessonBlockSchema[];
  feynmanBlocks: FeynmanBlockRead[];
  miniFeynmanHistory: SessionHistoryItem[];
  loading: boolean;
};

type Action =
  | { type: "fetch" }
  | {
      type: "done";
      lessonMeta: LessonSchema | null;
      blocks: LessonBlockSchema[];
      feynmanBlocks: FeynmanBlockRead[];
      miniFeynmanHistory: SessionHistoryItem[];
    };

function reducer(_: State, action: Action): State {
  if (action.type === "fetch") {
    return { lessonMeta: null, blocks: [], feynmanBlocks: [], miniFeynmanHistory: [], loading: true };
  }
  return {
    lessonMeta: action.lessonMeta,
    blocks: action.blocks,
    feynmanBlocks: action.feynmanBlocks,
    miniFeynmanHistory: action.miniFeynmanHistory,
    loading: false,
  };
}

function countFeynmanDirectives(content: string): number {
  return (content.match(/^:::\s+feynman/gm) ?? []).length;
}

function countQuestionDirectives(content: string): number {
  return (content.match(/^:::\s+question/gm) ?? []).length;
}

function LessonPanelInner({
  lesson,
  folderId,
  lessonsListVisible,
  chatVisible,
  onSelectLesson,
  onToggleLessonsList,
  onToggleChat,
  onCloseChat,
  onClosePanel,
  onAskNova,
  onMarkNote,
  onActiveBlockChange,
  onScrollToHighlightRef,
  onInlineQuizAnswersChange,
}: LessonPanelProps) {
  const {
    lessonMap,
    stepStatus,
    updateLessonProgress,
    setLessonStepStatus,
    resetStepStatus,
    refreshLessonProgress,
  } = useLessons();

  const lessonStorageKey = lessonUiStorageKey(lesson) ?? "";

  const [activeTab, setActiveTab] = useState<LessonTab>(() => {
    const saved = readLessonUiForLesson(lesson)?.activeTab;
    return isLessonTab(saved) ? saved : "Study";
  });

  const [resettingLesson, setResettingLesson] = useState(false);
  /** Bump after Redo lesson to refetch tab prefetch + lesson payload without changing lesson id. */
  const [lessonResetNonce, setLessonResetNonce] = useState(0);

  const [activeLessonId, setActiveLessonId] = useState(
    () => lessonUiStorageKey(lesson) ?? "",
  );
  const [testActive, setTestActive] = useState(() =>
    isLessonTestFullscreenUi(readLessonUiForLesson(lesson)),
  );
  const [answerReviewOpen, setAnswerReviewOpen] = useState(false);
  const [testingTabReselectKey, setTestingTabReselectKey] = useState(0);
  const [explanationStage, setExplanationStage] = useState<ExplanationStage>(
    () => {
      const s = readLessonUiForLesson(lesson)?.explanationStage;
      return isExplanationStage(s) ? s : "start";
    },
  );

  const { requestNavigation } = useTestGuard();

  const [{ lessonMeta, blocks, feynmanBlocks, miniFeynmanHistory, loading }, dispatch] = useReducer(
    reducer,
    { lessonMeta: null, blocks: [], feynmanBlocks: [], miniFeynmanHistory: [], loading: false },
  );

  if (activeLessonId !== lessonStorageKey) {
    setActiveLessonId(lessonStorageKey);
    const u = readLessonUiForLesson(lesson);
    const savedTab = u?.activeTab;
    setActiveTab(isLessonTab(savedTab) ? savedTab : "Study");
    setExplanationStage(
      isExplanationStage(u?.explanationStage) ? u.explanationStage : "start",
    );
    setTestActive(isLessonTestFullscreenUi(u));
    setAnswerReviewOpen(false);
    setTestingTabReselectKey(0);
    dispatch({ type: "fetch" });
  }

  useEffect(() => {
    if (!lessonStorageKey) return;
    writeLessonUiForLesson(lesson, {
      activeTab,
      explanationStage,
      testActive,
    });
  }, [lesson, lessonStorageKey, activeTab, explanationStage, testActive]);
  const prevLessonsVisible = useRef(false);
  const prevChatVisible = useRef(false);

  const activeTabIndex = LESSON_TAB_KEYS.indexOf(activeTab);

  const handleTabChange = useCallback(
    (index: number) => {
      if (index === TESTING_TAB_INDEX && activeTab === "Testing") {
        setTestingTabReselectKey((k) => k + 1);
      }
      setActiveTab(LESSON_TAB_KEYS[index]);
    },
    [activeTab],
  );

  const handleTestStart = useCallback(() => {
    prevLessonsVisible.current = lessonsListVisible;
    prevChatVisible.current = chatVisible;
    if (lessonsListVisible) onToggleLessonsList();
    if (chatVisible) onToggleChat();
    setTestActive(true);
  }, [lessonsListVisible, chatVisible, onToggleLessonsList, onToggleChat]);

  const handleTestEnd = useCallback(() => {
    if (prevLessonsVisible.current) onToggleLessonsList();
    if (prevChatVisible.current) onToggleChat();
    setTestActive(false);
  }, [onToggleLessonsList, onToggleChat]);

  useEffect(() => {
    if (!lessonStorageKey) return;
    const lessonId = lessonStorageKey;
    let cancelled = false;
    let hasFreshData = false;

    const memData = getMemoryLesson(lessonId);
    const memHistory = getMemoryFeynmanHistory(lessonId);
    if (memData) {
      const sorted = (memData.blocks ?? [])
        .slice()
        .sort((a, b) => a.block_number - b.block_number);
      dispatch({
        type: "done",
        lessonMeta: memData.lesson ?? null,
        blocks: sorted,
        feynmanBlocks: memData.feynman_blocks ?? [],
        miniFeynmanHistory: memHistory ?? [],
      });
    } else {
      dispatch({ type: "fetch" });
      (async () => {
        const [cachedData, cachedHistory] = await Promise.all([
          getCachedLesson(lessonId),
          getCachedFeynmanHistory(lessonId),
        ]);
        if (cancelled || hasFreshData || !cachedData) return;
        const sorted = (cachedData.blocks ?? [])
          .slice()
          .sort((a, b) => a.block_number - b.block_number);
        dispatch({
          type: "done",
          lessonMeta: cachedData.lesson ?? null,
          blocks: sorted,
          feynmanBlocks: cachedData.feynman_blocks ?? [],
          miniFeynmanHistory: cachedHistory ?? [],
        });
      })();
    }

    Promise.all([
      getLessonDetailApi(lessonId, folderId),
      getFeynmanHistory(lessonId),
    ]).then(([data, history]) => {
      if (cancelled) return;
      hasFreshData = true;
      if (!data) return;
      const sorted = (data.blocks ?? [])
        .slice()
        .sort((a, b) => a.block_number - b.block_number);
      dispatch({
        type: "done",
        lessonMeta: data.lesson ?? null,
        blocks: sorted,
        feynmanBlocks: data.feynman_blocks ?? [],
        miniFeynmanHistory: history,
      });
      cacheLesson(lessonId, data);
      cacheFeynmanHistory(lessonId, history);
      if (data.progress != null) {
        setLessonStepStatus(lessonId, data.progress);
        updateLessonProgress(lessonId, progressReadToLessonUpdate(data.progress));
      } else {
        void refreshLessonProgress(lessonId);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [
    lessonStorageKey,
    folderId,
    lessonResetNonce,
    refreshLessonProgress,
    setLessonStepStatus,
    updateLessonProgress,
  ]);

  const feynmanBlocksByBlockIdx = useMemo(() => {
    return blocks.reduce<{ result: FeynmanBlockRead[][]; offset: number }>(
      ({ result, offset }, block) => {
        const count = countFeynmanDirectives(block.content);
        return {
          result: [...result, feynmanBlocks.slice(offset, offset + count)],
          offset: offset + count,
        };
      },
      { result: [], offset: 0 },
    ).result;
  }, [blocks, feynmanBlocks]);

  const feynmanSegmentsByBlock = useMemo(() => {
    return blocks.map((block) =>
      parseContent(block.content).filter(
        (s) => s.kind === "directive" && s.name === "feynman",
      ),
    );
  }, [blocks]);

  const totalQuestions = useMemo(() => {
    return blocks.reduce(
      (sum, block) => sum + countQuestionDirectives(block.content),
      0,
    );
  }, [blocks]);

  const lessonTitle = lessonMeta?.name ?? lesson.name ?? "";

  const lessonTabs = useMemo((): TabItem[] => {
    const displayLesson =
      lessonStorageKey && lessonMap[lessonStorageKey]
        ? lessonMap[lessonStorageKey].lesson
        : lesson;
    const st = lessonStorageKey ? stepStatus[lessonStorageKey] : undefined;
    const stepFilled = lessonStepDisplayFlags(displayLesson, st);

    return LESSON_TAB_KEYS.map((tab, index) => {
      if (tab === "Results") {
        return { key: tab, label: <span>{tab}</span> };
      }
      return {
        key: tab,
        label: (
          <>
            <Tippy
              content={STAR_TOOLTIP[index]}
            >
              {stepFilled[index] ? (
                <StarFilledColoredIcon className="h-3.5 w-3.5 shrink-0" />
              ) : (
                <StarIcon className="h-3.5 w-3.5 shrink-0" />
              )}
            </Tippy>
            <span>{tab}</span>
          </>
        ),
        tabClassName: "gap-1",
      };
    });
  }, [lesson, lessonStorageKey, lessonMap, stepStatus]);

  const tabPrefetch = useLessonTabPrefetch(
    lessonStorageKey,
    folderId,
    lessonResetNonce,
  );

  const { answers, submitAnswer, resetQuiz } = useInlineQuiz(
    lessonStorageKey,
    totalQuestions,
  );

  // Lift inline quiz answers to parent for chat context injection.
  useEffect(() => {
    onInlineQuizAnswersChange?.(answers);
  }, [answers, onInlineQuizAnswersChange]);

  const handleRedoLesson = useCallback(async () => {
    if (lessonStorageKey) {
      setResettingLesson(true);
      await resetLesson(lessonStorageKey);
      clearLessonUiForLesson(lesson);
      await clearLessonCaches(lessonStorageKey);
      updateLessonProgress(lessonStorageKey, {
        study_star: false,
        feynman_star: false,
        test_star: false,
        mastery: null,
        confidence: null,
      });
      resetStepStatus(lessonStorageKey);
      setLessonResetNonce((n) => n + 1);
    }
    await resetQuiz();
    setExplanationStage("start");
    setActiveTab("Study");
    setResettingLesson(false);
  }, [lesson, lessonStorageKey, resetQuiz, resetStepStatus, updateLessonProgress]);

  const handleSubmitAnswer = useCallback(
    (blockId: string, questionIndex: number, record: AnswerRecord) => {
      submitAnswer(blockId, questionIndex, record);
    },
    [submitAnswer],
  );



  useEffect(() => {
    if (activeTab !== "Study") {
      onCloseChat();
    }
  }, [activeTab, onCloseChat]);

  const handleAnswerReviewModeChange = useCallback((open: boolean) => {
    setAnswerReviewOpen(open);
  }, []);

  const handleXClick = useCallback(async () => {
    if (activeTab === "Explanation" && explanationStage !== "start") {
      setExplanationStage("start");
      return;
    }
    if (testActive) {
      const canProceed = await requestNavigation();
      if (!canProceed) return;
    }
    onClosePanel?.();
  }, [onClosePanel, activeTab, explanationStage, testActive, requestNavigation]);

  const chatToggleAfter =
    activeTab === "Study" && !chatVisible ? (
      <Button
        variant="outline"
        iconOnly
        size='sm'
        type="button"
        onClick={onToggleChat}
        className="flex items-center justify-center transition-all duration-150"
        aria-label="Open chat"
      >
        <HideBarIcon className="h-4 w-4 rotate-180" />
      </Button>
    ) : undefined;

  const hideTopLessonChrome =
    testActive ||
    answerReviewOpen ||
    isLessonTestFullscreenUi(readLessonUiForLesson(lesson));

  return (
    <div
      className={cn(
        "flex h-full flex-col overflow-hidden",
        !hideTopLessonChrome && "pt-4",
      )}
    >
      {!hideTopLessonChrome && (
        <div className="flex items-center justify-between px-5 pt-1.5">
          <div className="flex">
            <Button
              variant="plain"
              iconOnly
              rounded={false}
              type="button"
              onClick={handleXClick}
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
              onClick={() => {
                if (
                  activeTab === "Study" &&
                  lessonsListVisible &&
                  !chatVisible
                ) {
                  onToggleChat();
                }
                onToggleLessonsList();
              }}
              className="flex shrink-0 items-center justify-center"
              aria-label={
                lessonsListVisible ? "Hide lessons list" : "Show lessons list"
              }
            >
              {lessonsListVisible ? (
                <ArrowsPointingOutIcon />
              ) : (
                <ArrowsPointingInIcon />
              )}
            </Button>
          </div>

          <TabsNav
            tabs={lessonTabs}
            activeIndex={activeTabIndex}
            onTabChange={handleTabChange}
            className="border-b border-[#E8E5E180] pt-0.5 pb-2"
            separator={
              <ChevronRightIcon className="size-4 stroke-[2.5px] text-[#A1A1AA]" />
            }
          />

          <div className="flex">
            {chatToggleAfter ?? <div className="h-8 w-8" />}
          </div>
        </div>
      )}

      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col overflow-hidden",
          activeTab !== "Study" && "hidden",
        )}
      >
        <LessonContent
          activeTab="Study"
          loading={loading}
          blocks={blocks}
          feynmanBlocks={feynmanBlocks}
          feynmanBlocksByBlockIdx={feynmanBlocksByBlockIdx}
          feynmanSegmentsByBlock={feynmanSegmentsByBlock}
          miniFeynmanHistory={miniFeynmanHistory}
          lessonTitle={lessonTitle}
          lessonId={lessonStorageKey}
          answers={answers}
          onSubmitAnswer={handleSubmitAnswer}
          onAskNova={onAskNova}
          onMarkNote={onMarkNote}
          onGoToExplanation={() => setActiveTab("Explanation")}
          onActiveBlockChange={onActiveBlockChange}
          onScrollToHighlightRef={onScrollToHighlightRef}
        />
      </div>

      <div
        className={cn(
          "min-h-0 flex-1 overflow-hidden",
          activeTab !== "Explanation" && "hidden",
        )}
      >
        <Explanation
          key={lessonStorageKey}
          lessonId={lessonStorageKey}
          activeStage={explanationStage}
          setActiveStage={setExplanationStage}
          navigateTesting={() => setActiveTab("Testing")}
          prefetchedHistory={tabPrefetch.feynmanHistory}
          prefetchedHistoryLoading={tabPrefetch.feynmanHistoryLoading}
        />
      </div>

      <div
        className={cn(
          "min-h-0 flex-1 overflow-y-auto",
          activeTab !== "Testing" && "hidden",
        )}
        style={{ contain: "layout style paint" }}
      >
        <TestingTab
          tabPrefetch={tabPrefetch}
          onTestStart={handleTestStart}
          onTestEnd={handleTestEnd}
          onAnswerReviewModeChange={handleAnswerReviewModeChange}
          lessonId={lessonStorageKey}
          testingTabReselectKey={testingTabReselectKey}
        />
      </div>

      <div
        className={cn(
          "min-h-0 flex-1 overflow-hidden",
          activeTab !== "Results" && "hidden",
        )}
      >
        <LessonResults
          navigateLessonPart={(blockId) => {
            setActiveTab("Study");
            requestAnimationFrame(() => {
              document
                .querySelector(`[data-block-id="${blockId}"]`)
                ?.scrollIntoView({ behavior: "smooth", block: "start" });
            });
          }}
          navigateNextLesson={() =>
            onSelectLesson(lessonMap[lessonStorageKey]?.nextId ?? "")
          }
          redoLesson={handleRedoLesson}
          lesson={lesson}
          prefetchedResults={tabPrefetch.lessonResults}
          prefetchedResultsLoading={tabPrefetch.lessonResultsLoading}
          resettingLesson={resettingLesson}
        />
      </div>
    </div>
  );
}

export const LessonPanel = memo(LessonPanelInner);

type LessonContentProps = {
  activeTab: LessonTab;
  loading: boolean;
  blocks: LessonBlockSchema[];
  feynmanBlocks: FeynmanBlockRead[];
  feynmanBlocksByBlockIdx: FeynmanBlockRead[][];
  feynmanSegmentsByBlock: Segment[][];
  miniFeynmanHistory: SessionHistoryItem[];
  lessonTitle: string;
  lessonId: string;
  answers: Map<string, AnswerRecord>;
  onSubmitAnswer: (
    blockId: string,
    questionIndex: number,
    record: AnswerRecord,
  ) => void;
  onAskNova?: (text: string) => void;
  onMarkNote?: VoidFunction;
  onGoToExplanation: VoidFunction;
  onActiveBlockChange?: (blockId: string | null) => void;
  onScrollToHighlightRef?: React.MutableRefObject<((text: string) => void) | null>;
};

const LessonContent = memo(function LessonContent({
  activeTab,
  loading,
  blocks,
  feynmanBlocks,
  feynmanBlocksByBlockIdx,
  feynmanSegmentsByBlock,
  miniFeynmanHistory,
  lessonTitle,
  lessonId,
  answers,
  onSubmitAnswer,
  onAskNova,
  onMarkNote,
  onGoToExplanation,
  onActiveBlockChange,
  onScrollToHighlightRef,
}: LessonContentProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useAutoHideScrollbar(scrollRef);
  const { selection, clearSelection } = useLessonSelection(scrollRef);

  // Persist scroll position on scroll (rAF-throttled) and restore on lesson
  // change once content has rendered. Blocks use `contentVisibility: auto`
  // with `containIntrinsicSize: 500px` so total scrollHeight is stable enough
  // for scrollTop to land in the right neighbourhood before off-screen blocks
  // lay out fully.
  const lastPersistedScrollRef = useRef(0);
  const scrollRafPendingRef = useRef(false);
  const scrollReadyForLessonRef = useRef<string | null>(null);

  useEffect(() => {
    if (!lessonId || loading || blocks.length === 0) return;
    const el = scrollRef.current;
    if (!el) return;

    const saved = readLessonUi(lessonId)?.scrollTop;
    // Pre-seed last-persisted so the scroll event fired by programmatic
    // restore won't be treated as a user action.
    lastPersistedScrollRef.current =
      typeof saved === "number" && saved > 0 ? saved : 0;

    // Restore only on the first "ready" effect for this lesson. Subsequent
    // triggers (e.g. StrictMode re-invoke, block count growth) keep the
    // persist listener live without resetting user scroll.
    const firstReadyForLesson = scrollReadyForLessonRef.current !== lessonId;
    scrollReadyForLessonRef.current = lessonId;

    if (firstReadyForLesson && typeof saved === "number" && saved > 0) {
      // Two rAFs so layout settles after the fade-in motion.div wrapper.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (scrollRef.current === el) {
            el.scrollTop = saved;
          }
        });
      });
    }

    const handleScroll = () => {
      if (scrollRafPendingRef.current) return;
      scrollRafPendingRef.current = true;
      requestAnimationFrame(() => {
        scrollRafPendingRef.current = false;
        const top = el.scrollTop;
        if (Math.abs(top - lastPersistedScrollRef.current) < 20) return;
        lastPersistedScrollRef.current = top;
        writeLessonUi(lessonId, { scrollTop: top });
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [lessonId, loading, blocks.length]);

  const [showLoader, setShowLoader] = useState(false);
  const [prevLoading, setPrevLoading] = useState(loading);
  if (prevLoading !== loading) {
    setPrevLoading(loading);
    if (!loading) setShowLoader(false);
  }
  useEffect(() => {
    if (!loading) return;
    const id = setTimeout(() => setShowLoader(true), 150);
    return () => clearTimeout(id);
  }, [loading]);
  const { notes, addNote, addNoteWithFocus, removeNote, loadForLesson } = useNotes();

  useEffect(() => {
    if (lessonId) loadForLesson(lessonId);
  }, [lessonId, loadForLesson]);

  useEffect(() => {
    if (!onScrollToHighlightRef) return;
    onScrollToHighlightRef.current = (text: string) => {
      const container = scrollRef.current;
      if (!container) return;
      const range = findTextRange(container, text);
      if (!range) return;
      const rect = range.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const top = rect.top - containerRect.top + container.scrollTop - 80;
      container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    };
    return () => { if (onScrollToHighlightRef) onScrollToHighlightRef.current = null; };
  }, [onScrollToHighlightRef]);

  const lessonNotes = useMemo(
    () => notes.filter((n) => n.lessonId === lessonId),
    [notes, lessonId],
  );
  const savedHighlights = useSavedHighlights(
    scrollRef,
    lessonNotes,
    loading,
    blocks.length,
  );

  const navItems = useMemo(
    () => extractBlockNav(blocks, lessonTitle),
    [blocks, lessonTitle],
  );
  const blockIds = useMemo(() => blocks.map((b) => b.id), [blocks]);
  const activeBlockId = useActiveBlock(scrollRef, blockIds);

  useEffect(() => {
    onActiveBlockChange?.(activeBlockId);
  }, [activeBlockId, onActiveBlockChange]);

  const handleMark = useCallback(
    (text: string) => {
      addNote(text, lessonId);
      onMarkNote?.();
    },
    [addNote, lessonId, onMarkNote],
  );

  const handleNote = useCallback(
    (text: string) => {
      addNoteWithFocus(text, lessonId);
      onMarkNote?.();
    },
    [addNoteWithFocus, lessonId, onMarkNote],
  );

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={scrollRef}
        className="lesson-content lesson-study-scroll h-full overflow-y-auto overflow-x-hidden"
        data-has-selection={selection ? "" : undefined}
        style={{ contain: "layout style paint" }}
      >
        {activeTab === "Study" && (
          <>
            {showLoader && (
              <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
              </div>
            )}

            {!loading && blocks.length === 0 && (
              <p className="py-16 text-center nova-text-p-base text-[#71717A]">
                No content available.
              </p>
            )}

            <AnimatePresence mode="wait">
              {!loading && blocks.length > 0 && (
                <motion.div
                  key={lessonId}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15, ease: "easeInOut" }}
                  className="mx-auto w-full max-w-177 flex flex-col gap-3 px-7 py-6"
                >
                  {blocks.map((block, idx) =>
                    idx === 0 ? (
                      <div key={block.id} data-block-id={block.id}>
                        <LessonIntro
                          content={block.content}
                          title={lessonTitle}
                        />
                      </div>
                    ) : (
                      <div
                        key={block.id}
                        data-block-id={block.id}
                        style={{
                          contentVisibility: "auto",
                          containIntrinsicSize: "auto 500px",
                        }}
                      >
                        <LessonCard className="px-1.5 pt-4 pb-2">
                          <BlockRenderer
                            content={block.content}
                            feynmanBlocks={feynmanBlocksByBlockIdx[idx]}
                            miniFeynmanHistory={miniFeynmanHistory}
                            lessonId={lessonId}
                            blockId={block.id}
                            answers={answers}
                            onSubmitAnswer={onSubmitAnswer}
                            onAskNova={onAskNova}
                          />
                        </LessonCard>
                      </div>
                    ),
                  )}
                  <div className="mt-3 flex justify-end">
                    <Button variant="outline" onClick={onGoToExplanation}>
                      Go to explanation
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}

        {activeTab === "Explanation" && (
          <div className="mx-auto w-full max-w-177 px-7 py-6">
            {feynmanBlocks.length === 0 ? (
              <p className="py-16 text-center nova-text-p-base text-[#71717A]">
                No Feynman exercises for this lesson.
              </p>
            ) : (
              <div className="flex flex-col gap-6">
                {blocks.map((block, blockIdx) =>
                  feynmanSegmentsByBlock[blockIdx].map((seg, segIdx) => {
                    if (seg.kind !== "directive") return null;
                    const fb = feynmanBlocksByBlockIdx[blockIdx][segIdx];
                    return (
                      <div key={`${block.id}-${segIdx}`}>
                        <BlockRenderer
                          content={`:::\u0020feynman\n${seg.body}\n:::`}
                          feynmanBlocks={fb ? [fb] : []}
                          miniFeynmanHistory={miniFeynmanHistory}
                          lessonId={lessonId}
                          onAskNova={onAskNova}
                        />
                      </div>
                    );
                  }),
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === "Study" && savedHighlights.length > 0 && (
          <SavedHighlights
            highlights={savedHighlights}
            containerRef={scrollRef}
            onDelete={removeNote}
            onAskNova={onAskNova}
          />
        )}

        {activeTab === "Study" && selection && (
          <>
            <LessonSelectionOverlay selection={selection} />
            <LessonSelectionToolbar
              selection={selection}
              containerRef={scrollRef}
              onClear={clearSelection}
              onAskNova={onAskNova}
              onMark={handleMark}
              onNote={handleNote}
            />
          </>
        )}
      </div>

      {activeTab === "Study" && !loading && blocks.length > 1 && (
        <div className="pointer-events-none absolute top-[calc(50%-24px)] -translate-y-1/2 right-6.5 z-20">
          <div className="pointer-events-auto">
            <Scroller
              navItems={navItems}
              activeBlockId={activeBlockId}
              scrollRef={scrollRef}
            />
          </div>
        </div>
      )}
    </div>
  );
});
