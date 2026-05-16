"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { motion } from "motion/react"
import { cn } from "@/shared/lib"
import { DocumentHistoryIcon, HideBarIcon, LoaderIcon, PencilEditIcon } from "@/shared/assets/icons"
import { useTests } from "../model"
import {
  normalizePracticeHistoryGroup,
  PRACTICE_HISTORY_GROUPS,
  type TestMode,
} from "../lib"
import { getQuestionTypes, type QuestionType } from "../api/tests-api"
import { ChatSidePanel } from "@/features/folder/ui/chat-side-panel"

import { WizardStepper } from "./wizard-stepper"
import { TopicSelection } from "./topic-selection"
import { QuestionsSetup } from "./questions-setup"
import { TestGeneration, type GenerationItemProgress } from "./test-generation"
import { TestTaking } from "./test-taking"
import { TestHistory } from "./test-history"

import { PracticeEmptyState } from "./practice-empty-state"
import { TestHistoryPanel } from "@/shared/ui/test-history-panel/test-history-panel"
import type { TestSessionOut } from "@/shared/api/generated/model"
import { Button } from "@/shared"
import { apiStreamOrigin } from "@/shared/api/api-fetch-origin"
import { getAccessToken } from "@/shared/lib/auth-storage"
import { notify } from "@/shared/lib/notify"
import { readFolderUi, writeFolderUi } from "@/features/folder/lib/lesson-ui-state"
import { useRouter } from "next/navigation"
type PracticeQuestionsViewProps = {
  folderId: string
  onFullscreenChange?: (isFullscreen: boolean) => void
  onNoPaddingChange?: (noPadding: boolean) => void
}

type ViewMode = "landing" | "wizard" | "taking" | "results"

type InnerTakingSurface = "test" | "results" | "review"

export function PracticeQuestionsView({ folderId, onFullscreenChange, onNoPaddingChange }: PracticeQuestionsViewProps) {
  const router = useRouter()
  
  const {
    sessions,
    sessionsLoading,
    activeSession,
    openSession,
    closeSession,
    generateTest,
    startTestSession,
    loadSessions,
    templates,
    loadTemplates,
    cancelGeneration,
    retryGeneration,
  } = useTests(folderId, "practice_questions");

  const [viewMode, setViewMode] = useState<ViewMode>("landing")
  const [wizardStep, setWizardStep] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [activeGroup, setActiveGroup] = useState(
    normalizePracticeHistoryGroup(readFolderUi(folderId)?.practiceQuestionsTestHistoryTab),
  )
  const [chatVisible, setChatVisible] = useState(false)
  const newChatRef = useRef<VoidFunction | null>(null)

  const handleActiveGroupChange = (group: string) => {
    const normalizedGroup = normalizePracticeHistoryGroup(group)
    writeFolderUi(folderId, { practiceQuestionsTestHistoryTab: normalizedGroup })
    setActiveGroup(normalizedGroup)
  }

  const [takingExpanded, setTakingExpanded] = useState(true)
  const [takingHistoryVisible, setTakingHistoryVisible] = useState(false)
  const [practiceChatQuestionId, setPracticeChatQuestionId] = useState<string | null>(null)
  const [hintRequestNonce, setHintRequestNonce] = useState(0)
  const [pendingHintText, setPendingHintText] = useState<string | null>(null)
  const [innerTakingView, setInnerTakingView] = useState<InnerTakingSurface>("test")
  const [takingSubmittingAnswers, setTakingSubmittingAnswers] = useState(false)

  const handlePracticeQuestionIdChange = useCallback((questionId: string) => {
    setPracticeChatQuestionId(questionId ? questionId : null)
    setHintRequestNonce(0)
    setPendingHintText(null)
  }, [])

  const handleTakingViewChange = useCallback((takingView: InnerTakingSurface) => {
    setInnerTakingView(takingView)
  }, [])

  const handlePracticeHintRequest = useCallback((hintText: string) => {
    setPendingHintText(hintText)
    setHintRequestNonce((n) => n + 1)
  }, [])

  const handleSubmittingAnswersChange = useCallback((submitting: boolean) => {
    setTakingSubmittingAnswers(submitting)
    if (submitting) setChatVisible(false)
  }, [])

  useEffect(() => {
    if (viewMode === "taking" || viewMode === "results") {
      const resultsSummaryWithNav = innerTakingView === "results"
      const immersive = !resultsSummaryWithNav
      onNoPaddingChange?.(immersive)
      onFullscreenChange?.(immersive)
      queueMicrotask(() => {
        setTakingExpanded(true)
      })
    } else if (viewMode === "landing") {
      onNoPaddingChange?.(false)
      onFullscreenChange?.(false)
    }
  }, [viewMode, innerTakingView, onNoPaddingChange, onFullscreenChange])

  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([])
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>([])
  const [questionTypesLoading, setQuestionTypesLoading] = useState(false)
  const [questionCounts, setQuestionCounts] = useState<Record<string, number>>({})
  const [testMode, setTestMode] = useState<TestMode>("practice")

  const [generationItems, setGenerationItems] = useState<GenerationItemProgress[]>([])
  const [generationDone, setGenerationDone] = useState(false)
  const templateIdRef = useRef<string | null>(null)

  const viewModeRef = useRef<ViewMode>(viewMode)
  useEffect(() => {
    viewModeRef.current = viewMode
  }, [viewMode])

  const totalQuestions = Object.values(questionCounts).reduce((a, b) => a + b, 0)

  const startWizard = useCallback(() => {
    setViewMode("wizard")
    setWizardStep(1)
    setSelectedNodeIds([])
    setQuestionTypes([])
    setQuestionCounts({})
    setTestMode("practice")
    setGenerationItems([])
    setGenerationDone(false)
    templateIdRef.current = null
    setIsFullscreen(true)
    onFullscreenChange?.(true)
    onNoPaddingChange?.(true)
  }, [onFullscreenChange, onNoPaddingChange])

  const backToLanding = useCallback(() => {
    setTakingSubmittingAnswers(false)
    setInnerTakingView("test")
    setViewMode("landing")
    closeSession()
    setIsFullscreen(false)
    onFullscreenChange?.(false)
    onNoPaddingChange?.(false)
  }, [closeSession, onFullscreenChange, onNoPaddingChange])

  const handleCountChange = useCallback((type: string, count: number) => {
    setQuestionCounts((prev) => ({ ...prev, [type]: count }))
  }, [])

  const handleWizardClose = useCallback(() => setViewMode("landing"), [])

  const handleWizardNext = useCallback(async () => {
    if (wizardStep === 1) {
      setWizardStep(2)
      setQuestionTypesLoading(true)
      try {
        const types = await getQuestionTypes(folderId)
        setQuestionTypes(types)
        const counts: Record<string, number> = {}
        for (const t of types) counts[t.label] = 0
        setQuestionCounts(counts)
      } catch {
        setQuestionTypes([])
        setQuestionCounts({})
      } finally {
        setQuestionTypesLoading(false)
      }
    } else if (wizardStep === 2) {
      setWizardStep(3)
      setGenerationDone(false)

      const initialItems: GenerationItemProgress[] = Object.entries(questionCounts)
        .filter(([, count]) => count > 0)
        .map(([label, count]) => ({
          label,
          requested: count,
          ready: 0,
          status: "pending" as const,
        }))
      setGenerationItems(initialItems)

      try {
        const typeCounts: Record<string, number> = {}
        for (const [label, count] of Object.entries(questionCounts)) {
          if (count > 0) {
            const qt = questionTypes.find(t => t.label === label)
            if (qt) typeCounts[qt.key] = count
          }
        }
        const hasTypeCounts = Object.keys(typeCounts).length > 0

        const templateId = await generateTest({
          folder_id: folderId,
          node_ids: selectedNodeIds,
          total_questions: totalQuestions || undefined,
          question_type_counts: hasTypeCounts ? typeCounts : undefined,
        })
        templateIdRef.current = templateId

        // Connect to SSE progress for real-time updates
        const { streamTemplateProgress } = await import("../api/tests-api")
        const abort = new AbortController()

        for await (const event of streamTemplateProgress(templateId, { signal: abort.signal })) {
          if (event.event === "progress") {
            setGenerationItems((prev) =>
              prev.map((item) => {
                const qt = questionTypes.find(t => t.label === item.label)
                const typeKey = qt?.key
                const node = typeKey ? event.nodes[typeKey] : undefined
                if (!node) return item
                const ready = node.generated
                const status: GenerationItemProgress["status"] =
                  ready >= item.requested ? "done" : ready > 0 ? "generating" : "pending"
                return { ...item, ready, status }
              }),
            )
          } else if (event.event === "complete") {
            setGenerationItems((prev) =>
              prev.map((i) => ({ ...i, ready: i.requested, status: "done" as const })),
            )
            // Pre-create session so "Start Test" is instant
            try {
              await startTestSession(templateId, testMode)
            } catch {
              // Session creation failed — user can still start manually
            }

            if (viewModeRef.current !== "wizard")
              notify({
                header: "Тест готов",
                content: "Он появится в разделе новых тестов.",
                button: {
                  buttonText: "Перейти к практике",
                  onButtonClick: () => {
                    writeFolderUi(folderId, { practiceQuestionsTestHistoryTab: PRACTICE_HISTORY_GROUPS.notStarted })
                    router.push(`/folders/${folderId}?tab=practice`)
                  }
                }
              })
            setGenerationDone(true)
            break
          } else if (event.event === "error") {
            setGenerationItems((prev) => prev.map((i) => ({ ...i, status: "done" as const })))
            setGenerationDone(true)
            break
          }
        }
      } catch {
        setGenerationItems((prev) => prev.map((i) => ({ ...i, status: "done" as const })))
        setGenerationDone(true)
      }
    }
  }, [wizardStep, folderId, selectedNodeIds, totalQuestions, questionCounts, questionTypes, generateTest, startTestSession, testMode, router])

  const handleWizardBack = useCallback(() => {
    if (wizardStep > 1) setWizardStep(wizardStep - 1)
    else backToLanding()
  }, [wizardStep, backToLanding])

  const handleStartTest = useCallback(async () => {
    setInnerTakingView("test")
    setTakingSubmittingAnswers(false)

    // Session was pre-created on complete event — just navigate
    if (activeSession?.session) {
      setTakingExpanded(true)
      setViewMode("taking")
      return
    }

    // Fallback: create session if pre-creation failed
    const tplId = templateIdRef.current
    if (!tplId) return
    try {
      await startTestSession(tplId, testMode)
      setTakingExpanded(true)
      setViewMode("taking")
    } catch {
      /* stay on wizard step 3 */
    }
  }, [startTestSession, testMode, activeSession])

  const handleDeleteTemplate = useCallback(async (templateId: string) => {
    try {
      const token = getAccessToken()
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      await fetch(
        `${apiStreamOrigin()}/api/v1/tests/templates/${templateId}`,
        { method: "DELETE", headers },
      )
      await loadTemplates()
    } catch {
      // silently fail
    }
  }, [loadTemplates])

  const handleOpenSession = useCallback(
    async (session: TestSessionOut) => {
      setTakingSubmittingAnswers(false)
      await openSession(session.id)
      setTakingExpanded(true)
      if (
        session.status === "graded"
        || session.status === "grading"
        || session.status === "submitted"
        || session.status === "completed"
      ) {
        setInnerTakingView("results")
        setViewMode("results")
      } else {
        setInnerTakingView("test")
        setViewMode("taking")
      }
    },
    [openSession],
  )

  const handleRetry = useCallback(async () => {
    if (!activeSession?.template?.id) return
    setInnerTakingView("test")
    setTakingSubmittingAnswers(false)
    try {
      await startTestSession(activeSession.template.id, testMode)
      setTakingExpanded(true)
      setViewMode("taking")
    } catch {
      /* keep current view; failed to start new attempt */
    }
  }, [activeSession, startTestSession, testMode])

  const toggleChat = useCallback(() => setChatVisible((v) => !v), [])

  const toggleTakingExpanded = useCallback(() => {
    setTakingExpanded((v) => {
      const next = !v
      queueMicrotask(() => {
        onNoPaddingChange?.(true)
        onFullscreenChange?.(next)
      })
      return next
    })
  }, [onNoPaddingChange, onFullscreenChange])

  const historySidebar = (
    <TestHistoryPanel
      sessions={sessions}
      activeGroup={activeGroup}
      setActiveGroup={handleActiveGroupChange}
      loading={sessionsLoading}
      onSelect={handleOpenSession}
      templates={templates}
      onTemplatesRefresh={loadTemplates}
      onCancelGeneration={cancelGeneration}
      onRetryGeneration={retryGeneration}
      onDeleteTemplate={handleDeleteTemplate}
      tab="practice-questions"
    />
  )

  const practiceSessionMode = (
    activeSession?.session.session_mode ?? "practice"
  ).toLowerCase()
  const isPracticeExamSession = practiceSessionMode === "exam"

  if ((viewMode === "taking" || viewMode === "results") && activeSession?.session) {
    return (
      <div className="flex h-full">
        <div className="min-w-0 flex-1">
          <TestTaking
            key={`${activeSession.session.id}-${viewMode}`}
            sessionId={activeSession.session.id}
            questions={activeSession.questions}
            gradedQuestionIds={activeSession.graded_question_ids}
            answersInitial={activeSession.answers}
            mode={activeSession.session.session_mode ?? "practice"}
            initialView={viewMode === "results" ? "results" : "test"}
            onBack={() => {
              backToLanding()
              loadSessions()
            }}
            onRetry={handleRetry}
            chatVisible={chatVisible}
            onToggleChat={isPracticeExamSession ? undefined : toggleChat}
            onToggleFullscreen={toggleTakingExpanded}
            isFullscreen={takingExpanded}
            historyVisible={!takingExpanded && takingHistoryVisible}
            onToggleHistory={() => setTakingHistoryVisible((v) => !v)}
            onCurrentQuestionIdChange={
              isPracticeExamSession ? undefined : handlePracticeQuestionIdChange
            }
            onTakingViewChange={handleTakingViewChange}
            onSubmittingAnswersChange={handleSubmittingAnswersChange}
            onPracticeHintRequest={handlePracticeHintRequest}
          />
        </div>

        {!isPracticeExamSession &&
          viewMode === "taking" &&
          (innerTakingView === "test" || innerTakingView === "review") &&
          !takingSubmittingAnswers && (
            <motion.div
              initial={false}
              animate={
                chatVisible
                  ? { width: 418, opacity: 1 }
                  : { width: 0, opacity: 0 }
              }
              transition={
                chatVisible
                  ? { width: { type: "spring", stiffness: 300, damping: 30 }, opacity: { duration: 0.25, delay: 0.05 } }
                  : { width: { type: "spring", stiffness: 400, damping: 35 }, opacity: { duration: 0.15 } }
              }
              className="shrink-0 overflow-hidden border-l border-[var(--ege-border)]"
            >
              <div className="flex h-full flex-col overflow-hidden" style={{ minWidth: 418 }}>
                {practiceChatQuestionId ? (
                  <ChatSidePanel
                    key={`${activeSession.session.id}-${practiceChatQuestionId}-${innerTakingView === "review" ? "review" : "practice"}`}
                    folderId={folderId}
                    showNotebook={false}
                    practiceChatScope={
                      practiceChatQuestionId
                        ? {
                          testSessionId: activeSession.session.id,
                          questionId: practiceChatQuestionId,
                          scopeType: innerTakingView === "review" ? "review" : undefined,
                        }
                        : undefined
                    }
                    hintRequestNonce={innerTakingView === "review" ? 0 : hintRequestNonce}
                    pendingHintText={innerTakingView === "review" ? null : pendingHintText}
                    tabsClassName="border-b border-[var(--ege-border)] px-5 py-3"
                    onNewChatRef={newChatRef}
                    headerAfter={
                      <div className="flex items-center gap-2">
                        <Button
                          iconOnly
                          variant="outline"
                          size="sm"
                          type="button"
                          onClick={() => newChatRef.current?.()}
                          className="flex items-center justify-center"
                          aria-label="Новый чат"
                          title="Новый чат"
                        >
                          <PencilEditIcon className="h-4 w-4" />
                        </Button>
                        <div className="h-4 w-px rounded-full bg-[var(--ege-border)]" />
                        <Button
                          iconOnly
                          variant="outline"
                          size="sm"
                          type="button"
                          onClick={toggleChat}
                          className="flex items-center justify-center"
                          aria-label="Закрыть чат"
                          title="Закрыть чат"
                        >
                          <HideBarIcon className="h-4 w-4" />
                        </Button>
                      </div>
                    }
                  />
                ) : (
                  <div
                    className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-4"
                    aria-busy
                    aria-label="Загрузка чата"
                  >
                    <LoaderIcon className="size-8 animate-spin text-[var(--ege-muted)]" aria-hidden />
                    <span className="text-center nova-text-p-base text-[var(--ege-muted)]">
                      Чат загружается...
                    </span>
                  </div>
                )}
              </div>
            </motion.div>
          )}

        <motion.div
          initial={false}
          animate={
            !takingExpanded && takingHistoryVisible
              ? { width: 350, opacity: 1 }
              : { width: 0, opacity: 0 }
          }
          transition={
            !takingExpanded && takingHistoryVisible
              ? { width: { type: "spring", stiffness: 300, damping: 30 }, opacity: { duration: 0.25, delay: 0.05 } }
              : { width: { type: "spring", stiffness: 400, damping: 35 }, opacity: { duration: 0.15 } }
          }
          className="shrink-0 overflow-hidden border-l border-[var(--ege-border)] bg-[var(--ege-canvas)]"
        >
          <div className="relative flex h-full min-h-0 flex-col bg-[var(--ege-canvas)]" style={{ minWidth: 300 }}>
            <div className="absolute top-2 right-4 z-10">
              <Button
                variant="outline"
                size="xs"
                type="button"
                onClick={() => setTakingHistoryVisible(false)}
                className="pointer-events-auto flex gap-x-1 items-center"
                aria-label="Скрыть историю тестов"
              >
                <DocumentHistoryIcon />
                История тестов
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <TestHistory
                sessions={sessions}
                loading={sessionsLoading}
                onSelect={handleOpenSession}
                templates={templates}
                onTemplatesRefresh={loadTemplates}
                onCancelGeneration={cancelGeneration}
                onRetryGeneration={retryGeneration}
                onDeleteTemplate={handleDeleteTemplate}
                hideScoreForIncompleteSessions
              />
            </div>
          </div>
        </motion.div>
      </div>
    )
  }

  if (viewMode === "wizard") {
    return (
      <div
        className={cn("flex gap-4 transition-[padding] duration-300 ease-in-out", isFullscreen && "px-4")}
        style={{ paddingRight: 16 }}
      >
        <div className="min-w-0 flex-1">
          {/* Keep the wizard header visible while the user scrolls through
              a long topic/questions list (FRO-28). Stickiness is scoped to
              this call site so the shared WizardStepper stays usable elsewhere. */}
          <div className="sticky top-0 z-10 bg-[var(--ege-canvas)]">
            <WizardStepper
              currentStep={wizardStep}
              onBack={handleWizardBack}
              onNext={wizardStep < 3 ? handleWizardNext : undefined}
              nextLabel="Подтвердить"
              nextDisabled={
                (wizardStep === 1 && selectedNodeIds.length === 0) ||
                (wizardStep === 2 && totalQuestions === 0)
              }
              isFullscreen={isFullscreen}
              onClose={handleWizardClose}
            />
          </div>

          <div className="mx-auto mt-8 max-w-[800px]">
            {wizardStep === 1 && (
              <TopicSelection
                folderId={folderId}
                selectedNodeIds={selectedNodeIds}
                onSelectionChange={setSelectedNodeIds}
              />
            )}
            {wizardStep === 2 && (
              <QuestionsSetup
                questionCounts={questionCounts}
                onCountChange={handleCountChange}
                mode={testMode}
                onModeChange={setTestMode}
                loading={questionTypesLoading}
              />
            )}
            {wizardStep === 3 && (
              <TestGeneration
                items={generationItems}
                allDone={generationDone}
                onStartTest={generationDone ? handleStartTest : undefined}
              />
            )}
          </div>
        </div>

      </div>
    )
  }

  return (
    <div
      className="flex transition-[padding] duration-300 ease-in-out"
      style={{ paddingRight: activeGroup ? "clamp(300px, 25vw, 400px)" : 145 }}
    >
      <div className="min-w-0 flex-1 pr-7">
        <PracticeEmptyState onCreateTest={startWizard} />
      </div>
      {historySidebar}
    </div>
  )
}
