"use client"

import type { CompleteStepResponse } from "@/shared/api/generated/model"
import { LessonSchema, LessonProgressRead, RoadmapLessonOut, RoadmapOut } from "@/shared/api/generated/model"
import { createContext, useCallback, useContext, useEffect, useRef, useReducer } from "react"
import { getRoadmapApi } from "../api/roadmap-api"
import { getLessonProgressApi, getLessonsApi } from "../api/lessons-api"
import { getAccessToken } from "@/shared/lib/auth-storage"

type LessonInfo = {
    detail: LessonSchema
    lesson: RoadmapLessonOut
    nextId?: string
}
type LessonMap = Record<string, LessonInfo>

export type LessonProgressUpdate = {
    study_star?: boolean
    feynman_star?: boolean
    test_star?: boolean
    mastery?: number | null
    confidence?: number | null
}

function earnedStepStar(value: boolean | null | undefined): boolean {
    return value === true
}

export function progressReadToLessonUpdate(progress: LessonProgressRead): LessonProgressUpdate {
    return {
        study_star: earnedStepStar(progress.study_star),
        feynman_star: earnedStepStar(progress.feynman_star),
        test_star: earnedStepStar(progress.test_star),
        mastery: progress.mastery ?? null,
    }
}

export function progressUpdateFromCompleteStep(r: CompleteStepResponse): LessonProgressUpdate {
    return {
        study_star: earnedStepStar(r.study_star),
        feynman_star: earnedStepStar(r.feynman_star),
        test_star: earnedStepStar(r.test_star),
        mastery: r.mastery ?? null,
        confidence: r.confidence ?? null,
    }
}

export type LessonStepStatus = {
    study: boolean
    feynman: boolean
    test: boolean
}

export type LessonStep = 1 | 2 | 3

type StepStatusMap = Record<string, LessonStepStatus>

export const EMPTY_STEP_STATUS: LessonStepStatus = { study: false, feynman: false, test: false }

export function lessonStepDisplayFlags(
    lesson: Pick<RoadmapLessonOut, "study_star" | "feynman_star" | "test_star">,
    stepSt: LessonStepStatus | undefined,
): [boolean, boolean, boolean] {
    const study = !!lesson.study_star
    const feynman = !!lesson.feynman_star
    const test = !!lesson.test_star
    if (stepSt === undefined) {
        return [study, feynman, test]
    }
    return [stepSt.study || study, stepSt.feynman || feynman, stepSt.test || test]
}

function progressToStepStatus(progress: LessonProgressRead | null | undefined): LessonStepStatus {
    if (!progress) return EMPTY_STEP_STATUS
    return {
        study: earnedStepStar(progress.study_star),
        feynman: earnedStepStar(progress.feynman_star),
        test: earnedStepStar(progress.test_star),
    }
}

function applyStep(status: LessonStepStatus, step: LessonStep, value: boolean): LessonStepStatus {
    if (step === 1) return { ...status, study: value }
    if (step === 2) return { ...status, feynman: value }
    return { ...status, test: value }
}

type LessonsContextValue = {
    roadmap: RoadmapOut | null
    lessonMap: LessonMap
    loading: boolean
    updateLessonProgress: (lessonId: string, update: LessonProgressUpdate) => void
    stepStatus: Record<string, LessonStepStatus>
    setLessonStepStatus: (lessonId: string, progress: LessonProgressRead | null | undefined) => void
    markStepComplete: (lessonId: string, step: LessonStep) => void
    resetStepStatus: (lessonId: string) => void
    refreshLessonProgress: (lessonId: string) => Promise<void>
}

const LessonsContext = createContext<LessonsContextValue | null>(null)

type LessonsProviderProps = {
    children: React.ReactNode
    folderId: string
}

type State = {
    roadmap: RoadmapOut | null
    lessonMap: LessonMap
    loading: boolean
    stepStatus: StepStatusMap
}
type Action =
    | { type: "fetch" }
    | { type: "done"; roadmap: RoadmapOut | null; lessonMap: LessonMap }
    | { type: "updateProgress"; lessonId: string; update: LessonProgressUpdate }
    | { type: "setStepStatus"; lessonId: string; status: LessonStepStatus }
    | { type: "markStepComplete"; lessonId: string; step: LessonStep }
    | { type: "resetStepStatus"; lessonId: string }

function applyLessonUpdate(lesson: RoadmapLessonOut, patch: Partial<RoadmapLessonOut>): RoadmapLessonOut {
    return { ...lesson, ...patch }
}

function updateRoadmapLesson(state: State, lessonId: string, patch: Partial<RoadmapLessonOut>): State {
    const entry = state.lessonMap[lessonId]
    if (!entry) return state
    const updatedLesson = applyLessonUpdate(entry.lesson, patch)
    const updatedMap = { ...state.lessonMap, [lessonId]: { ...entry, lesson: updatedLesson } }
    const updatedRoadmap = state.roadmap ? {
        ...state.roadmap,
        sections: state.roadmap.sections.map(section => ({
            ...section,
            lessons: section.lessons.map(l =>
                l.lesson_id === lessonId ? applyLessonUpdate(l, patch) : l
            ),
            subsections: section.subsections.map(sub => ({
                ...sub,
                lessons: sub.lessons.map(l =>
                    l.lesson_id === lessonId ? applyLessonUpdate(l, patch) : l
                ),
            })),
        })),
    } : null
    return { ...state, lessonMap: updatedMap, roadmap: updatedRoadmap }
}

function reducer(state: State, action: Action): State {
    if (action.type === "fetch") return { roadmap: null, lessonMap: {}, loading: true, stepStatus: {} }
    if (action.type === "done") {
        const seedStatus: StepStatusMap = {}
        for (const [lessonId, info] of Object.entries(action.lessonMap)) {
            seedStatus[lessonId] = {
                study: !!info.lesson.study_star,
                feynman: !!info.lesson.feynman_star,
                test: !!info.lesson.test_star,
            }
        }
        // In-session completions (from markStepComplete) take precedence over roadmap seed
        return { roadmap: action.roadmap, lessonMap: action.lessonMap, loading: false, stepStatus: { ...seedStatus, ...state.stepStatus } }
    }
    if (action.type === "updateProgress") {
        const { study_star, feynman_star, test_star, mastery, confidence } = action.update
        const patch: Partial<RoadmapLessonOut> = {}
        if (study_star !== undefined) patch.study_star = study_star
        if (feynman_star !== undefined) patch.feynman_star = feynman_star
        if (test_star !== undefined) patch.test_star = test_star
        if (mastery !== undefined) patch.mastery = mastery
        if (confidence !== undefined) patch.confidence = confidence
        return updateRoadmapLesson(state, action.lessonId, patch)
    }
    if (action.type === "setStepStatus") {
        const prev = state.stepStatus[action.lessonId] ?? EMPTY_STEP_STATUS
        if (
            prev.study === action.status.study &&
            prev.feynman === action.status.feynman &&
            prev.test === action.status.test
        ) {
            return state
        }
        return { ...state, stepStatus: { ...state.stepStatus, [action.lessonId]: action.status } }
    }
    if (action.type === "markStepComplete") {
        const prev = state.stepStatus[action.lessonId] ?? EMPTY_STEP_STATUS
        const next = applyStep(prev, action.step, true)
        if (prev.study === next.study && prev.feynman === next.feynman && prev.test === next.test) {
            return state
        }
        return { ...state, stepStatus: { ...state.stepStatus, [action.lessonId]: next } }
    }
    if (action.type === "resetStepStatus") {
        if (!state.stepStatus[action.lessonId]) return state
        return { ...state, stepStatus: { ...state.stepStatus, [action.lessonId]: EMPTY_STEP_STATUS } }
    }
    return state
}

export function LessonsProvider({ children, folderId }: LessonsProviderProps) {
    const [{ roadmap, lessonMap, loading, stepStatus }, dispatch] = useReducer(reducer, {
        roadmap: null,
        lessonMap: {},
        loading: true,
        stepStatus: {},
    })

    useEffect(() => {
        let cancelled = false
        dispatch({ type: "fetch" })

        Promise.all([getRoadmapApi(folderId), getLessonsApi()]).then(([roadmapData, lessons]) => {
            if (cancelled) return
            const map: LessonMap = {}

            const schemaMap: Record<string, LessonSchema> = {}
            for (const l of lessons) {
                schemaMap[l.id] = l
            }

            let prevId: string | undefined = undefined
            const setNextIds = (lesson: RoadmapLessonOut) => {
                const nextId = lesson.lesson_id ?? undefined
                if (prevId && prevId in schemaMap)
                    map[prevId] = {
                        ...map[prevId],
                        nextId: nextId
                    }
                if (nextId)
                    map[nextId] = {
                        detail: schemaMap[nextId],
                        lesson: lesson
                    }
                prevId = nextId
            }

            roadmapData?.sections.forEach(section => {
                section.lessons.forEach(setNextIds)
                section.subsections.forEach(sub => sub.lessons.forEach(setNextIds))
            })

            dispatch({ type: "done", roadmap: roadmapData, lessonMap: map })
        })

        return () => {
            cancelled = true
        }
    }, [folderId])

    const nodeToLessonRef = useRef<Record<string, string>>({})
    useEffect(() => {
        if (!roadmap) return
        const map: Record<string, string> = {}
        for (const section of roadmap.sections) {
            for (const l of section.lessons) {
                if (l.lesson_id) map[l.id] = l.lesson_id
            }
            for (const sub of section.subsections) {
                for (const l of sub.lessons) {
                    if (l.lesson_id) map[l.id] = l.lesson_id
                }
            }
        }
        nodeToLessonRef.current = map
    }, [roadmap])

    useEffect(() => {
        let cancelled = false
        let retryDelay = 1000

        const connect = async () => {
            try {
                const token = getAccessToken()
                const res = await fetch(`/api/v1/roadmap/folders/${folderId}/progress/stream`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                })
                if (!res.ok || !res.body) return
                const reader = res.body.getReader()
                const decoder = new TextDecoder()
                let buffer = ""
                let eventType = ""
                let data = ""
                while (!cancelled) {
                    const { done, value } = await reader.read()
                    if (done) break
                    buffer += decoder.decode(value, { stream: true })
                    const lines = buffer.split("\n")
                    buffer = lines.pop() ?? ""
                    for (const line of lines) {
                        if (line.startsWith("event: ")) {
                            eventType = line.slice(7)
                        } else if (line.startsWith("data: ")) {
                            data = line.slice(6)
                        } else if (line === "") {
                            if (eventType === "progress" && data) {
                                try {
                                    const d = JSON.parse(data) as Record<string, unknown>
                                    const lessonId = nodeToLessonRef.current[String(d.node_id)]
                                    if (lessonId) {
                                        const update: LessonProgressUpdate = {}
                                        if (d.mastery !== undefined) update.mastery = d.mastery as number | null
                                        if (d.confidence !== undefined) update.confidence = d.confidence as number | null
                                        const hasBool =
                                            typeof d.study_star === "boolean" ||
                                            typeof d.feynman_star === "boolean" ||
                                            typeof d.test_star === "boolean"
                                        if (hasBool) {
                                            if (typeof d.study_star === "boolean") update.study_star = d.study_star
                                            if (typeof d.feynman_star === "boolean") update.feynman_star = d.feynman_star
                                            if (typeof d.test_star === "boolean") update.test_star = d.test_star
                                        }
                                        dispatch({ type: "updateProgress", lessonId, update })
                                    }
                                } catch {}
                            }
                            retryDelay = 1000
                            eventType = ""
                            data = ""
                        }
                    }
                }
            } catch {}
            if (!cancelled) {
                setTimeout(connect, retryDelay)
                retryDelay = Math.min(retryDelay * 2, 30000)
            }
        }

        connect()
        return () => { cancelled = true }
    }, [folderId])

    const updateLessonProgress = useCallback((lessonId: string, update: LessonProgressUpdate) => {
        dispatch({ type: "updateProgress", lessonId, update })
    }, [])

    const setLessonStepStatus = useCallback(
        (lessonId: string, progress: LessonProgressRead | null | undefined) => {
            dispatch({ type: "setStepStatus", lessonId, status: progressToStepStatus(progress) })
        },
        [],
    )

    const markStepComplete = useCallback((lessonId: string, step: LessonStep) => {
        dispatch({ type: "markStepComplete", lessonId, step })
    }, [])

    const resetStepStatus = useCallback((lessonId: string) => {
        dispatch({ type: "resetStepStatus", lessonId })
    }, [])

    const refreshLessonProgress = useCallback(async (lessonId: string) => {
        const progress = await getLessonProgressApi(lessonId)
        if (!progress) return
        dispatch({ type: "setStepStatus", lessonId, status: progressToStepStatus(progress) })
        dispatch({
            type: "updateProgress",
            lessonId,
            update: progressReadToLessonUpdate(progress),
        })
    }, [])

    const value: LessonsContextValue = {
        roadmap,
        lessonMap,
        loading,
        stepStatus,
        updateLessonProgress,
        setLessonStepStatus,
        markStepComplete,
        resetStepStatus,
        refreshLessonProgress,
    }

    return (
        <LessonsContext.Provider value={value}>{children}</LessonsContext.Provider>
    )
}

export function useLessons(): LessonsContextValue {
    const ctx = useContext(LessonsContext)
    if (!ctx) throw new Error("useLessons must be used within LessonsProvider")
    return ctx
}
