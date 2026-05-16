import { useCallback, useEffect, useState } from "react"
import type { SessionHistoryItem } from "@/shared/api/generated/model"
import { ExplanationStart } from "./start"
import { ExplanationResults } from "./results"
import { ExplanationChat } from "./chat"
import { completeStepApi } from "../../../api/lessons-api"
import { progressUpdateFromCompleteStep, useLessons } from "../../../model/lessons-context"
import { readLessonUi, writeLessonUi } from "../../../lib/lesson-ui-state"
import type { ExplanationStage } from "../types"
import { notify } from "@/shared/lib/notify"


type ExplanationProps = {
    lessonId: string,
    navigateTesting(): void
    prefetchedHistory: SessionHistoryItem[] | null
    prefetchedHistoryLoading: boolean
    activeStage: ExplanationStage
    setActiveStage(stage: ExplanationStage): void
}

export function Explanation({ lessonId, navigateTesting, prefetchedHistory, prefetchedHistoryLoading, activeStage, setActiveStage }: ExplanationProps) {
    const { updateLessonProgress, markStepComplete } = useLessons()
    const [sessionId, setSessionId] = useState<string | undefined>(undefined)
    const [resultId, setResultId] = useState(() => readLessonUi(lessonId)?.explanationResultId ?? "")
    const [resumeInitialSessionId, setResumeInitialSessionId] = useState<string | undefined>(
        () => readLessonUi(lessonId)?.explanationFeynmanSessionId ?? undefined,
    )

    useEffect(() => {
        writeLessonUi(lessonId, { explanationResultId: resultId })
    }, [lessonId, resultId])

    const persistFeynmanSession = useCallback((id: string | null) => {
        writeLessonUi(lessonId, { explanationFeynmanSessionId: id })
    }, [lessonId])

    const startSession = useCallback(() => {
        setSessionId(undefined)
        setResultId("")
        setResumeInitialSessionId(undefined)
        writeLessonUi(lessonId, { explanationFeynmanSessionId: null })
        setActiveStage("chat")
    }, [lessonId, setActiveStage])

    const navigateResult = (id: string) => {
        setActiveStage("result")
        setResultId(id)
    }

    const navigateChatHistory = (historyId: string) => {
        setSessionId(historyId)
        setResumeInitialSessionId(undefined)
        setActiveStage("chat")
    }

    if (activeStage === "start")
        return (
            <ExplanationStart
                lessonId={lessonId}
                navigateChatHistory={navigateChatHistory}
                navigateResults={navigateResult}
                startSession={startSession}
                prefetchedHistory={prefetchedHistory}
                prefetchedHistoryLoading={prefetchedHistoryLoading}
            />
        )

    if (activeStage === "chat")
        return (
            <ExplanationChat
                navigateResults={navigateResult}
                lessonId={lessonId}
                historySessionId={sessionId}
                resumeInitialSessionId={resumeInitialSessionId}
                onPersistFeynmanSession={persistFeynmanSession}
            />
        )

    if (activeStage === "result")
        return (
            <ExplanationResults
                lessonId={lessonId}
                sessionId={resultId}
                navigateTesting={navigateTesting}
                restartSession={startSession}
            />
        )
}
