import { MarkIcon, PastPaperExamIcon, PastPaperPracticeIcon } from "@/shared/assets/icons";
import { startTestSession } from "../../api/lesson-test-api";
import type { PastPaperTestInfo } from "./types";
import { useEffect, useRef } from "react";
import { Button } from "@/shared";

type PastPapersStartProps = {
    selectedPastPaperId: string | null
    setPastPaperTesting(value: PastPaperTestInfo): void
    onSessionsRefresh?: () => void
}

export function PastPapersStart({ selectedPastPaperId, setPastPaperTesting, onSessionsRefresh }: PastPapersStartProps) {
    const startingTest = useRef(false)

    useEffect(() => {
        startingTest.current = false
    }, [selectedPastPaperId])

    const handleStart = async (type: "practice" | "exam") => {
        if (!selectedPastPaperId || startingTest.current) return
        startingTest.current = true
        const session = await startTestSession(selectedPastPaperId, type)
        if (session) {
            setPastPaperTesting({ status: "taking", session })
            onSessionsRefresh?.()
        }
        startingTest.current = false
    }

    return (
        <div className="flex flex-col p-3 max-w-176 mx-auto border border-[#F1F1F3] rounded-[16px]">
            <p className="nova-text-h-small-sb text-[#242529]">How would you like to approach this paper?</p>
            <p className="mt-2.5 nova-text-label-small-regular text-[#A1A1AA]">Your choice shapes the experience — whether you get feedback along the way or save it all for the end</p>

            <div className="mt-5 flex gap-x-2 **:transition-colors cursor-default">
                <div className="flex-1 group flex flex-col items-start gap-y-4 py-5 px-4 border border-[#F1F1F3] rounded-[16px] hover:nova-shadow-triple transition-shadow hover:border-[#E2DDDB] has-[button:active]:bg-[#FAF8F7]">
                    <PastPaperPracticeIcon />

                    <p className="nova-text-label-base text-[#242529]">Practice mode</p>
                    <div className="h-px w-7/8 bg-[#F4F4F5] rounded-full" />

                    <div className="flex flex-col gap-y-1.5 nova-text-label-small-regular text-[#71717A]">
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            Hints available
                        </div>
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            Mark each answer individually
                        </div>
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            Instant feedback per question
                        </div>
                    </div>

                    <Button
                        onClick={() => handleStart("practice")}
                    >
                        Select
                    </Button>
                </div>
                <div className="flex-1 group flex flex-col items-start gap-y-4 py-5 px-4 border border-[#F1F1F3] rounded-[16px] hover:nova-shadow-triple hover:border-[#E2DDDB] has-[button:active]:bg-[#FAF8F7]">
                    <PastPaperExamIcon />

                    <p className="nova-text-label-base text-[#242529]">Exam mode</p>
                    <div className="h-px w-7/8 bg-[#F4F4F5] rounded-full" />

                    <div className="flex flex-col gap-y-1.5 nova-text-label-small-regular text-[#71717A]">
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            Results at the end only
                        </div>
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            Timed experience
                        </div>
                        <div className="flex gap-x-1.5 ">
                            <MarkIcon />
                            No hints
                        </div>
                    </div>

                    <Button
                        onClick={() => handleStart("exam")}
                    >
                        Select
                    </Button>
                </div>
            </div>
        </div>
    )
}
