import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import { LoaderIcon, PencilEditIcon } from "@/shared/assets/icons";
import { TestQuestionOut, TestSessionOut } from "@/shared/api/generated/model";
import { getTestDetail } from "../../api/lesson-test-api";
import { normalizeSessionQuestions } from "../lesson-panel/testing-tab/testing-tab";
import { backendAnswersToLocal } from "../lesson-panel/testing-tab/session-answers-map";
import { Button } from "@/shared/ui";
import type { PastPaperTestInfo } from "./types";
import { TestTaking } from "@/features/practice-questions/ui/test-taking";
import { ChatSidePanel } from "../chat-side-panel";
import { motion } from "motion/react";

type PastPaperTestProps = {
    folderId: string,
    onTestEnd(session: TestSessionOut): void,
    onTestExit: VoidFunction,
    testInfo: PastPaperTestInfo,
    onArrowsClick: VoidFunction
    onHomeClick: VoidFunction,

    onTogglePastPapersList(): void
    onCollapsePastPapersList(): void
    onClosePanel(): void
    isPastPapersListOpen?: boolean
}

export function PastPaperTest({ folderId, testInfo, onClosePanel, onTogglePastPapersList, onCollapsePastPapersList, isPastPapersListOpen }: PastPaperTestProps) {
    const [loading, setLoading] = useState(true)
    const [questions, setQuestions] = useState<TestQuestionOut[]>([])
    const [initialAnswers, setInitialAnswers] = useState<
        Parameters<typeof backendAnswersToLocal>[0] | undefined
    >(undefined)

    const [chatVisible, setChatVisible] = useState(false)
    const [practiceChatQuestionId, setPracticeChatQuestionId] = useState<string | null>(null)
    const [hintRequestNonce, setHintRequestNonce] = useState(0)
    const [pendingHintText, setPendingHintText] = useState<string | null>(null)
    const [takingSubmitting, setTakingSubmitting] = useState(false)
    const newChatRef = useRef<VoidFunction | null>(null)

    const { session, status } = testInfo
    const isExam = session?.session_mode?.toLowerCase() === "exam"
    const isPractice = !isExam

    useEffect(() => {
        let cancelled = false
        if (status === "none" || !session) return

        startTransition(() => {
            setLoading(true)
            setQuestions([])
        })

        getTestDetail(session.id).then(detail => {
            if (cancelled || !detail) return
            const questionList = normalizeSessionQuestions(detail.questions)
            setQuestions(questionList)
            setInitialAnswers(detail.answers)
            setLoading(false)
        }).catch(e => {
            console.error(e)
            setLoading(false)
            setQuestions([])
        })

        return () => { cancelled = true }
    }, [session, status])

    const handlePracticeQuestionIdChange = useCallback((questionId: string) => {
        setPracticeChatQuestionId(questionId || null)
        setHintRequestNonce(0)
        setPendingHintText(null)
    }, [])

    const handlePracticeHintRequest = useCallback((hintText: string) => {
        setPendingHintText(hintText)
        setHintRequestNonce(n => n + 1)
    }, [])

    const handleSubmittingAnswersChange = useCallback((submitting: boolean) => {
        setTakingSubmitting(submitting)
        if (submitting) setChatVisible(false)
    }, [])

    const toggleChat = useCallback(() => {
        setChatVisible(v => !v)
    }, [])

    const handleTakingViewChange = useCallback(
        (surface: "test" | "results" | "review") => {
            if (surface === "results") {
                onCollapsePastPapersList()
            }
        },
        [onCollapsePastPapersList],
    )

    if (!session) return null

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        )
    }

    if (questions.length === 0) {
        return (
            <div className="py-16 text-center nova-text-p-base text-[#71717A]">
                Failed to load questions.
            </div>
        )
    }

    const initialView = status === "result" ? "results" : "test"

    return (
        <div className="flex h-full">
            <div className="min-w-0 flex-1">
                <TestTaking
                    key={session.id}
                    sessionId={session.id}
                    questions={questions}
                    answersInitial={initialAnswers}
                    mode={session.session_mode ?? "practice"}
                    initialView={initialView as "test" | "results"}
                    onBack={onClosePanel}
                    onToggleFullscreen={onTogglePastPapersList}
                    isFullscreen={status === "result" || !isPastPapersListOpen}
                    onTakingViewChange={handleTakingViewChange}
                    chatVisible={isPractice ? chatVisible : undefined}
                    onToggleChat={isPractice ? toggleChat : undefined}
                    onCurrentQuestionIdChange={isPractice ? handlePracticeQuestionIdChange : undefined}
                    onSubmittingAnswersChange={handleSubmittingAnswersChange}
                    onPracticeHintRequest={isPractice ? handlePracticeHintRequest : undefined}
                    resultsCloseInsetPastPaper
                    showOptionalQuestionSkip
                    showPastPaperAnswerImageAttach
                />
            </div>

            {isPractice && !takingSubmitting && (
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
                    className="shrink-0 overflow-hidden border-l border-[#F4F4F5]"
                >
                    <div className="flex h-full flex-col overflow-hidden" style={{ minWidth: 418 }}>
                        {practiceChatQuestionId ? (
                            <ChatSidePanel
                                key={`${session.id}-${practiceChatQuestionId}`}
                                folderId={folderId}
                                showNotebook={false}
                                practiceChatScope={{
                                    testSessionId: session.id,
                                    questionId: practiceChatQuestionId,
                                }}
                                hintRequestNonce={hintRequestNonce}
                                pendingHintText={pendingHintText}
                                tabsClassName="border-b border-[#E8E5E180] px-5 py-3"
                                onNewChatRef={newChatRef}
                                headerAfter={
                                    <div className="flex items-center gap-2">
                                        <Button
                                            iconOnly
                                            variant="outline"
                                            size="sm"
                                            type="button"
                                            onClick={() => newChatRef.current?.()}
                                            aria-label="New chat"
                                            title="New chat"
                                        >
                                            <PencilEditIcon className="h-4 w-4" />
                                        </Button>
                                        <div className="h-4 w-px rounded-full bg-[#F4F4F5]" />
                                        <Button
                                            iconOnly
                                            variant="outline"
                                            size="sm"
                                            type="button"
                                            onClick={toggleChat}
                                            aria-label="Close chat"
                                            title="Close chat"
                                        >
                                            <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 16 16" fill="none">
                                                <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                            </svg>
                                        </Button>
                                    </div>
                                }
                            />
                        ) : null}
                    </div>
                </motion.div>
            )}
        </div>
    )
}
