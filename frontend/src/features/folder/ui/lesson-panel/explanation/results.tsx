import { ChevronRightIcon, CircleCheckIcon, LoaderIcon } from "@/shared/assets/icons";
import { useEffect, useReducer, useRef, useState } from "react";
import { Button, cn } from "@/shared";
import { getSessionFeedbackApiV1FeynmanSessionSessionIdFeedbackGet } from "@/shared/api";
import { SessionFeedbackRead } from "@/shared/api/generated/model";

import { coercePointScore, feedbackTextAt, sumCoveredPoints } from "./feynman-points";
import { scoreMessage } from "../testing-tab/utils";
import { completeStepApi } from "@/features/folder/api/lessons-api";
import { progressUpdateFromCompleteStep, useLessons } from "@/features/folder/model/lessons-context";
import { notify } from "@/shared/lib/notify";


type FeedbackDropdownProps = FeedbackDataPoint & {
    defaultOpen?: boolean
}

function FeedbackDropdown({ title, feedback, score, didCover, defaultOpen = false }: FeedbackDropdownProps) {
    const [isOpen, setIsOpen] = useState(defaultOpen)

    return (
        <div className={cn("px-3 py-3 transition-colors rounded-[16px]", isOpen ? "bg-[#FAF9F7]" : "hover:bg-[#F9F9F9]")}>
            <div
                onClick={() => didCover ? setIsOpen(prev => !prev) : null}
                className={cn(
                    "flex items-start gap-x-2 transition-colors",
                    didCover ? "cursor-pointer" : "cursor-default",
                    isOpen ? "text-[#242529]" : "text-[#8A8F98]"
                )}
            >
                <div className="flex size-6 items-center justify-center shrink-0">
                    <ChevronRightIcon
                        className={cn(
                            "h-[12px] w-[6px] stroke-[2.2px] transition-transform",
                            isOpen && "rotate-90",
                            didCover ? "text-[#242529]" : "text-[#8A8F98]"
                        )}
                    />
                </div>

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5">
                    <p className="nova-text-label-medium-regular text-[14.9px]">{title}</p>

                    {didCover
                        ? <p className="nova-text-label-medium-regular">{score}/5</p>
                        : <p className="py-0.5 px-1.5 bg-[#F1ECE9] rounded-full nova-text-label-tiny text-[#71717A]">Did not cover</p>
                    }
                </div>
            </div>
            <div className={cn("grid transition-all", isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
                <div className="min-h-0 overflow-hidden">
                    <p className="pl-8 pr-2 pb-1 nova-text-label-medium-regular text-[14.9px] text-[#8A8F98]">{feedback}</p>
                </div>
            </div>
        </div>
    )
}

type FeedbackData = {
    stars: number,
    percent: number,
    points: FeedbackDataPoint[]
}
type FeedbackDataPoint = {
    title: string,
    score: number,
    didCover?: boolean
    feedback: string
}

function backendToLocal(data: SessionFeedbackRead): FeedbackData {
    const covered = data.session.covered_points ?? [];
    const score_sum = sumCoveredPoints(covered);
    const score_total = Math.max(covered.length, 1) * 5;
    const percent = Math.round((score_sum / score_total) * 100);
    const feedbackList = data.session.feedback ?? [];
    return {
        stars: Math.floor(percent / 30),
        percent,
        points: data.feynman_block.points.map((text, ind) => ({
            title: text,
            score: coercePointScore(covered[ind]),
            feedback: feedbackTextAt(feedbackList, ind),
            didCover: covered[ind] != null && covered[ind] !== false,
        })),
    };
}

type ExplanationResultsProps = {
    lessonId: string
    sessionId: string
    navigateTesting(): void
    restartSession(): void
}

type State = {
    results: FeedbackData | null;
    loading: boolean;
};

type Action =
    | { type: "fetch" }
    | { type: "done"; results: FeedbackData | null };

function reducer(_: State, action: Action): State {
    if (action.type === "fetch") return { results: null, loading: true };
    return { results: action.results, loading: false };
}

export function ExplanationResults({ lessonId, sessionId, navigateTesting, restartSession }: ExplanationResultsProps) {
    const { markStepComplete, updateLessonProgress, stepStatus, lessonMap } = useLessons()
    const stepStatusRef = useRef(stepStatus)
    const lessonMapRef = useRef(lessonMap)

    useEffect(() => {
        stepStatusRef.current = stepStatus
        lessonMapRef.current = lessonMap
    }, [stepStatus, lessonMap])

    const [{ results, loading }, dispatch] = useReducer(reducer, {
        results: null,
        loading: true
    })
    const firstCoveredPointIndex = results?.points.findIndex((point) => point.didCover) ?? -1

    useEffect(() => {
        let cancelled = false
        dispatch({ type: "fetch" })
        getSessionFeedbackApiV1FeynmanSessionSessionIdFeedbackGet(sessionId).then((resp) => {
            if (cancelled) return
            if (resp.status !== 200) {
                dispatch({ type: "done", results: null })
                return
            }
            dispatch({ type: "done", results: backendToLocal(resp.data) })

            const alreadyEarned = stepStatusRef.current[lessonId]?.feynman || lessonMapRef.current[lessonId]?.lesson.feynman_star
            const starGranted = !alreadyEarned && resp.data.all_covered && resp.data.session.covered_points?.every(point => Number(point) >= 3)
            if (starGranted)
                completeStepApi(lessonId, 2).then((r) => {
                    if (!r) return
                    updateLessonProgress(lessonId, progressUpdateFromCompleteStep(r))
                    markStepComplete(lessonId, 2)
                    notify({ header: "Feynman star earned", content: "You've earned the Feynman star for this lesson by explaining all of the subtopics clearly!" })
                })
        })
        return () => { cancelled = true }
    }, [lessonId, sessionId, updateLessonProgress, markStepComplete])

    if (loading) {
        return (
            <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        );
    }

    if (!results) {
        return (
            <div className="py-16 text-center nova-text-p-base text-[#71717A]">
                Failed to load session results.
            </div>
        )
    }

    return (
        <div className="flex-1 h-full overflow-y-auto px-8">
            <div className="w-full max-w-177 mx-auto py-8">
                <div className="flex flex-col gap-y-6 justify-center items-center w-full py-6 border border-[#F4F4F5] rounded-[16px]">
                    <div className="w-full max-w-58 flex flex-col gap-y-3 items-center">
                        <CircleCheckIcon />
                        <p className="nova-text-h-small text-[#242529]">{scoreMessage(results.percent)}</p>
                        <p className="text-center nova-text-p-base text-[#6A6B6E]">You explained {results.percent}% of the material excellently</p>
                    </div>

                    <div className="flex gap-x-2 nova-text-label-small text-[#242529]">
                        <Button
                            onClick={navigateTesting}
                        >
                            Go to testing
                        </Button>
                        <Button
                            variant="plain"
                            onClick={restartSession}
                        >
                            Try again
                        </Button>
                    </div>
                </div>

                <div className="flex flex-col gap-y-3 mt-3">
                    <p className="nova-text-h-small-sb text-[#242529]">Feedback</p>

                    <div className="flex flex-col gap-y-1.5 p-2 border border-[#E8E8EA] rounded-[24px]">
                        {results.points.map((point, index) =>
                            <FeedbackDropdown
                                key={point.title}
                                defaultOpen={index === firstCoveredPointIndex}
                                {...point}
                            />
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
