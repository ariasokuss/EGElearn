import { BookOpenIcon, BreakdownCheckIcon, BreakdownWarningIcon, CheckIcon, ChevronDownIcon, ExclamationTriangleIcon, LoaderIcon, StarFilledColoredIcon, StarFilledGrayIcon } from "@/shared/assets/icons";
import { useEffect, useReducer, useState } from "react";
import { Button, cn } from "@/shared";
import { CircularProgressbar } from "react-circular-progressbar"
import { getLessonResultsApiV1LearningLessonsLessonIdResultsGet } from "@/shared/api";
import type { LessonResultRead, RoadmapLessonOut } from "@/shared/api/generated/model";
import { lessonProgressToText } from "./utils";
import { Tippy } from "@/shared/ui";
import { STAR_TOOLTIP } from "@/features/folder/lib/tooltip-content";
import { lessonStepDisplayFlags, useLessons } from "@/features/folder/model/lessons-context";

type FeedbackDropdownProps = {
    title: string,
    percent: number,
    description: string,
    lessonBlockId?: string | null,
    navigateLessonPart(blockId: string): void
}

function BreakdownDropdown({ title, percent, description, lessonBlockId, navigateLessonPart }: FeedbackDropdownProps) {
    const [isOpen, setIsOpen] = useState(false)

    return (
        <div
            className="px-3"
        >
            <div
                onClick={() => setIsOpen(prev => !prev)}
                className="flex gap-x-3 py-2.5 items-center"
            >
                {percent < 50
                    ? <BreakdownWarningIcon />
                    : <BreakdownCheckIcon />
                }

                <p className="flex-1 nova-text-label-tiny-sb">{title}</p>

                <div className="flex gap-x-1.5 items-center">
                    <p className={cn("nova-text-label-small", percent < 50 && "text-[#C77785]")}>{percent}%</p>
                    {percent === 100
                        ? <CheckIcon />
                        : <CircularProgressbar
                            value={percent}
                            strokeWidth={14}
                            className="size-5"
                            styles={{
                                path: {
                                    stroke: percent < 50 ? "#C77785" : "#C1B1A6"
                                },
                                trail: {
                                    stroke: percent < 50 ? "#EBCED3" : "#E8DFD9",
                                },
                            }}
                        />
                    }

                </div>

                <ChevronDownIcon className={cn("fill-[#242529] transition-transform", isOpen && "rotate-180")} />
            </div>

            <div className={cn("pl-9 grid overflow-hidden transition-all", isOpen ? "grid-rows-[1fr] pb-5" : "grid-rows-[0fr]")}>
                <div className="min-h-0 flex flex-col gap-y-3 items-start">
                    <p className="nova-text-p-base text-[#6A6B6E]">{description}</p>
                    {lessonBlockId &&
                        <Button
                            variant="outline"
                            className="flex gap-x-1 items-center"
                            onClick={e => {
                                e.stopPropagation()
                                navigateLessonPart(lessonBlockId)
                            }}
                        >
                            <BookOpenIcon />
                            Go to this part
                        </Button>
                    }
                </div>
            </div>
        </div>
    )
}

type LessonResultsProps = {
    lesson: RoadmapLessonOut
    navigateNextLesson(): void
    redoLesson(): void
    resettingLesson?: boolean
    navigateLessonPart(blockId: string): void
    prefetchedResults: LessonResultRead | null
    prefetchedResultsLoading: boolean
}

type BreakdownEntry = {
    lesson_block_id?: string | null;
    title: string;
    percent: number;
    description: string;
};

type ResultsData = {
    stars: number;
    percent: number;
    need_review: string[];
    breakdown: BreakdownEntry[];
};

type State = {
    results: ResultsData | null;
    status?: "loading" | "error" | "success";
};

type Action =
    | { type: "fetch" }
    | { type: "error" }
    | { type: "done"; results: ResultsData };

function reducer(_: State, action: Action): State {
    if (action.type === "fetch") return { results: null, status: "loading" };
    if (action.type === "error") return { results: null, status: "error" };
    return { results: action.results, status: "success" };
}

export function LessonResults({
    lesson,
    navigateLessonPart,
    navigateNextLesson,
    redoLesson,
    resettingLesson,
    prefetchedResults,
    prefetchedResultsLoading,
}: LessonResultsProps) {
    const { lessonMap, stepStatus } = useLessons()

    const lessonId = lesson.lesson_id ?? "";
    const displayLesson =
        lessonId && lessonMap[lessonId] ? lessonMap[lessonId].lesson : lesson;
    const st = lessonId ? stepStatus[lessonId] : undefined;
    const stepFilled = lessonStepDisplayFlags(displayLesson, st);

    const [{ results, status }, dispatch] = useReducer(reducer, {
        results: null,
    })

    useEffect(() => {
        let cancelled = false

        if (prefetchedResultsLoading) {
            dispatch({ type: "fetch" })
            return () => {
                cancelled = true
            }
        }

        if (prefetchedResults) {
            dispatch({ type: "done", results: prefetchedResults })
            return () => {
                cancelled = true
            }
        }

        dispatch({ type: "fetch" })

        getLessonResultsApiV1LearningLessonsLessonIdResultsGet(lesson.lesson_id ?? "").then(resp => {
            if (cancelled || resp.status !== 200) return
            dispatch({ type: "done", results: resp.data })
        }).catch(() => {
            if (cancelled) return
            dispatch({ type: "error" })
        })
        return () => {
            cancelled = true
        }
    }, [lesson, prefetchedResultsLoading, prefetchedResults])

    if (status === "loading") {
        return (
            <div className="flex items-center justify-center py-16">
                <LoaderIcon className="animate-spin" />
            </div>
        );
    }

    if (status === "error" || results === null) {
        return (
            <div className="py-16 text-center nova-text-p-base text-[#71717A]">
                Failed to load results.
            </div>
        )
    }

    return (
        <div className="flex-1 h-full overflow-y-auto px-8">
            <div className="flex flex-col gap-y-3 w-full max-w-177 mx-auto py-8">
                <div className="flex flex-col gap-y-6 justify-center items-center w-full py-6 border border-[#F4F4F5] rounded-[16px]">
                    <div className="w-full max-w-58 flex flex-col gap-y-3 items-center">
                        <CircularProgressbar
                            value={results.percent}
                            text={`${results.percent}%`}
                            className="size-27"
                            strokeWidth={8}
                            styles={{
                                path: {
                                    stroke: "#D1C1B7",
                                    strokeLinecap: "round",
                                },
                                trail: {
                                    stroke: "#F1ECE9",
                                },
                                text: {
                                    textAnchor: "middle",
                                    dominantBaseline: "middle",
                                }
                            }}
                            classes={{
                                background: "",
                                path: "",
                                root: "",
                                text: "nova-text-label-base text-[#242529]",
                                trail: ""
                            }}
                        />

                        <div className="flex gap-x-0.5 h-5 *:nth-[2]:self-end">
                            {Array.from({ length: 3 }, (_, index) =>
                                <Tippy
                                    key={index}
                                    content={STAR_TOOLTIP[index]}
                                >
                                    {stepFilled[index]
                                        ? <StarFilledColoredIcon className="size-3.5" />
                                        : <StarFilledGrayIcon className="size-3.5" />
                                    }
                                </Tippy>
                            )}
                        </div>
                        <p className="nova-text-h-small text-[#242529]">{lessonProgressToText(results.percent)}</p>
                        {lesson.study_star && lesson.feynman_star && lesson.test_star &&
                            <p className="text-center nova-text-p-base text-[#6A6B6E]">You successfuly completed this lesson</p>
                        }
                    </div>

                    <div className="flex gap-x-2 nova-text-label-small text-[#242529]">
                        <Button
                            onClick={navigateNextLesson}
                        >
                            Next lesson
                        </Button>
                        <Button
                            variant="plain"
                            onClick={redoLesson}
                            isLoading={resettingLesson}
                        >
                            Redo lesson
                        </Button>
                    </div>
                </div>

                {results.need_review.length !== 0 &&
                    <div className="flex gap-x-3 px-5 py-6 border border-[#F4F4F5] rounded-[16px]">
                        <ExclamationTriangleIcon className="shrink-0" />

                        <div className="flex flex-col gap-y-1">
                            <p className="nova-text-label-tiny-sb text-[#242529]">{results.need_review.length} area{results.need_review.length > 1 ? "s" : ""} need{results.need_review.length > 1 ? "" : "s"} review</p>
                            <p className="nova-text-label-medium-regular text-[#6A6B6E]">{results.need_review.join(", ")}</p>
                        </div>
                    </div>
                }

                <div className="border border-[#F4F4F5] rounded-[16px] text-[#1D1B20] divide-y divide-[#F4F4F5]">
                    <p className="p-3 nova-text-label-tiny-sb">Parts breakdown</p>

                    {results.breakdown.map((entry, i) =>
                        <BreakdownDropdown
                            key={i}
                            title={entry.title}
                            percent={entry.percent}
                            description={entry.description}
                            lessonBlockId={entry.lesson_block_id}
                            navigateLessonPart={navigateLessonPart}
                        />
                    )}
                </div>
            </div>
        </div>
    )
}
