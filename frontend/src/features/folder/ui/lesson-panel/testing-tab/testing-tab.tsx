"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { SessionResultsOut, TestQuestionOut, TestSessionOut } from "@/shared/api/generated/model";
import { LoaderIcon, TestsFolderIconIcon } from "@/shared/assets/icons";

import {
  getTestDetail,
  getTestStatus,
  saveSessionAnswer,
  startTestSession,
  submitTest,
} from "../../../api/lesson-test-api";
import { completeStepApi } from "../../../api/lessons-api";
import type { UseLessonTabPrefetchReturn } from "../use-lesson-tab-prefetch";
import { BackendTestQuestionView } from "./backend-test-question-view";
import { GradedQuestionReviewView } from "./graded-question-review-view";
import { ResultsView } from "./results-view";
import { TestHistory } from "@/features/practice-questions/ui/test-history";
import { buildReviewRowsFromFeedback, type GradedReviewRow } from "./build-graded-review-rows";
import { isMcqQuestion } from "./test-question-helpers";
import {
  getSessionFeedbackApiV1TestsSessionsSessionIdFeedbackGet,
  getSessionResultsApiV1TestsSessionsSessionIdResultsGet,
} from "@/shared/api";
import { pollForGradingResults } from "./use-grading-poll";
import { progressUpdateFromCompleteStep, useLessons } from "../../../model/lessons-context";
import {
  backendAnswersToLocal,
  computeResumeQuestionIndex,
  isTestSessionFinishedForResults,
  isTestStatusReadyForResultsSurface,
} from "./session-answers-map";
import { Button } from "@/shared";
import { useTestGuard } from "@/shared/lib";
import { Modal } from "@/shared/ui";
import {
  isTestingSubView,
  readLessonUi,
  writeLessonUi,
} from "../../../lib/lesson-ui-state";
import { notify } from "@/shared/lib/notify";

function clampQuestionIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.min(Math.max(0, index), length - 1);
}

export function normalizeSessionQuestions(raw: unknown): TestQuestionOut[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((q): q is TestQuestionOut => {
    if (q == null || typeof q !== "object") return false;
    const o = q as TestQuestionOut;
    return typeof o.id === "string" && typeof o.question === "string";
  });
}

type TestingTabProps = {
  tabPrefetch: UseLessonTabPrefetchReturn;
  onTestStart: VoidFunction;
  onTestEnd: VoidFunction;
  onAnswerReviewModeChange?: (open: boolean) => void;
  lessonId: string | null;
  testingTabReselectKey?: number;
};

export function TestingTab({
  tabPrefetch,
  onTestStart,
  onTestEnd,
  onAnswerReviewModeChange,
  lessonId,
  testingTabReselectKey = 0,
}: TestingTabProps) {
  const { updateLessonProgress, markStepComplete, stepStatus } = useLessons();
  const refreshTestingHistoryRef = useRef(tabPrefetch.refreshTestingHistory);
  refreshTestingHistoryRef.current = tabPrefetch.refreshTestingHistory;
  const refreshLessonResultsRef = useRef(tabPrefetch.refreshLessonResults);
  refreshLessonResultsRef.current = tabPrefetch.refreshLessonResults;
  const onTestStartRef = useRef(onTestStart);
  onTestStartRef.current = onTestStart;
  const onTestEndRef = useRef(onTestEnd);
  onTestEndRef.current = onTestEnd;

  type TestState = {
    view: "start" | "test" | "results" | "review";
    currentIdx: number;
    currentResults: SessionResultsOut | null;
    backendSession: TestSessionOut | null;
    backendQuestions: TestQuestionOut[];
    backendMcqAnswers: Record<number, number>;
    backendOpenAnswers: Record<number, string>;
    submitting: boolean;
    grading: boolean;
    resultsSessionId: string | null;
    resultsLoading: boolean;
    reviewRows: GradedReviewRow[];
    reviewIdx: number;
    reviewLoading: boolean;
  };

  const initialTestState: TestState = {
    view: "start",
    currentIdx: 0,
    currentResults: null,
    backendSession: null,
    backendQuestions: [],
    backendMcqAnswers: {},
    backendOpenAnswers: {},
    submitting: false,
    grading: false,
    resultsSessionId: null,
    resultsLoading: false,
    reviewRows: [],
    reviewIdx: 0,
    reviewLoading: false,
  };

  type TestAction =
    | { type: "RESET" }
    | { type: "SET"; patch: Partial<TestState> };

  function testReducer(state: TestState, action: TestAction): TestState {
    switch (action.type) {
      case "RESET":
        return initialTestState;
      case "SET":
        return { ...state, ...action.patch };
    }
  }

  const [ts, dispatch] = useReducer(testReducer, initialTestState);
  const {
    view, currentIdx, currentResults, backendSession, backendQuestions,
    backendMcqAnswers, backendOpenAnswers, submitting, grading,
    resultsSessionId, resultsLoading, reviewRows, reviewIdx, reviewLoading,
  } = ts;
  const [resumeLoading, setResumeLoading] = useState(false);
  const [startLoading, setStartLoading] = useState(false);
  const { activateGuard, deactivateGuard } = useTestGuard();
  const [exitModalOpen, setExitModalOpen] = useState(false);
  const testRestoreInProgressRef = useRef(false);
  const restoreGenerationRef = useRef(0);

  useEffect(() => {
    if (view === "test" || submitting || grading) {
      activateGuard();
    } else {
      deactivateGuard();
    }
    return () => deactivateGuard();
  }, [view, submitting, grading, activateGuard, deactivateGuard]);
  const setView = useCallback((view: TestState["view"]) => dispatch({ type: "SET", patch: { view } }), []);
  const setCurrentIdx = useCallback((currentIdx: number) => dispatch({ type: "SET", patch: { currentIdx } }), []);
  const setCurrentResults = useCallback((currentResults: SessionResultsOut | null) => dispatch({ type: "SET", patch: { currentResults } }), []);
  const setBackendSession = useCallback((backendSession: TestSessionOut | null) => dispatch({ type: "SET", patch: { backendSession } }), []);
  const setBackendQuestions = useCallback((backendQuestions: TestQuestionOut[]) => dispatch({ type: "SET", patch: { backendQuestions } }), []);
  const setBackendMcqAnswers = useCallback((backendMcqAnswers: Record<number, number>) => dispatch({ type: "SET", patch: { backendMcqAnswers } }), []);
  const setBackendOpenAnswers = useCallback((backendOpenAnswers: Record<number, string>) => dispatch({ type: "SET", patch: { backendOpenAnswers } }), []);
  const setSubmitting = useCallback((submitting: boolean) => dispatch({ type: "SET", patch: { submitting } }), []);
  const setGrading = useCallback((grading: boolean) => dispatch({ type: "SET", patch: { grading } }), []);
  const setResultsSessionId = useCallback((resultsSessionId: string | null) => dispatch({ type: "SET", patch: { resultsSessionId } }), []);
  const setResultsLoading = useCallback((resultsLoading: boolean) => dispatch({ type: "SET", patch: { resultsLoading } }), []);
  const setReviewRows = useCallback((reviewRows: GradedReviewRow[]) => dispatch({ type: "SET", patch: { reviewRows } }), []);
  const setReviewIdx = useCallback((reviewIdx: number) => dispatch({ type: "SET", patch: { reviewIdx } }), []);
  const setReviewLoading = useCallback((reviewLoading: boolean) => dispatch({ type: "SET", patch: { reviewLoading } }), []);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "RESET" });
    setResumeLoading(false);
    setStartLoading(false);

    if (!lessonId) {
      return () => {
        cancelled = true;
      };
    }

    const persisted = readLessonUi(lessonId);
    const tv = persisted?.testingView;
    const tsid = persisted?.testingSessionId;
    if (
      !tsid ||
      !tv ||
      !isTestingSubView(tv) ||
      tv === "start"
    ) {
      return () => {
        cancelled = true;
      };
    }

    if (tv === "results" || tv === "review") {
      setResumeLoading(true);
      void (async () => {
        try {
          const detail = await getTestDetail(tsid);
          if (cancelled) return;
          if (!detail) {
            writeLessonUi(lessonId, {
              testingView: "start",
              testingSessionId: null,
              testActive: false,
            });
            return;
          }
          dispatch({ type: "SET", patch: { resultsSessionId: tsid, view: "results" } });
        } finally {
          if (!cancelled) setResumeLoading(false);
        }
      })();
    }

    if (tv === "test") {
      testRestoreInProgressRef.current = true;
      setResumeLoading(true);
      onTestStartRef.current();
      const genAtRestoreStart = restoreGenerationRef.current;
      void (async () => {
        try {
          const detail = await getTestDetail(tsid);
          if (cancelled || !detail) {
            writeLessonUi(lessonId, {
              testingView: "start",
              testingSessionId: null,
              testActive: false,
            });
            onTestEndRef.current();
            dispatch({ type: "RESET" });
            return;
          }
          if (genAtRestoreStart !== restoreGenerationRef.current) {
            return;
          }
          const questions = normalizeSessionQuestions(detail.questions);
          const { mcq, open } = backendAnswersToLocal(detail.answers, questions);
          dispatch({
            type: "SET",
            patch: {
              backendSession: detail.session,
              backendQuestions: questions,
              backendMcqAnswers: mcq,
              backendOpenAnswers: open,
              currentIdx: computeResumeQuestionIndex(questions, mcq, open),
              view: "test",
            },
          });
        } finally {
          testRestoreInProgressRef.current = false;
          if (!cancelled) setResumeLoading(false);
        }
      })();
    }

    return () => {
      cancelled = true;
      testRestoreInProgressRef.current = false;
    };
  }, [lessonId]);

  const viewRef = useRef(view);
  viewRef.current = view;
  useEffect(() => {
    if (testingTabReselectKey === 0) return;
    if (viewRef.current !== "results" && viewRef.current !== "review") return;
    dispatch({ type: "RESET" });
    setResumeLoading(false);
    setStartLoading(false);
  }, [testingTabReselectKey]);

  useEffect(() => {
    if (!resultsSessionId) {
      setResultsLoading(false);
      return;
    }
    let cancelled = false;
    setResultsLoading(true);
    setCurrentResults(null);

    const resetToStartAfterMissingResults = () => {
      if (cancelled) return;
      dispatch({
        type: "SET",
        patch: {
          resultsSessionId: null,
          currentResults: null,
          view: "start",
          reviewRows: [],
          reviewIdx: 0,
        },
      });
      if (lessonId) {
        writeLessonUi(lessonId, {
          testingView: "start",
          testingSessionId: null,
          testActive: false,
        });
      }
    };

    const loadResults = async () => {
      const status = await getTestStatus(resultsSessionId);
      if (cancelled) return;
      if (status?.status === "grading" || status?.status === "submitted") {
        const graded = await pollForGradingResults(resultsSessionId);
        if (!cancelled) setCurrentResults(graded);
        return;
      }
      const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(resultsSessionId);
      if (cancelled) return;
      if (resp.status === 200) {
        setCurrentResults(resp.data);
        return;
      }
      resetToStartAfterMissingResults();
    };

    loadResults()
      .catch(() => {
        if (cancelled) return;
        resetToStartAfterMissingResults();
      })
      .finally(() => {
        if (!cancelled) setResultsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lessonId, resultsSessionId, setCurrentResults, setResultsLoading]);

  const answerReviewNotifyRef = useRef(onAnswerReviewModeChange);
  answerReviewNotifyRef.current = onAnswerReviewModeChange;

  useEffect(() => {
    answerReviewNotifyRef.current?.(view === "review");
    return () => {
      answerReviewNotifyRef.current?.(false);
    };
  }, [view]);

  useEffect(() => {
    if (!lessonId || testRestoreInProgressRef.current) return;
    const sid =
      view === "start"
        ? null
        : (backendSession?.id ?? resultsSessionId ?? null);
    writeLessonUi(lessonId, {
      testingView: view,
      testingSessionId: sid,
      testActive: view === "test",
    });
  }, [lessonId, view, backendSession?.id, resultsSessionId]);

  const openReviewAtQuestionIndex = useCallback(
    async (questionIndex: number) => {
      const sessionId = resultsSessionId ?? backendSession?.id ?? null;
      if (!sessionId) return;
      setView("review");
      setReviewLoading(true);
      setReviewRows([]);
      try {
        const [fbRes, detail] = await Promise.all([
          getSessionFeedbackApiV1TestsSessionsSessionIdFeedbackGet(sessionId),
          getTestDetail(sessionId),
        ]);
        if (fbRes.status !== 200) {
          setView("results");
          return;
        }
        const items = fbRes.data.items;
        if (items.length === 0) {
          setView("results");
          return;
        }
        const templates = detail ? normalizeSessionQuestions(detail.questions) : [];
        const templateByIndex = items.map((_, i) => templates[i] ?? null);
        setReviewRows(buildReviewRowsFromFeedback(items, currentResults, templateByIndex));
        setReviewIdx(clampQuestionIndex(questionIndex, items.length));
      } finally {
        setReviewLoading(false);
      }
    },
    [
      resultsSessionId,
      backendSession?.id,
      currentResults,
      setView,
      setReviewLoading,
      setReviewRows,
      setReviewIdx,
    ],
  );

  const handleOpenAnswerReview = useCallback(() => {
    void openReviewAtQuestionIndex(0);
  }, [openReviewAtQuestionIndex]);

  const saveAnswerAtIndex = useCallback(
    async (index: number) => {
      if (!backendSession) return;
      const q = backendQuestions[index];
      if (!q) return;
      if (isMcqQuestion(q)) {
        const sel = backendMcqAnswers[index];
        if (sel === undefined || sel < 0) return;
        await saveSessionAnswer(backendSession.id, q.id, String(sel));
      } else {
        const text = backendOpenAnswers[index] ?? "";
        if (!text.trim()) return;
        await saveSessionAnswer(backendSession.id, q.id, text);
      }
    },
    [backendSession, backendQuestions, backendMcqAnswers, backendOpenAnswers],
  );

  const handleSubmitTest = useCallback(async () => {
    if (!backendSession) return;
    setSubmitting(true);

    const answers = backendQuestions.reduce<{ question_id: string; answer: string }[]>((acc, q, idx) => {
      if (isMcqQuestion(q)) {
        const sel = backendMcqAnswers[idx];
        if (sel !== undefined && sel >= 0) {
          acc.push({ question_id: q.id, answer: String(sel) });
        }
      } else {
        const text = (backendOpenAnswers[idx] ?? "").trim();
        if (text) {
          acc.push({ question_id: q.id, answer: text });
        }
      }
      return acc;
    }, []);

    let result = await submitTest(backendSession.id, answers);
    if (!result) {
      try {
        const status = await getTestStatus(backendSession.id);
        if (status && isTestStatusReadyForResultsSurface(status.status)) {
          result = {
            ...backendSession,
            status: status.status,
            earned_marks: status.earned_marks ?? backendSession.earned_marks,
            total_marks: status.total_marks ?? backendSession.total_marks,
            score: status.score ?? backendSession.score,
          };
        }
      } catch {
        /* fall through to submission failure notification */
      }
    }

    if (!result) {
      setSubmitting(false);
      notify({ header: "Не удалось отправить", content: "Не получилось отправить ответы. Попробуй ещё раз." });
      return;
    }

    const marks = {
      earned: 0,
      total: 0,
    }

    if (result.status === "graded" || result.status === "completed") {
      marks.earned = result.earned_marks ?? 0
      marks.total = result.total_marks

      setView("results")
      setResultsLoading(true);
      setSubmitting(false);
      const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(backendSession.id);
      setResultsLoading(false);
      if (resp.status === 200) setCurrentResults(resp.data);
    } else {
      setGrading(true);
      setSubmitting(false);
      try {
        const gradedResults = await pollForGradingResults(backendSession.id);
        marks.earned = gradedResults.marks ?? 0
        marks.total = gradedResults.total_marks
        setCurrentResults(gradedResults);
      } catch {
        const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(backendSession.id);
        if (resp.status === 200) {
          marks.earned = resp.data.marks ?? 0
          marks.total = resp.data.total_marks
          setCurrentResults(resp.data);
        }
      } finally {
        setGrading(false);
      }
    }

    if (lessonId) {
      refreshTestingHistoryRef.current();
      refreshLessonResultsRef.current();
      if (!stepStatus[lessonId]?.test && marks.earned / marks.total >= 0.7) {
        completeStepApi(lessonId, 3).then((r) => {
          if (!r) return;
          updateLessonProgress(lessonId, progressUpdateFromCompleteStep(r));
          markStepComplete(lessonId, 3);
          notify({ header: "Звезда за тест получена", content: "Ты набрал больше 70% за тест и получил звезду за этот урок." })
        });
      }
    }

    setView("results");
    onTestEnd();
  }, [
    backendSession,
    backendQuestions,
    backendMcqAnswers,
    backendOpenAnswers,
    stepStatus,
    lessonId,
    onTestEnd,
    setCurrentResults,
    setGrading,
    setSubmitting,
    setView,
    updateLessonProgress,
    markStepComplete,
    setResultsLoading,
  ]);

  const handleHistorySelect = useCallback(
    async (session: TestSessionOut) => {
      if (isTestSessionFinishedForResults(session)) {
        setResultsSessionId(session.id);
        setView("results");
        return;
      }
      setResumeLoading(true);
      setResultsSessionId(null);
      setReviewRows([]);
      setReviewIdx(0);
      setCurrentResults(null);
      onTestStart();
      try {
        const detail = await getTestDetail(session.id);
        if (!detail) {
          onTestEnd();
          return;
        }
        const questions = normalizeSessionQuestions(detail.questions);
        const { mcq, open } = backendAnswersToLocal(detail.answers, questions);
        setBackendSession(detail.session);
        setBackendQuestions(questions);
        setBackendMcqAnswers(mcq);
        setBackendOpenAnswers(open);
        setCurrentIdx(computeResumeQuestionIndex(questions, mcq, open));
        setView("test");
      } finally {
        setResumeLoading(false);
      }
    },
    [
      onTestStart,
      onTestEnd,
      setResultsSessionId,
      setReviewRows,
      setReviewIdx,
      setCurrentResults,
      setBackendSession,
      setBackendQuestions,
      setBackendMcqAnswers,
      setBackendOpenAnswers,
      setCurrentIdx,
      setView,
    ],
  );

  const prefetchForLesson =
    lessonId != null && tabPrefetch.lessonKey === lessonId;

  const templateMeta = prefetchForLesson ? tabPrefetch.testingTemplate : null;

  const templatePending = prefetchForLesson && tabPrefetch.testingTemplateLoading;

  const templateResolved =
    lessonId != null &&
    templateMeta != null &&
    templateMeta.lessonId === lessonId &&
    !tabPrefetch.testingTemplateLoading;

  const canStartTest =
    templateResolved && templateMeta.available === true && templateMeta.templateId != null;

  const noTemplateForLesson = templateResolved && !templateMeta.available;

  const availableButNoTemplateId =
    templateResolved && templateMeta.available === true && templateMeta.templateId == null;

  const backendHistory =
    prefetchForLesson && tabPrefetch.testingHistory != null ? tabPrefetch.testingHistory : [];

  const historyLoading = prefetchForLesson && tabPrefetch.testingHistoryLoading;

  if (!lessonId) return null;

  const handleStart = async () => {
    if (!lessonId || !templateMeta || templateMeta.lessonId !== lessonId || !templateMeta.templateId) {
      return;
    }
    setStartLoading(true);
    try {
      setResultsSessionId(null);
      setReviewRows([]);
      setReviewIdx(0);
      setCurrentIdx(0);
      setBackendMcqAnswers({});
      setBackendOpenAnswers({});
      onTestStart();

      const session = await startTestSession(templateMeta.templateId, "exam");
      if (!session) {
        onTestEnd();
        return;
      }

      const detail = await getTestDetail(session.id);
      if (!detail) {
        onTestEnd();
        return;
      }

      setBackendSession(session);
      setBackendQuestions(normalizeSessionQuestions(detail.questions));
      setView("test");
    } finally {
      setStartLoading(false);
    }
  };

  if (view === "start") {
    if (resumeLoading || startLoading) {
      return (
        <div className="mx-auto flex w-full max-w-[710px] min-h-[280px] flex-col items-center justify-center px-7 py-16">
          <LoaderIcon className="animate-spin text-[#71717A]" aria-hidden />
          <span className="mt-3 nova-text-p-base text-[#71717A]">
            Загружаем тест…
          </span>
        </div>
      );
    }
    return (
      <div className="mx-auto w-full max-w-[710px] px-7 py-6">
        <div className="flex flex-col rounded-2xl border border-[#E8E5E1] bg-white px-2 py-2">
          <h2 className="py-[16px] pl-[16px] nova-text-h-small-sb text-[#242529]">
            Проверь себя
          </h2>
          <div
            className="flex min-h-[280px] w-full flex-col items-center justify-center rounded-2xl border border-[#E8E5E1] bg-white px-4 py-4 shadow-[0px_4px_6px_-1px_rgba(0,0,0,0.04),0px_2px_4px_-2px_rgba(0,0,0,0.02)]"
          >
            {templatePending ? (
              <LoaderIcon className="animate-spin text-[#71717A]" aria-hidden />
            ) : (
              <>
                <TestsFolderIconIcon width={155} height={118} className="mb-5" />
                <p className="mb-6 w-3/5 text-center nova-text-label-small text-[#71717A]">
                  {canStartTest
                    ? "Для этого урока доступен готовый тест. Проверь, насколько хорошо ты понял тему."
                    : availableButNoTemplateId
                      ? "Тест отмечен как доступный, но идентификатор не получен. Попробуй позже или обратись в поддержку."
                      : noTemplateForLesson
                        ? "Для этого урока пока нет готового теста."
                        : "Не удалось определить доступность теста."}
                </p>
                <Button
                  variant="outline"
                  size="l"
                  type="button"
                  disabled={!canStartTest}
                  onClick={handleStart}
                  className="my-[24px] disabled:cursor-not-allowed"
                >
                  Начать тест
                </Button>
              </>
            )}
          </div>
        </div>

        <div className="mt-6">
          <TestHistory
            sessions={backendHistory}
            loading={!!historyLoading}
            onSelect={handleHistorySelect}
          />
        </div>
      </div>
    );
  }

  if (view === "results") {
    if (startLoading) {
      return (
        <div className="flex h-full min-h-[200px] items-center justify-center px-7">
          <LoaderIcon className="animate-spin text-[#71717A]" aria-hidden />
          <span className="ml-3 nova-text-p-base text-[#71717A]">
            Загружаем тест…
          </span>
        </div>
      );
    }
    if (resultsLoading) {
      return (
        <div className="flex h-full min-h-[200px] items-center justify-center px-7">
          <LoaderIcon className="animate-spin" aria-hidden />
          <span className="ml-3 nova-text-p-base text-[#71717A]">
            Загружаем результаты…
          </span>
        </div>
      );
    }
    if (currentResults) {
      return (
        <ResultsView
          results={currentResults}
          onPrimaryClick={() => void handleOpenAnswerReview()}
          onSecondaryClick={handleStart}
          onGoToQuestion={(idx) => void openReviewAtQuestionIndex(idx)}
        />
      );
    }
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center px-7">
        <p className="text-center nova-text-p-base text-[#71717A]">
          Could not load results.
        </p>
      </div>
    );
  }

  if (view === "review") {
    if (reviewLoading) {
      return (
        <div className="flex h-full min-h-[200px] items-center justify-center px-7">
          <LoaderIcon className="animate-spin" aria-hidden />
          <span className="ml-3 nova-text-p-base text-[#71717A]">
            Загружаем вопросы…
          </span>
        </div>
      );
    }
    if (reviewRows.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-4 px-7 py-16">
          <p className="text-center nova-text-p-base text-[#71717A]">
            Не удалось загрузить отвеченные вопросы для этой сессии.
          </p>
          <Button
            variant="outline"
            size="l"
            type="button"
            onClick={() => setView("results")}
          >
            К результатам
          </Button>
        </div>
      );
    }
    const safeReviewIdx = clampQuestionIndex(reviewIdx, reviewRows.length);
    const rq = reviewRows[safeReviewIdx];
    const isLastReview = safeReviewIdx >= reviewRows.length - 1;
    return (
      <GradedQuestionReviewView
        row={rq}
        questionIndex={safeReviewIdx}
        total={reviewRows.length}
        onXClick={() => setView("results")}
        onBack={() => setReviewIdx(Math.max(0, safeReviewIdx - 1))}
        onNext={() => {
          if (isLastReview) setView("results");
          else setReviewIdx(Math.min(reviewRows.length - 1, safeReviewIdx + 1));
        }}
        isLast={isLastReview}
      />
    );
  }

  if (backendQuestions.length > 0) {
    const safeIdx = Math.min(Math.max(0, currentIdx), backendQuestions.length - 1);
    const current = backendQuestions[safeIdx];
    const isLast = safeIdx === backendQuestions.length - 1;

    const onNavigateBack = () => {
      void saveAnswerAtIndex(safeIdx);
      setCurrentIdx(Math.max(0, safeIdx - 1));
    };

    const onNavigateNext = async () => {
      if (isLast) {
        await saveAnswerAtIndex(safeIdx);
        await handleSubmitTest();
      } else {
        void saveAnswerAtIndex(safeIdx);
        setCurrentIdx(Math.min(backendQuestions.length - 1, safeIdx + 1));
      }
    };

    const onExitTest = () => {
      void saveAnswerAtIndex(safeIdx);
      restoreGenerationRef.current += 1;
      if (lessonId) {
        writeLessonUi(lessonId, {
          testingView: "start",
          testingSessionId: null,
          testActive: false,
        });
      }
      dispatch({ type: "RESET" });
      onTestEnd();
      if (lessonId) {
        refreshTestingHistoryRef.current();
      }
    };

    if (submitting || grading) {
      return (
        <div className="flex h-full items-center justify-center">
          <LoaderIcon className="animate-spin" />
          <span className="ml-3 nova-text-p-base text-[#71717A]">
            {grading ? "Проверяем ответы..." : "Отправляем ответы..."}
          </span>
        </div>
      );
    }

    if (!current) {
      return (
        <div className="flex h-full items-center justify-center px-7">
          <p className="text-center nova-text-p-base text-[#71717A]">Не удалось загрузить этот вопрос.</p>
        </div>
      );
    }

    return (
      <div className="relative flex h-full flex-col">
        <Modal
          title="Выйти из теста?"
          description="Прогресс сохранится, и ты сможешь вернуться к нему через историю тестов."
          primaryButtonText="Подтвердить"
          secondaryButtonText="Отмена"
          isOpen={exitModalOpen}
          onPrimaryClick={() => { void onExitTest(); setExitModalOpen(false); }}
          onSecondaryClick={() => setExitModalOpen(false)}
          contained
        />
        <BackendTestQuestionView
          question={current}
          questionIndex={safeIdx}
          total={backendQuestions.length}
          mcqAnswer={isMcqQuestion(current) ? (backendMcqAnswers[safeIdx] ?? null) : null}
          onMcqSelect={(idx) => setBackendMcqAnswers({ ...backendMcqAnswers, [safeIdx]: idx })}
          openAnswer={backendOpenAnswers[safeIdx] ?? ""}
          onOpenAnswer={(val) => setBackendOpenAnswers({ ...backendOpenAnswers, [safeIdx]: val })}
          onXClick={() => setExitModalOpen(true)}
          onBack={() => void onNavigateBack()}
          onNext={() => void onNavigateNext()}
          isLast={isLast}
          examMode
        />
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center px-7">
      <p className="text-center nova-text-p-base text-[#71717A]">Не удалось загрузить вопросы теста.</p>
    </div>
  );
}
