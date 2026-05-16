"use client"

import { LoaderIcon } from "@/shared/assets/icons"
import { useEffect, useState } from "react"
import { format } from "date-fns"
import { abortSessionApiV1FeynmanSessionSessionIdAbortPost } from "@/shared/api"
import type { SessionHistoryItem } from "@/shared/api/generated/model"

import { percentFromCoveredPoints } from "./feynman-points"
import { Button } from "@/shared"

type ExplanationProps = {
    lessonId: string,
    navigateResults(id: string): void,
    navigateChatHistory(id: string): void
    startSession(): void
    prefetchedHistory: SessionHistoryItem[] | null
    prefetchedHistoryLoading: boolean
}

export function ExplanationStart({
    lessonId,
    startSession,
    navigateChatHistory,
    navigateResults,
    prefetchedHistory,
    prefetchedHistoryLoading,
}: ExplanationProps) {
    const [history, setHistory] = useState<SessionHistoryItem[]>([])

    useEffect(() => {
        if (!lessonId || prefetchedHistoryLoading || prefetchedHistory === null) {
            return
        }
        let cancelled = false
        const raw = prefetchedHistory
        queueMicrotask(() => {
            if (cancelled) return
            setHistory(raw)
        })

        const abortPromises = raw.flatMap((entry) =>
            entry.session.status === "active"
                ? [abortSessionApiV1FeynmanSessionSessionIdAbortPost(entry.session.id, { exhausted: false })]
                : []
        )
        if (abortPromises.length === 0) {
            return () => {
                cancelled = true
            }
        }

        Promise.all(abortPromises).then((respAborted) => {
            if (cancelled) return
            setHistory(
                raw.filter(
                    (entry) =>
                        entry.session.status !== "active" ||
                        !respAborted.some((ab) => ab.status === 200 && ab.data.id === entry.session.id),
                ),
            )
        })
        return () => {
            cancelled = true
        }
    }, [lessonId, prefetchedHistoryLoading, prefetchedHistory])

    if (!lessonId) {
        return null
    }

    if (prefetchedHistoryLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        );
    }

    return (
        <div className="flex-1 h-full overflow-y-auto px-7">
            <div className="w-full max-w-177 mx-auto py-7">
                <div className="w-full h-60 p-2 border border-dashed border-[#DDD7D4] rounded-[20px]">
                    <div className="flex h-full w-full flex-col items-center justify-center rounded-[12px] border border-solid border-[#DDD7D45C] bg-[#FDFCFC] px-6">
                        <p className="nova-text-label-base text-[#1D1B20]">Teaching using the Feynman Technique</p>
                        <p className="mt-2 text-center nova-text-label-small text-[#242529]">Check your knowledge by explaining the lesson topic on artificial intelligence. You explain the AI topic as if to a friend or teacher, mimicking a real presentation. In the end, it will show how well you understand the topic and help improve your response</p>

                        <Button
                            className="mt-5"
                            onClick={startSession}
                        >
                            {history.length === 0
                                ? "Start"
                                : "Try again"
                            }
                        </Button>
                    </div>
                </div>

                <div className="mt-6 px-4 pt-12 pb-4 space-y-4">
                    {history.length === 0 && (
                        <p className="py-8 text-center nova-text-label-small-regular text-[#A1A1AA]">
                            No test history yet
                        </p>
                    )}

                    {history.map(entry =>
                        <div key={entry.session.id} className="flex flex-col gap-y-0.5 p-4 border border-[#F4F2F1] rounded-[16px]">
                            <p className="nova-text-label-small text-[#242529]">{percentFromCoveredPoints(entry.session.covered_points)}%</p>
                            <p className="flex items-center h-8 nova-text-label-small-regular text-[#72706F]">{format(entry.session.updated_at, "dd.MM.yy")}</p>
                            <div className="flex gap-x-2 nova-text-label-small text-[#242529]">
                                <Button
                                    variant="outline"
                                    onClick={() => navigateChatHistory(entry.session.id)}
                                >
                                    See chat
                                </Button>
                                <Button
                                    variant="plain"
                                    onClick={() => navigateResults(entry.session.id)}
                                >
                                    See results
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
