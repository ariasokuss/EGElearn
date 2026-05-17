"use client";

import { Suspense, useCallback, useEffect, useLayoutEffect, memo, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import {
  ChatSidePanel,
  FolderTabsNav,
  LessonPanel,
  Lessons,
  Roadmap,
} from "@/features/folder";
import type { AnswerRecord } from "@/features/folder/ui/lesson-panel/use-inline-quiz";
import { Feedback } from "@/features/folder/ui/feedback";
import { NotesProvider } from "@/features/folder/model/notes-context";
import { PracticeQuestionsView } from "@/features/practice-questions";
import { usePanelResize } from "@/features/chat/model/use-panel-resize";
import { PageCard } from "@/shared/ui";
import { LoaderIcon } from "@/shared/assets/icons";
import { cn, useAutoHideScrollbar } from "@/shared/lib";
import type { LessonSchema, RoadmapLessonOut } from "@/shared/api/generated/model";
import {
  readSavedTab,
  resolveDisplayedFolderTab,
  resolveInitialFolderTab,
  writeSavedTab,
  type FolderTabParam,
} from "@/features/folder/lib/folder-ui-copy";
import {
  readFolderLessonsUi,
  writeFolderLessonsUi,
} from "@/features/folder/lib/lesson-ui-state";
import {
  LessonsProvider,
  useLessons,
} from "@/features/folder/model/lessons-context";
import { recordActivityEvent } from "@/shared/api/activity";

function findLessonInMap<T extends { lesson: RoadmapLessonOut }>(
  map: Record<string, T>,
  lessonKeyOrNodeId: string,
): T | undefined {
  const direct = map[lessonKeyOrNodeId];
  if (direct) return direct;
  for (const info of Object.values(map)) {
    if (
      info.lesson.lesson_id === lessonKeyOrNodeId ||
      info.lesson.id === lessonKeyOrNodeId
    ) {
      return info;
    }
  }
  return undefined;
}

type FolderPageProps = {
  folderId: string;
};

function FolderAmbientDecor() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
    >
      <svg
        viewBox="0 0 620 330"
        fill="none"
        className="absolute -right-34 -bottom-12 h-[300px] w-[660px] text-[#c46b72]"
      >
        <path
          d="M78 332C134 276 190 280 234 234C264 202 246 174 288 152C357 116 459 110 535 50C584 11 596 -19 588 -60"
          stroke="currentColor"
          strokeWidth="10"
          strokeLinecap="round"
        />
        <path
          d="M210 358C264 306 313 302 358 256C389 224 371 198 414 176C482 141 564 128 637 70C684 33 696 4 690 -36"
          stroke="currentColor"
          strokeWidth="10"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

type LessonWithChatPanelProps = {
  lesson: RoadmapLessonOut;
  folderId: string;
  lessonsListVisible: boolean;
  chatVisible: boolean;
  onSelectLesson: (id: string) => void;
  onToggleLessonsList: VoidFunction;
  onToggleChat: VoidFunction;
  onCloseChat: VoidFunction;
  onClosePanel: VoidFunction;
};

function LessonWithChatPanelInner({
  lesson,
  folderId,
  lessonsListVisible,
  chatVisible,
  onSelectLesson,
  onToggleLessonsList,
  onToggleChat,
  onCloseChat,
  onClosePanel,
}: LessonWithChatPanelProps) {
  const {
    width: chatPanelWidth,
    isResizing: chatPanelResizing,
    handleMouseDown: handleChatResizeMouseDown,
  } = usePanelResize({
    defaultWidth: 418,
    minWidth: 334,
    maxWidth: 560,
    direction: "right",
    storageKey: "novalearn:lesson-chat-width",
  });

  const setTaggedPartRef = useRef<((text: string) => void) | null>(null);
  const switchToNotebookRef = useRef<VoidFunction | null>(null);
  const scrollToHighlightRef = useRef<((text: string) => void) | null>(null);
  const [currentBlockId, setCurrentBlockId] = useState<string | null>(null);
  const [inlineQuizAnswers, setInlineQuizAnswers] = useState<Map<string, AnswerRecord>>(() => new Map());

  const handleAskNova = useCallback(
    (text: string) => {
      if (!chatVisible) onToggleChat();
      requestAnimationFrame(() => {
        setTaggedPartRef.current?.(text);
      });
    },
    [chatVisible, onToggleChat],
  );

  const handleMarkNote = useCallback(() => {
    if (!chatVisible) onToggleChat();
    requestAnimationFrame(() => {
      switchToNotebookRef.current?.();
    });
  }, [chatVisible, onToggleChat]);

  return (
    <div className="folder-visual-heavy flex flex-1 overflow-hidden">
      <PageCard className="relative flex min-w-0 flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <LessonPanel
            lesson={lesson}
            folderId={folderId}
            lessonsListVisible={lessonsListVisible}
            chatVisible={chatVisible}
            onSelectLesson={onSelectLesson}
            onToggleLessonsList={onToggleLessonsList}
            onToggleChat={onToggleChat}
            onCloseChat={onCloseChat}
            onClosePanel={onClosePanel}
            onAskNova={handleAskNova}
            onMarkNote={handleMarkNote}
            onActiveBlockChange={setCurrentBlockId}
            onScrollToHighlightRef={scrollToHighlightRef}
            onInlineQuizAnswersChange={setInlineQuizAnswers}
          />
        </div>

        <AnimatePresence initial={false}>
          {chatVisible && (
            <motion.div
              initial={{ width: 0 }}
              animate={{
                width: chatPanelWidth,
                transition: chatPanelResizing
                  ? { duration: 0 }
                  : { type: "tween", duration: 0.25, ease: [0.4, 0, 0.2, 1] },
              }}
              exit={{
                width: 0,
                transition: {
                  type: "tween",
                  duration: 0.25,
                  ease: [0.4, 0, 0.2, 1],
                },
              }}
              className="relative shrink-0"
            >
              <div className="h-full overflow-hidden">
              <motion.div
                initial={{ x: chatPanelWidth, opacity: 0 }}
                animate={{
                  x: 0,
                  opacity: 1,
                  transition: chatPanelResizing
                    ? { duration: 0 }
                    : { type: "tween", duration: 0.25, ease: [0, 0, 0.2, 1] },
                }}
                exit={{
                  x: chatPanelWidth,
                  opacity: 0,
                  transition: {
                    type: "tween",
                    duration: 0.2,
                    ease: [0.4, 0, 1, 1],
                  },
                }}
                className="flex h-full"
                style={{
                  width: chatPanelWidth,
                  willChange: "transform, opacity",
                }}
              >
                <ChatSidePanel
                  folderId={folderId}
                  lessonId={lesson.lesson_id}
                  currentBlockId={currentBlockId}
                  inlineQuizAnswers={inlineQuizAnswers}
                  onClose={onToggleChat}
                  onSetTaggedPartRef={setTaggedPartRef}
                  onSwitchToNotebookRef={switchToNotebookRef}
                  onScrollToHighlightRef={scrollToHighlightRef}
                />
              </motion.div>
              </div>

              <div
                onMouseDown={handleChatResizeMouseDown}
                className="group absolute inset-y-0 left-0 z-20 flex w-3 -translate-x-1/2 cursor-col-resize items-center justify-center"
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize chat panel"
              >
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[#F4F4F5] transition-colors group-hover:bg-[#D4D4D8] group-active:bg-[#C0ADA1]" />
                <div className="pointer-events-none relative flex h-5.5 w-2 flex-col items-center justify-center rounded-full border border-[#E4E4E7] bg-white py-1.25 px-px transition-colors group-hover:bg-[#F0EFED] group-active:bg-[#E8E5E1]" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </PageCard>
    </div>
  );
}

const LessonWithChatPanel = memo(LessonWithChatPanelInner);

type SelectedLesson = {
  lesson: RoadmapLessonOut;
  detail: LessonSchema | null;
};

function FolderContent({ folderId }: FolderPageProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const rawUrlTab =
    searchParams.get("tab") ??
    (typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("tab")
      : null);
  const rawUrlLesson =
    searchParams.get("lesson") ??
    (typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("lesson")
      : null);

  const urlTabForContent =
    rawUrlLesson && rawUrlLesson.length > 0 && (rawUrlTab == null || rawUrlTab === "")
      ? ("lessons" as const)
      : rawUrlTab;

  const [initTab, setInitTab] = useState<FolderTabParam>(null);
  useLayoutEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") != null) return;
    const savedFolder = readFolderLessonsUi(folderId);
    const hasLessonInUrl =
      Boolean(new URLSearchParams(window.location.search).get("lesson")) ||
      Boolean(rawUrlLesson && rawUrlLesson.length > 0);
    const hasOpenLesson =
      hasLessonInUrl ||
      (typeof savedFolder?.selectedLessonId === "string" &&
        savedFolder.selectedLessonId.length > 0);
    const next = hasOpenLesson
      ? ("lessons" as const)
      : resolveInitialFolderTab(null, readSavedTab(folderId));
    if (hasOpenLesson) {
      writeSavedTab(folderId, "lessons");
    }
    queueMicrotask(() => {
      setInitTab(next);
    });
  }, [folderId, rawUrlLesson]);

  const [selectedTab, setSelectedTab] = useState<FolderTabParam | undefined>(undefined);

  useEffect(() => {
    if (rawUrlTab !== null) {
      queueMicrotask(() => {
        setInitTab(null);
        setSelectedTab(undefined);
      });
    }
  }, [rawUrlTab]);

  const tab = selectedTab !== undefined
    ? selectedTab
    : resolveDisplayedFolderTab(urlTabForContent, initTab);

  const { lessonMap, loading: lessonsLoading } = useLessons();

  const [selectedLesson, setSelectedLesson] = useState<SelectedLesson | null>(
    null,
  );
  const [lessonsListVisible, setLessonsListVisible] = useState(true);
  const [lastAccessedRefreshNonce, setLastAccessedRefreshNonce] = useState(0);

  useEffect(() => {
    queueMicrotask(() => {
      setLastAccessedRefreshNonce(0);
    });
  }, [folderId]);

  const [chatVisible, setChatVisible] = useState(false);
  const pendingChatOpenLogRef = useRef(false);

  const pendingRestoreLessonIdRef = useRef<string | null>(null);
  const panelsRestoredRef = useRef(false);
  const [lessonRestoreSettled, setLessonRestoreSettled] = useState(false);
  const [skipWidthAnim, setSkipWidthAnim] = useState(false);

  const folderIdScrollFlushRef = useRef(folderId);
  const lessonsScrollTopRef = useRef(0);
  const lessonsScrollPersistRafRef = useRef(0);
  const lessonsScrollRestoreDoneRef = useRef(false);
  const prevLessonsScrollLayoutRef = useRef<{
    multi: boolean;
    listVis: boolean;
  } | null>(null);
  const prevTabForScrollRef = useRef<typeof tab>(tab);

  useLayoutEffect(() => {
    if (folderIdScrollFlushRef.current !== folderId) {
      writeFolderLessonsUi(folderIdScrollFlushRef.current, {
        lessonsMainScrollTop: lessonsScrollTopRef.current,
      });
      lessonsScrollTopRef.current = 0;
      folderIdScrollFlushRef.current = folderId;
    }
    panelsRestoredRef.current = false;
    pendingRestoreLessonIdRef.current = null;
    lessonsScrollRestoreDoneRef.current = false;
    prevLessonsScrollLayoutRef.current = null;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLessonRestoreSettled(false);
    setSelectedLesson(null);
  }, [folderId]);

  useLayoutEffect(() => {
    if (panelsRestoredRef.current) return;
    panelsRestoredRef.current = true;
    const saved = readFolderLessonsUi(folderId);
    const lessonFromUrl =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("lesson")
        : null;
    const lessonToRestore =
      lessonFromUrl && lessonFromUrl.length > 0
        ? lessonFromUrl
        : saved && typeof saved.selectedLessonId === "string" && saved.selectedLessonId
          ? saved.selectedLessonId
          : null;

    if (!saved && !lessonToRestore) {
      queueMicrotask(() => {
        setLessonRestoreSettled(true);
      });
      return;
    }

    if (lessonToRestore) {
      pendingRestoreLessonIdRef.current = lessonToRestore;
    }

    queueMicrotask(() => {
      if (saved) {
        if (typeof saved.lessonsListVisible === "boolean") {
          setLessonsListVisible(saved.lessonsListVisible);
        }
        if (typeof saved.chatVisible === "boolean") {
          setChatVisible(saved.chatVisible);
        }
      }
      if (!lessonToRestore) {
        setLessonRestoreSettled(true);
      }
    });
  }, [folderId]);

  useEffect(() => {
    if (lessonRestoreSettled) return;
    const pendingId = pendingRestoreLessonIdRef.current;
    if (!pendingId) {
      queueMicrotask(() => {
        setLessonRestoreSettled(true);
      });
      return;
    }
    if (lessonsLoading) return;
    const info = findLessonInMap(lessonMap, pendingId);
    if (!info) {
      pendingRestoreLessonIdRef.current = null;
      writeFolderLessonsUi(folderId, { selectedLessonId: null });
      queueMicrotask(() => {
        setLessonRestoreSettled(true);
      });
      return;
    }
    queueMicrotask(() => {
      if (pendingRestoreLessonIdRef.current !== pendingId) return;
      pendingRestoreLessonIdRef.current = null;
      const canonical = info.lesson.lesson_id ?? info.lesson.id ?? null;
      if (canonical) {
        writeFolderLessonsUi(folderId, { selectedLessonId: canonical });
        if (typeof window !== "undefined" && pathname) {
          const p = new URLSearchParams(window.location.search);
          if (p.get("lesson") !== canonical) {
            p.set("tab", "lessons");
            p.set("lesson", canonical);
            window.history.replaceState(null, "", `${pathname}?${p.toString()}`);
          }
        }
      }
      setSkipWidthAnim(true);
      setSelectedLesson({ lesson: info.lesson, detail: info.detail });
      setLastAccessedRefreshNonce((n) => n + 1);
      setLessonRestoreSettled(true);
    });
  }, [lessonMap, lessonRestoreSettled, lessonsLoading, folderId, pathname]);

  const [practiceFullscreen, setPracticeFullscreen] = useState(false);
  const [practiceNoPadding, setPracticeNoPadding] = useState(false);
  const [practiceTabReselectKey, setPracticeTabReselectKey] = useState(0);
  const [feedbackFullscreen, setFeedbackFullscreen] = useState(false);

  const mainScrollRef = useRef<HTMLDivElement>(null);
  useAutoHideScrollbar(mainScrollRef);

  useEffect(() => {
    if (tab !== "lessons") {
      lessonsScrollRestoreDoneRef.current = false;
      prevLessonsScrollLayoutRef.current = null;
    }
  }, [tab]);

  useEffect(() => {
    if (prevTabForScrollRef.current === "lessons" && tab !== "lessons") {
      writeFolderLessonsUi(folderId, {
        lessonsMainScrollTop: lessonsScrollTopRef.current,
      });
    }
    prevTabForScrollRef.current = tab;
  }, [tab, folderId]);

  useEffect(() => {
    const el = mainScrollRef.current;
    if (!el || tab !== "lessons") return;
    lessonsScrollTopRef.current = el.scrollTop;
    const onScroll = () => {
      lessonsScrollTopRef.current = el.scrollTop;
      if (lessonsScrollPersistRafRef.current) return;
      lessonsScrollPersistRafRef.current = requestAnimationFrame(() => {
        lessonsScrollPersistRafRef.current = 0;
        writeFolderLessonsUi(folderId, { lessonsMainScrollTop: el.scrollTop });
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      if (lessonsScrollPersistRafRef.current) {
        cancelAnimationFrame(lessonsScrollPersistRafRef.current);
        lessonsScrollPersistRafRef.current = 0;
      }
    };
  }, [tab, folderId]);

  useLayoutEffect(() => {
    if (tab !== "lessons" || !lessonRestoreSettled || lessonsLoading) return;
    const el = mainScrollRef.current;
    if (!el) return;
    const saved = readFolderLessonsUi(folderId)?.lessonsMainScrollTop;
    const hasSaved =
      typeof saved === "number" && Number.isFinite(saved) && saved > 0;
    const layout = {
      multi: tab === "lessons" && !!selectedLesson,
      listVis: lessonsListVisible,
    };
    const prev = prevLessonsScrollLayoutRef.current;
    const layoutChanged =
      prev !== null &&
      (prev.multi !== layout.multi || prev.listVis !== layout.listVis);

    if (!hasSaved) {
      if (!lessonsScrollRestoreDoneRef.current) {
        lessonsScrollRestoreDoneRef.current = true;
      }
      prevLessonsScrollLayoutRef.current = layout;
      return;
    }

    if (!lessonsScrollRestoreDoneRef.current || layoutChanged) {
      const max = Math.max(0, el.scrollHeight - el.clientHeight);
      el.scrollTop = Math.min(saved, max);
      lessonsScrollTopRef.current = el.scrollTop;
      lessonsScrollRestoreDoneRef.current = true;
    }
    prevLessonsScrollLayoutRef.current = layout;
  }, [
    tab,
    folderId,
    lessonsLoading,
    lessonRestoreSettled,
    selectedLesson,
    lessonsListVisible,
  ]);

  const handleLessonClick = useCallback(
    (lessonId: string) => {
      pendingRestoreLessonIdRef.current = null;
      setLessonRestoreSettled(true);
      if (!selectedLesson) setSkipWidthAnim(true);
      const info = findLessonInMap(lessonMap, lessonId);
      if (!info) return;
      setSelectedLesson({ lesson: info.lesson, detail: info.detail });
      setLastAccessedRefreshNonce((n) => n + 1);
      setLessonsListVisible(true);
      const sid = info.lesson.lesson_id ?? info.lesson.id ?? null;
      if (sid) {
        writeFolderLessonsUi(folderId, {
          selectedLessonId: sid,
          lessonsListVisible: true,
        });
        if (typeof window !== "undefined" && pathname) {
          const p = new URLSearchParams(window.location.search);
          p.set("tab", "lessons");
          p.set("lesson", sid);
          window.history.replaceState(null, "", `${pathname}?${p.toString()}`);
        }
      }
    },
    [selectedLesson, lessonMap, folderId, pathname],
  );

  const toggleLessonsList = useCallback(
    () => setLessonsListVisible((v) => !v),
    [],
  );
  const closeLesson = useCallback(() => {
    setSelectedLesson(null);
    writeFolderLessonsUi(folderId, { selectedLessonId: null });
    if (typeof window !== "undefined" && pathname) {
      const p = new URLSearchParams(window.location.search);
      p.delete("lesson");
      const qs = p.toString();
      window.history.replaceState(null, "", qs ? `${pathname}?${qs}` : pathname);
    }
  }, [folderId, pathname]);
  const toggleChat = useCallback(() => {
    const willOpen = !chatVisible;
    pendingChatOpenLogRef.current = willOpen;
    setChatVisible(willOpen);
  }, [chatVisible]);
  const closeChat = useCallback(() => setChatVisible(false), []);

  useEffect(() => {
    if (!chatVisible || !pendingChatOpenLogRef.current) return;
    pendingChatOpenLogRef.current = false;
    const lesson = selectedLesson?.lesson;
    const lessonId = lesson?.lesson_id ?? lesson?.id;
    if (!lessonId) return;

    recordActivityEvent({
      event_type: "chat_opened",
      route_label: "Opened lesson chat",
      entity_type: "lesson",
      entity_id: lessonId,
      folder_id: folderId,
      lesson_id: lessonId,
      metadata: { surface: "lesson_panel" },
    });
  }, [chatVisible, folderId, selectedLesson]);

  const isLessonsMultiPanel = tab === "lessons" && !!selectedLesson;

  useEffect(() => {
    if (!lessonRestoreSettled) return;
    if (!isLessonsMultiPanel) {
      queueMicrotask(() => {
        closeChat();
      });
    }
  }, [isLessonsMultiPanel, closeChat, lessonRestoreSettled]);

  useEffect(() => {
    if (!lessonRestoreSettled) return;
    writeFolderLessonsUi(folderId, {
      lessonsListVisible,
      chatVisible,
    });
  }, [folderId, lessonsListVisible, chatVisible, lessonRestoreSettled]);

  const leftColumnAnimate = !isLessonsMultiPanel
    ? { width: "auto", opacity: 1 }
    : !lessonsListVisible
      ? { width: 0, opacity: 0 }
      : { width: 384, opacity: 1 };
  const isImmersiveTab =
    (tab === "practice" && practiceFullscreen) ||
    (tab === "feedback" && feedbackFullscreen);
  const showFolderAmbientDecor =
    !isImmersiveTab && !(tab === "practice" && practiceNoPadding);

  return (
    <div className="flex flex-1 gap-2 overflow-hidden">
      <motion.div
        animate={leftColumnAnimate}
        transition={
          skipWidthAnim
            ? { duration: 0 }
            : { duration: 0.3, ease: [0.4, 0, 0.2, 1] }
        }
        onAnimationComplete={() => setSkipWidthAnim(false)}
        className={cn(
          "overflow-hidden",
          !isLessonsMultiPanel && "flex-1",
          isLessonsMultiPanel && lessonsListVisible && "shrink-0",
        )}
      >
        <PageCard
          className={cn(
            "flex h-full flex-col overflow-hidden",
            !isImmersiveTab && "pt-5.5",
          )}
          style={{ minWidth: 384 }}
        >
          {!isImmersiveTab && (
            <div className="px-7">
              <FolderTabsNav
                onFolderTabChange={(param) => {
                  setSelectedTab(param);
                  setInitTab(param);
                }}
                onPracticeTabReselect={() =>
                  setPracticeTabReselectKey((k) => k + 1)
                }
              />
            </div>
          )}

          <div className="relative flex-1 h-full min-h-0">
            {showFolderAmbientDecor && <FolderAmbientDecor />}
            <div
              ref={mainScrollRef}
              className={cn(
                "relative z-10 h-full overflow-y-auto auto-hide-scrollbar",
                tab === "practice" && practiceNoPadding ? "p-0" : "px-7 pb-7",
              )}
            >
              {!tab && <Roadmap folderId={folderId} />}

              {tab === "lessons" && (
                <Lessons
                  folderId={folderId}
                  selectedLessonId={selectedLesson?.lesson.id ?? null}
                  lastAccessedRefreshNonce={lastAccessedRefreshNonce}
                  onLessonClick={handleLessonClick}
                  variant={isLessonsMultiPanel ? "list" : "grid"}
                />
              )}

              {tab === "practice" && (
                <PracticeQuestionsView
                  key={practiceTabReselectKey}
                  folderId={folderId}
                  onFullscreenChange={setPracticeFullscreen}
                  onNoPaddingChange={setPracticeNoPadding}
                />
              )}

              {tab === "feedback" && (
                <Feedback
                  key={folderId}
                  folderId={folderId}
                  isFullscreen={feedbackFullscreen}
                  toggleFullscreen={() => setFeedbackFullscreen((p) => !p)}
                />
              )}
            </div>
          </div>
        </PageCard>
      </motion.div>

      {isLessonsMultiPanel && selectedLesson && (
        <LessonWithChatPanel
          lesson={selectedLesson.lesson}
          folderId={folderId}
          lessonsListVisible={lessonsListVisible}
          chatVisible={chatVisible}
          onSelectLesson={handleLessonClick}
          onToggleLessonsList={toggleLessonsList}
          onToggleChat={toggleChat}
          onCloseChat={closeChat}
          onClosePanel={closeLesson}
        />
      )}

    </div>
  );
}

export function FolderPage({ folderId }: FolderPageProps) {
  return (
    <div className="flex flex-1 overflow-hidden">
      <Suspense
        fallback={
          <div className="flex flex-1 items-center justify-center">
            <LoaderIcon className="size-8 animate-spin text-[#71717A]" aria-hidden />
          </div>
        }
      >
        <LessonsProvider folderId={folderId}>
          <NotesProvider folderId={folderId}>
            <FolderContent folderId={folderId} />
          </NotesProvider>
        </LessonsProvider>
      </Suspense>
    </div>
  );
}
