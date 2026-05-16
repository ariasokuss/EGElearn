"use client"

import {
  useState,
  useCallback,
  useEffect,
  useLayoutEffect,
  startTransition,
  useMemo,
  useRef,
} from "react"
import type {
  CheckAnswerOut,
  TestQuestionOut,
  QuestionWithAnswerOut,
  SessionResultsOut,
  SessionAnswerOut,
  QuestionResultOut,
} from "@/shared/api/generated/model"
import { LoaderIcon, HideBarIcon } from "@/shared/assets/icons"

import { BackendTestQuestionView } from "@/features/folder/ui/lesson-panel/testing-tab/backend-test-question-view"
import type { PracticeQuestionControls } from "@/features/folder/ui/lesson-panel/testing-tab/practice-question-bar"
import { ResultsView } from "@/features/folder/ui/lesson-panel/testing-tab/results-view"
import { isMcqQuestion } from "@/features/folder/ui/lesson-panel/testing-tab/test-question-helpers"

import {
  checkAnswer,
  getTestDetail,
  getTestStatus,
  saveSessionAnswer,
  setQuestionSkipped,
  submitTest,
  uploadSessionAnswerDiagramImage,
} from "@/features/folder/api/lesson-test-api"
import {
  removeUploadedAnswerImageKey,
  syncAnswerImageKeys,
  type UploadedAnswerImageKeyMap,
} from "./answer-image-sync"
import {
  getSessionResultsApiV1TestsSessionsSessionIdResultsGet,
  getSessionFeedbackApiV1TestsSessionsSessionIdFeedbackGet,
} from "@/shared/api"
import { backendAnswersToLocal, computeResumeQuestionIndex } from "@/features/folder/ui/lesson-panel/testing-tab/session-answers-map"
import { pollForGradingResults } from "@/features/folder/ui/lesson-panel/testing-tab/use-grading-poll"
import { normalizeSessionQuestions } from "@/features/folder/ui/lesson-panel/testing-tab/testing-tab"
import {
  buildReviewRowsFromFeedback,
  type GradedReviewRow,
} from "@/features/folder/ui/lesson-panel/testing-tab/build-graded-review-rows"
import { GradedQuestionReviewView } from "@/features/folder/ui/lesson-panel/testing-tab/graded-question-review-view"
import { buildPracticeChecksFromSession } from "@/features/folder/ui/lesson-panel/testing-tab/build-practice-checks-from-session"
import { Button, Modal } from "@/shared/ui"
import { useTestGuard } from "@/shared/lib"
import { notify } from "@/shared/lib/notify"

type TestSessionQuestion = TestQuestionOut | QuestionWithAnswerOut

type TestTakingProps = {
  sessionId: string
  questions: (TestQuestionOut | QuestionWithAnswerOut)[]
  gradedQuestionIds?: string[]
  mode: string
  onBack: VoidFunction
  onRetry?: VoidFunction
  chatVisible?: boolean
  onToggleChat?: VoidFunction
  onToggleFullscreen: VoidFunction
  historyVisible?: boolean
  onToggleHistory?: VoidFunction
  isFullscreen?: boolean,
  answersInitial?: SessionAnswerOut[]
  onCurrentQuestionIdChange?: (questionId: string) => void
  initialView?: "test" | "results"
  onTakingViewChange?: (view: "test" | "results" | "review") => void
  onSubmittingAnswersChange?: (submitting: boolean) => void
  onPracticeHintRequest?: (hintText: string) => void
  resultsCloseInsetPastPaper?: boolean
  showOptionalQuestionSkip?: boolean
  showPastPaperAnswerImageAttach?: boolean
}

function normalizeSessionResultsOut(raw: SessionResultsOut | Record<string, unknown>): SessionResultsOut {
  const d = raw as Record<string, unknown>
  const questionsRaw = d.questions
  const questions: QuestionResultOut[] = Array.isArray(questionsRaw)
    ? questionsRaw.reduce<QuestionResultOut[]>((acc, q) => {
      if (q == null || typeof q !== "object") return acc
      const o = q as Record<string, unknown>
      const pointsRaw = o.points
      let points: number | null = null
      if (pointsRaw != null && pointsRaw !== "") {
        const n = Number(pointsRaw)
        if (Number.isFinite(n)) points = n
      }
      acc.push({
        question: String(o.question ?? ""),
        relation: String(o.relation ?? ""),
        points,
        max_points: Number(o.max_points ?? o.maxPoints ?? 0),
        is_skipped: Boolean(o.is_skipped ?? o.isSkipped ?? false),
      })
      return acc
    }, [])
    : []
  return {
    marks: d.marks == null || d.marks === "" ? null : Number(d.marks),
    total_marks: Number(d.total_marks ?? d.totalMarks ?? 0),
    mode: String(d.mode ?? ""),
    questions,
  }
}

function normalizeTestTakingQuestions(raw: unknown[]): TestSessionQuestion[] {
  return raw.filter((q): q is TestSessionQuestion => {
    if (q == null || typeof q !== "object") return false
    const o = q as TestQuestionOut
    return typeof o.id === "string" && typeof o.question === "string"
  })
}

export function clampQuestionIndex(index: number, length: number): number {
  if (length <= 0) return 0
  return Math.min(Math.max(0, index), length - 1)
}

export function TestTaking({
  sessionId,
  questions: rawQuestions,
  gradedQuestionIds,
  mode,
  onBack,
  onRetry,
  chatVisible,
  onToggleChat,
  onToggleFullscreen,
  historyVisible,
  onToggleHistory,
  isFullscreen,
  answersInitial,
  onCurrentQuestionIdChange,
  initialView = "test",
  onTakingViewChange,
  onSubmittingAnswersChange,
  onPracticeHintRequest,
  resultsCloseInsetPastPaper,
  showOptionalQuestionSkip = false,
  showPastPaperAnswerImageAttach = false,
}: TestTakingProps) {
  const isExam = mode.toLowerCase() === "exam"

  const { activateGuard, deactivateGuard } = useTestGuard()
  const [isModalOpen, setIsModalOpen] = useState(false)

  const [hintShownQids, setHintShownQids] = useState<Set<string>>(new Set())
  useEffect(() => {
    if (!chatVisible) setHintShownQids(new Set())
  }, [chatVisible])
  const questions = useMemo(() => normalizeTestTakingQuestions(rawQuestions), [rawQuestions])

  const [view, setView] = useState<"test" | "results" | "review">(
    initialView === "results" ? "results" : "test",
  )
  const [currentIdx, setCurrentIdx] = useState(0)
  const [mcqAnswers, setMcqAnswers] = useState<Record<number, number>>({})
  const [openAnswers, setOpenAnswers] = useState<Record<number, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [grading, setGrading] = useState(false)

  useEffect(() => {
    if (view === "test" || submitting || grading) {
      activateGuard()
    } else {
      deactivateGuard()
    }
    return () => deactivateGuard()
  }, [view, submitting, grading, activateGuard, deactivateGuard])

  const [resultsLoading, setResultsLoading] = useState(initialView === "results")
  const [results, setResults] = useState<SessionResultsOut | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewRows, setReviewRows] = useState<GradedReviewRow[]>([])
  const [reviewIdx, setReviewIdx] = useState(0)

  const [practiceCheckByQid, setPracticeCheckByQid] = useState<
    Record<string, CheckAnswerOut>
  >({})
  const [practiceCheckLoading, setPracticeCheckLoading] = useState(false)
  const [optionalSkippedByQuestionId, setOptionalSkippedByQuestionId] = useState<
    Record<string, boolean>
  >({})
  const [answerImagesByQuestionId, setAnswerImagesByQuestionId] = useState<
    Record<string, File[]>
  >({})
  const diagramSyncedFingerprintsRef = useRef<
    Record<string, UploadedAnswerImageKeyMap>
  >({})
  const pendingSavesRef = useRef<Set<Promise<void>>>(new Set())

  const trackSave = useCallback((p: Promise<void>) => {
    pendingSavesRef.current.add(p)
    void p.finally(() => pendingSavesRef.current.delete(p))
  }, [])

  const syncPendingDiagramImages = useCallback(
    async (questionId: string, files: File[]): Promise<string[]> => {
      if (!showPastPaperAnswerImageAttach || files.length === 0) return []
      const synced =
        diagramSyncedFingerprintsRef.current[questionId] ??
        (diagramSyncedFingerprintsRef.current[questionId] = {})
      return syncAnswerImageKeys({
        files,
        uploadedByFingerprint: synced,
        uploadFile: (file) =>
          uploadSessionAnswerDiagramImage(sessionId, questionId, file),
      })
    },
    [sessionId, showPastPaperAnswerImageAttach],
  )

  useEffect(() => {
    onSubmittingAnswersChange?.(submitting)
  }, [submitting, onSubmittingAnswersChange])

  const safeIdx = useMemo(
    () =>
      questions.length === 0
        ? 0
        : Math.min(Math.max(0, currentIdx), questions.length - 1),
    [currentIdx, questions.length],
  )

  useLayoutEffect(() => {
    if (!onCurrentQuestionIdChange) return
    if (view !== "test") {
      onCurrentQuestionIdChange("")
      return
    }
    if (questions.length === 0) {
      onCurrentQuestionIdChange("")
      return
    }
    const q = questions[safeIdx]
    onCurrentQuestionIdChange(q?.id ?? "")
  }, [view, questions, safeIdx, onCurrentQuestionIdChange])

  useEffect(() => {
    if (!answersInitial) return
    const { mcq, open } = backendAnswersToLocal(answersInitial, questions)
    startTransition(() => {
      setMcqAnswers(mcq)
      setOpenAnswers(open)
      setCurrentIdx(computeResumeQuestionIndex(questions as TestQuestionOut[], mcq, open))
    })
    const skipped: Record<string, boolean> = {}
    for (const ans of answersInitial) {
      if ("is_skipped" in ans && ans.is_skipped) {
        skipped[ans.question_id] = true
      }
    }
    if (Object.keys(skipped).length > 0) {
      setOptionalSkippedByQuestionId((prev) => ({ ...prev, ...skipped }))
    }
  }, [answersInitial, questions])

  useEffect(() => {
    if (isExam) return
    const fromServer = buildPracticeChecksFromSession(
      questions,
      gradedQuestionIds,
      answersInitial,
    )
    setPracticeCheckByQid((prev) => ({ ...fromServer, ...prev }))
  }, [isExam, gradedQuestionIds, answersInitial, questions])

  useEffect(() => {
    if (view === "review" && reviewRows.length > 0) {
      const safeIdx = clampQuestionIndex(reviewIdx, reviewRows.length)
      const rq = reviewRows[safeIdx]
      if (rq?.templateQuestion?.id && onCurrentQuestionIdChange) {
        onCurrentQuestionIdChange(rq.templateQuestion.id)
      }
    }
  }, [view, reviewIdx, reviewRows, onCurrentQuestionIdChange])

  useEffect(() => {
    const surface: "test" | "results" | "review" =
      view === "test" ? "test" : view === "review" ? "review" : "results"
    onTakingViewChange?.(surface)
  }, [view, onTakingViewChange])

  const openReviewAtQuestionIndex = useCallback(
    async (questionIndex: number) => {
      if (!results) return
      setView("review")
      setReviewLoading(true)
      setReviewRows([])
      try {
        const [fbRes, detail] = await Promise.all([
          getSessionFeedbackApiV1TestsSessionsSessionIdFeedbackGet(sessionId),
          getTestDetail(sessionId),
        ])
        if (fbRes.status !== 200) {
          setView("results")
          return
        }
        const items = fbRes.data.items
        if (items.length === 0) {
          setView("results")
          return
        }
        const templates = detail ? normalizeSessionQuestions(detail.questions) : []
        const templateByIndex = items.map(
          (_item: (typeof items)[number], i: number) => templates[i] ?? null,
        )
        setReviewRows(buildReviewRowsFromFeedback(items, results, templateByIndex))
        setReviewIdx(clampQuestionIndex(questionIndex, items.length))
      } finally {
        setReviewLoading(false)
      }
    },
    [sessionId, results],
  )

  const handleOpenAnswerReview = useCallback(() => {
    void openReviewAtQuestionIndex(0)
  }, [openReviewAtQuestionIndex])

  useEffect(() => {
    if (initialView !== "results") return
    const controller = new AbortController()
    let cancelled = false
    setResultsLoading(true)
    void (async () => {
      try {
        const status = await getTestStatus(sessionId)
        if (cancelled) return
        if (status?.status === "grading" || status?.status === "submitted" || status?.status === "completed") {
          setGrading(true)
          try {
            const graded = await pollForGradingResults(sessionId, controller.signal)
            if (cancelled) return
            setResults(normalizeSessionResultsOut(graded))
            return
          } catch {
            if (cancelled) return
          } finally {
            if (!cancelled) setGrading(false)
          }
        }
        const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(sessionId)
        if (cancelled) return
        if (resp.status === 200 && resp.data) {
          setResults(normalizeSessionResultsOut(resp.data))
          return
        }
      } catch {
        if (cancelled) return
      } finally {
        if (!cancelled) setResultsLoading(false)
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [sessionId, initialView])

  const saveAnswerAtIndex = useCallback(
    async (index: number) => {
      const q = questions[index]
      if (!q) return
      if (isMcqQuestion(q)) {
        const sel = mcqAnswers[index]
        if (sel === undefined || sel < 0) return
        await saveSessionAnswer(sessionId, q.id, String(sel))
      } else {
        const files = answerImagesByQuestionId[q.id] ?? []
        const imageKeys = await syncPendingDiagramImages(q.id, files)
        const text = openAnswers[index] ?? ""
        if (!text.trim() && imageKeys.length === 0) return
        await saveSessionAnswer(sessionId, q.id, text, imageKeys)
      }
    },
    [
      sessionId,
      questions,
      mcqAnswers,
      openAnswers,
      answerImagesByQuestionId,
      syncPendingDiagramImages,
    ],
  )

  const handleSubmitTest = useCallback(async () => {
    setSubmitting(true)

    try {
      // Drain any fire-and-forget saves from navigation so they don't race
      // with the submit transaction and cause a DB deadlock.
      if (pendingSavesRef.current.size > 0) {
        await Promise.allSettled([...pendingSavesRef.current])
      }

      const answers: { question_id: string; answer: string; image_keys?: string[] }[] = []
      for (const [idx, q] of questions.entries()) {
        if (isMcqQuestion(q)) {
          const sel = mcqAnswers[idx]
          if (sel !== undefined && sel >= 0) {
            answers.push({ question_id: q.id, answer: String(sel) })
          }
        } else {
          const text = (openAnswers[idx] ?? "").trim()
          const imageKeys = await syncPendingDiagramImages(
            q.id,
            answerImagesByQuestionId[q.id] ?? [],
          )
          if (text || imageKeys.length > 0) {
            answers.push({
              question_id: q.id,
              answer: text,
              image_keys: imageKeys,
            })
          }
        }
      }

      let submitResult = await submitTest(sessionId, answers)

      if (!submitResult) {
        // Backend rejected submit — check if session is already graded/grading
        try {
          const status = await getTestStatus(sessionId)
          if (status?.status === "graded" || status?.status === "completed" || status?.status === "grading") {
            submitResult = status as unknown as typeof submitResult
          }
        } catch { /* ignore */ }

        if (!submitResult) {
          notify({ header: "Не удалось отправить ответы", content: "Попробуй еще раз." })
          return
        }
      }

      const loadResults = async () => {
        if (submitResult.status === "graded" || submitResult.status === "completed") {
          try {
            const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(sessionId)
            if (resp.status === 200 && resp.data) {
              setResults(normalizeSessionResultsOut(resp.data))
            }
          } catch {
            // Results fetch failed; the fallback state handles it below.
          }
          return
        }
        setGrading(true)
        try {
          const graded = await pollForGradingResults(sessionId)
          setResults(normalizeSessionResultsOut(graded))
        } catch {
          try {
            const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(sessionId)
            if (resp.status === 200 && resp.data) {
              setResults(normalizeSessionResultsOut(resp.data))
            }
          } catch {
            // Both polling and fallback fetch failed; the fallback state handles it below.
          }
        } finally {
          setGrading(false)
        }
      }

      await loadResults()
      setView("results")
    } catch (err) {
      console.error("[handleSubmitTest] unexpected error", err)
      notify({ header: "Ошибка отправки", content: String(err) })
    } finally {
      setSubmitting(false)
    }
  }, [
    sessionId,
    questions,
    mcqAnswers,
    openAnswers,
    answerImagesByQuestionId,
    syncPendingDiagramImages,
  ])

  const handleNavigateBack = useCallback(() => {
    trackSave(saveAnswerAtIndex(currentIdx))
    setCurrentIdx((i) => Math.max(0, i - 1))
  }, [currentIdx, saveAnswerAtIndex, trackSave])

  const handleNavigateNext = useCallback(async () => {
    if (currentIdx === questions.length - 1) {
      await saveAnswerAtIndex(currentIdx)
      await handleSubmitTest()
    } else {
      trackSave(saveAnswerAtIndex(currentIdx))
      setCurrentIdx((i) => Math.min(questions.length - 1, i + 1))
    }
  }, [currentIdx, questions.length, saveAnswerAtIndex, handleSubmitTest, trackSave])

  const handlePracticeCheck = useCallback(async () => {
    const q = questions[safeIdx]
    if (!q) return
    if (optionalSkippedByQuestionId[q.id]) {
      await handleNavigateNext()
      return
    }
    setPracticeCheckLoading(true)
    try {
      if (isMcqQuestion(q)) {
        const sel = mcqAnswers[safeIdx]
        if (sel == null || sel < 0) return
        const res = await checkAnswer(sessionId, q.id, String(sel))
        if (res) {
          setPracticeCheckByQid((prev) => ({ ...prev, [q.id]: res }))
        }
        return
      }
      const text = (openAnswers[safeIdx] ?? "").trim()
      const files = answerImagesByQuestionId[q.id] ?? []
      const imageKeys = await syncPendingDiagramImages(q.id, files)
      if (text || imageKeys.length > 0) {
        const res = await checkAnswer(sessionId, q.id, text, imageKeys)
        if (res) {
          setPracticeCheckByQid((prev) => ({ ...prev, [q.id]: res }))
        }
      }
    } finally {
      setPracticeCheckLoading(false)
    }
  }, [
    sessionId,
    questions,
    safeIdx,
    mcqAnswers,
    openAnswers,
    answerImagesByQuestionId,
    syncPendingDiagramImages,
    optionalSkippedByQuestionId,
    handleNavigateNext,
  ])

  const handleConfirmExitTest = useCallback(async () => {
    await saveAnswerAtIndex(currentIdx)
    setIsModalOpen(false)
    onBack()
  }, [currentIdx, saveAnswerAtIndex, onBack])

  const currentQuestion = questions[safeIdx]

  const handleMcqSelectPractice = useCallback(
    (idx: number) => {
      const q = questions[safeIdx]
      if (q && isMcqQuestion(q)) {
        setPracticeCheckByQid((prev) => {
          if (!(q.id in prev)) return prev
          const next = { ...prev }
          delete next[q.id]
          return next
        })
      }
      setMcqAnswers((prev) => ({ ...prev, [safeIdx]: idx }))
    },
    [questions, safeIdx],
  )

  const handleOpenAnswerPractice = useCallback(
    (val: string) => {
      const q = questions[safeIdx]
      if (q && !isMcqQuestion(q)) {
        setPracticeCheckByQid((prev) => {
          if (!(q.id in prev)) return prev
          const next = { ...prev }
          delete next[q.id]
          return next
        })
      }
      setOpenAnswers((prev) => ({ ...prev, [safeIdx]: val }))
    },
    [questions, safeIdx],
  )

  const practiceControls: PracticeQuestionControls | null = useMemo(() => {
    if (isExam || !currentQuestion) return null
    const res = practiceCheckByQid[currentQuestion.id]
    const checkResult = res
      ? {
          isCorrect: res.is_correct,
          correctOptionIndex: res.correct_option_index ?? null,
          feedback: res.feedback ?? null,
          modelAnswer: res.model_answer ?? null,
          recommendation: res.recommendations ?? null,
          earnedMarks: res.earned_marks ?? null,
          totalMarks: res.total_marks ?? 0,
        }
      : null
    const isLast = safeIdx === questions.length - 1
    const hintText = currentQuestion.hint ?? null
    const hintUsed = hintShownQids.has(currentQuestion.id)
    const isSkipped = optionalSkippedByQuestionId[currentQuestion.id] === true
    const base = {
      hint: hintText,
      hintUsed,
      onShowHintInChat: hintText
        ? () => {
            if (hintUsed) return
            setHintShownQids((prev) => new Set(prev).add(currentQuestion.id))
            if (!chatVisible) onToggleChat?.()
            onPracticeHintRequest?.(hintText)
          }
        : undefined,
      onCheck: () => void handlePracticeCheck(),
      checkLoading: practiceCheckLoading,
      checkResult,
      isLast,
      onContinue: () => void handleNavigateNext(),
    }
    if (isMcqQuestion(currentQuestion)) {
      return {
        ...base,
        checkDisabled:
          !isSkipped &&
          (mcqAnswers[safeIdx] == null || mcqAnswers[safeIdx]! < 0),
      }
    }
    const hasText = (openAnswers[safeIdx] ?? "").trim().length > 0
    const hasImage =
      (answerImagesByQuestionId[currentQuestion.id] ?? []).length > 0
    return {
      ...base,
      checkDisabled: !isSkipped && !hasText && !hasImage,
    }
  }, [
    isExam,
    currentQuestion,
    practiceCheckByQid,
    practiceCheckLoading,
    mcqAnswers,
    openAnswers,
    answerImagesByQuestionId,
    optionalSkippedByQuestionId,
    safeIdx,
    handlePracticeCheck,
    handleNavigateNext,
    questions.length,
    chatVisible,
    onToggleChat,
    onPracticeHintRequest,
    hintShownQids,
  ])

  const optionalQuestionSkipForView = useMemo(() => {
    if (!showOptionalQuestionSkip || !currentQuestion) return null
    const qid = currentQuestion.id
    return {
      checked: optionalSkippedByQuestionId[qid] ?? false,
      onCheckedChange: (checked: boolean) => {
        // Optimistic local update — revert on API failure.
        if (checked) {
          setPracticeCheckByQid((prev) => {
            if (!(qid in prev)) return prev
            const next = { ...prev }
            delete next[qid]
            return next
          })
        }
        setOptionalSkippedByQuestionId((prev) => ({ ...prev, [qid]: checked }))
        void (async () => {
          const ok = await setQuestionSkipped(sessionId, qid, checked)
          if (!ok) {
            setOptionalSkippedByQuestionId((prev) => ({
              ...prev,
              [qid]: !checked,
            }))
          }
        })()
      },
    }
  }, [
    showOptionalQuestionSkip,
    currentQuestion,
    optionalSkippedByQuestionId,
    sessionId,
  ])

  const answerImageAttachForView = useMemo(() => {
    if (
      !showPastPaperAnswerImageAttach ||
      !currentQuestion ||
      isMcqQuestion(currentQuestion)
    ) {
      return null
    }
    const qid = currentQuestion.id
    const files = answerImagesByQuestionId[qid] ?? []
    return {
      files,
      onAddFiles: (newFiles: File[]) => {
        const existing = answerImagesByQuestionId[qid] ?? []
        const accepted = newFiles.slice(0, Math.max(0, 3 - existing.length))
        if (accepted.length === 0) return
        setPracticeCheckByQid((prev) => {
          if (!(qid in prev)) return prev
          const next = { ...prev }
          delete next[qid]
          return next
        })
        setAnswerImagesByQuestionId((prev) => ({
          ...prev,
          [qid]: [...(prev[qid] ?? []), ...accepted],
        }))
      },
      onRemoveAt: (index: number) => {
        setAnswerImagesByQuestionId((prev) => {
          const cur = [...(prev[qid] ?? [])]
          const removed = cur[index]
          if (removed) {
            const synced = diagramSyncedFingerprintsRef.current[qid]
            if (synced) removeUploadedAnswerImageKey(synced, removed)
          }
          cur.splice(index, 1)
          return { ...prev, [qid]: cur }
        })
      },
    }
  }, [
    showPastPaperAnswerImageAttach,
    currentQuestion,
    answerImagesByQuestionId,
  ])

  if (view === "review") {
    if (reviewLoading) {
      return (
        <div className="flex h-full min-h-[200px] items-center justify-center px-7">
          <LoaderIcon className="animate-spin text-[var(--ege-muted)]" aria-hidden />
          <span className="ml-3 nova-text-p-base text-[var(--ege-muted)]">
            Загружаем вопросы...
          </span>
        </div>
      )
    }
    if (reviewRows.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-4 px-7 py-16">
          <p className="text-center nova-text-p-base text-[var(--ege-muted)]">
            Не удалось загрузить ответы для этого теста.
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
      )
    }
    const safeReviewIdx = clampQuestionIndex(reviewIdx, reviewRows.length)
    const rq = reviewRows[safeReviewIdx]
    const isLastReview = safeReviewIdx >= reviewRows.length - 1
    return (
      <GradedQuestionReviewView
        row={rq}
        questionIndex={safeReviewIdx}
        total={reviewRows.length}
        onXClick={() => setView("results")}
        onBack={() => setReviewIdx(Math.max(0, safeReviewIdx - 1))}
        onNext={() => {
          if (isLastReview) setView("results")
          else setReviewIdx(Math.min(reviewRows.length - 1, safeReviewIdx + 1))
        }}
        isLast={isLastReview}
        chatVisible={chatVisible}
        onToggleChat={onToggleChat}
      />
    )
  }

  if (view === "results") {
    if (resultsLoading || grading) {
      return (
        <div className="flex h-full min-h-[200px] items-center justify-center px-7">
          <LoaderIcon className="animate-spin text-[var(--ege-muted)]" aria-hidden />
          <span className="ml-3 nova-text-p-base text-[var(--ege-muted)]">
            {grading ? "Проверяем тест..." : "Загружаем результаты..."}
          </span>
        </div>
      )
    }
    if (results) {
      return (
        <ResultsView
          onXClick={onBack}
          results={results}
          onPrimaryClick={() => void handleOpenAnswerReview()}
          onSecondaryClick={onRetry ?? onBack}
          onGoToQuestion={(idx) => void openReviewAtQuestionIndex(idx)}
          resultsCloseInsetPastPaper={resultsCloseInsetPastPaper}
        />
      )
    }
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center px-7">
        <p className="text-center nova-text-p-base text-[var(--ege-muted)]">
          Не удалось загрузить результаты.
        </p>
      </div>
    )
  }

  if (submitting) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center px-7">
        <LoaderIcon className="animate-spin text-[var(--ege-muted)]" aria-hidden />
        <span className="ml-3 nova-text-p-base text-[var(--ege-muted)]">
          Отправляем ответы...
        </span>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-7">
        <p className="text-center nova-text-p-base text-[var(--ege-muted)]">Вопросы не найдены.</p>
      </div>
    )
  }

  const headerButtons = (() => {
    const buttons: React.ReactNode[] = []

    if (onToggleChat && !chatVisible && !isExam) {
      buttons.push(
        <Button
          iconOnly
          size="sm"
          variant="outline"
          key="chat"
          type="button"
          onClick={onToggleChat}
          className="flex shrink-0 items-center justify-center"
          aria-label="Открыть чат"
          title="Открыть чат"
        >
          <HideBarIcon className="h-4 w-4 rotate-180" />
        </Button>,
      )
    }

    if (!isFullscreen && onToggleHistory && !historyVisible) {
      buttons.push(
        <Button
          iconOnly
          size="sm"
          variant="outline"
          key="history"
          type="button"
          onClick={onToggleHistory}
          className="flex shrink-0 items-center justify-center"
          aria-label="Открыть историю тестов"
          title="Открыть историю тестов"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width={16}
            height={16}
            viewBox="0 0 16 16"
            fill="none"
            className="text-[var(--ege-text)]"
            aria-hidden="true"
          >
            <path
              d="M12.6666 6.99998V6.66661C12.6666 4.15249 12.6666 2.89539 11.8856 2.11434C11.1045 1.33331 9.84745 1.33331 7.33332 1.33331C4.81922 1.33331 3.56213 1.33335 2.78109 2.11437C2.00006 2.89541 2.00005 4.15246 2.00003 6.66656L2 9.66665C1.99998 11.8583 1.99997 12.9541 2.60526 13.6917C2.71608 13.8267 2.83991 13.9505 2.97495 14.0614C3.71251 14.6666 4.80833 14.6666 6.99996 14.6666"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M4.66663 4.66669H9.99996M4.66663 7.33335H7.33329"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M12 12.3334L11 11.9667V10.3334M8 11.6667C8 13.3235 9.34315 14.6667 11 14.6667C12.6569 14.6667 14 13.3235 14 11.6667C14 10.0098 12.6569 8.66669 11 8.66669C9.34315 8.66669 8 10.0098 8 11.6667Z"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Button>,
      )
    }

    return buttons.length > 0 ? (
      <div className="flex items-center gap-2">{buttons}</div>
    ) : undefined
  })()

  return (
    <div className="flex h-full flex-col">
      <Modal
        title="Выйти из теста?"
        description="Прогресс сохранится, и ты сможешь продолжить из истории тестов."
        primaryButtonText="Подтвердить"
        secondaryButtonText="Отмена"
        isOpen={isModalOpen}
        onPrimaryClick={() => { void handleConfirmExitTest() }}
        onSecondaryClick={() => setIsModalOpen(false)}
      />
      <BackendTestQuestionView
        question={currentQuestion}
        questionIndex={safeIdx}
        total={questions.length}
        mcqAnswer={
          currentQuestion && isMcqQuestion(currentQuestion)
            ? (mcqAnswers[safeIdx] ?? null)
            : null
        }
        onMcqSelect={handleMcqSelectPractice}
        openAnswer={openAnswers[safeIdx] ?? ""}
        onOpenAnswer={handleOpenAnswerPractice}
        onArrowsClick={onToggleFullscreen}
        onXClick={() => setIsModalOpen(true)}
        onBack={() => void handleNavigateBack()}
        onNext={() => void handleNavigateNext()}
        isLast={safeIdx === questions.length - 1}
        headerExtra={headerButtons}
        isExpanded={isFullscreen}
        examMode={isExam}
        practiceControls={practiceControls}
        optionalQuestionSkip={optionalQuestionSkipForView}
        answerImageAttach={answerImageAttachForView}
      />
    </div>
  )
}
