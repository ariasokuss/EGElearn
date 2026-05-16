"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import type {
  GenerateTemplateRequest,
  TestSessionOut,
  SessionDetailOut,
  SubmitSessionRequest,
} from "@/shared/api/generated/model"
import {
  startSession,
  listSessions,
  getSession,
  submitSession,
  startGeneration,
  listTemplates,
  cancelGeneration as cancelGenerationApi,
  retryGeneration as retryGenerationApi,
} from "../api"
import type { NodeProgress, TemplateWithProgress } from "../api"
import {
  readCachedTestLists,
  writeCachedTestSessions,
  writeCachedTestTemplates,
} from "./test-list-cache"

import type { TestSessionTypes } from "./types"
export type { TestSessionTypes } from "./types"

export type GenerationProgress = {
  /** Per-node generation status: node_name -> {generated, total} */
  nodes: Record<string, NodeProgress>
  /** Template ID (available after complete event) */
  templateId: string | null
  done: boolean
}

type UseTestsReturn = {
  sessions: TestSessionOut[]
  sessionsLoading: boolean
  sessionsError: string | null
  activeSession: SessionDetailOut | null
  activeSessionLoading: boolean
  templates: TemplateWithProgress[]
  loadSessions: (type?: TestSessionTypes) => Promise<void>
  loadTemplates: () => Promise<void>
  openSession: (sessionId: string) => Promise<void>
  /** Re-fetch GET session detail for the active session (e.g. after practice hint consumed). */
  refreshActiveSession: () => Promise<void>
  closeSession: () => void
  /**
   * Start generation and return the template ID.
   * The template appears as a processing card in history.
   */
  generateTest: (req: GenerateTemplateRequest) => Promise<string>
  /** Start a session from a ready template */
  startTestSession: (templateId: string, mode?: string) => Promise<void>
  submitAnswers: (sessionId: string, req: SubmitSessionRequest) => Promise<void>
  cancelGeneration: (templateId: string) => Promise<void>
  retryGeneration: (templateId: string) => Promise<void>
}

export function useTests(folderId: string | null, type?: TestSessionTypes): UseTestsReturn {
  const shouldUseListCache = folderId != null && type === "past_paper"
  const cachedLists = shouldUseListCache ? readCachedTestLists(folderId, type) : null

  const [sessions, setSessions] = useState<TestSessionOut[]>(() => cachedLists?.sessions ?? [])
  const [sessionsLoading, setSessionsLoading] = useState(() => !cachedLists?.sessions)
  const [sessionsError, setSessionsError] = useState<string | null>(null)
  const [activeSession, setActiveSession] = useState<SessionDetailOut | null>(null)
  const [activeSessionLoading, setActiveSessionLoading] = useState(false)
  const [templates, setTemplates] = useState<TemplateWithProgress[]>(() => cachedLists?.templates ?? [])

  // Abort polling on unmount
  const pollAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const pollAbort = pollAbortRef.current
    return () => { pollAbort?.abort() }
  }, [])

  const loadSessions = useCallback(
    async (typeOverride?: TestSessionTypes) => {
      if (!folderId) return
      setSessionsLoading(true)
      setSessionsError(null)
      try {
        const filterType = typeOverride ?? type
        const data = await listSessions(folderId, filterType)
        if (shouldUseListCache && filterType === "past_paper") {
          writeCachedTestSessions(folderId, filterType, data)
        }
        setSessions(data)
      } catch {
        setSessionsError("Failed to load test sessions")
      } finally {
        setSessionsLoading(false)
      }
    },
    [folderId, shouldUseListCache, type],
  )

  const loadTemplates = useCallback(async () => {
    if (!folderId) return
    try {
      const data = await listTemplates(folderId, type)
      if (shouldUseListCache && type === "past_paper") {
        writeCachedTestTemplates(folderId, type, data)
      }
      setTemplates(data)
    } catch {
      // silently fail — templates list is supplementary
    }
  }, [folderId, shouldUseListCache, type])

  useEffect(() => {
    if (!folderId) return
    if (!cachedLists?.sessions) {
      void loadSessions(type)
    }
    if (!cachedLists?.templates) {
      void loadTemplates()
    }
  }, [cachedLists?.sessions, cachedLists?.templates, folderId, loadSessions, loadTemplates, type])

  const openSession = useCallback(async (sessionId: string) => {
    setActiveSessionLoading(true)
    try {
      const detail = await getSession(sessionId)
      setActiveSession(detail)
    } catch {
      setActiveSession(null)
    } finally {
      setActiveSessionLoading(false)
    }
  }, [])

  const refreshActiveSession = useCallback(async () => {
    const sessionId = activeSession?.session?.id
    if (!sessionId) return
    setActiveSessionLoading(true)
    try {
      const detail = await getSession(sessionId)
      setActiveSession(detail)
    } catch {
      // keep previous
    } finally {
      setActiveSessionLoading(false)
    }
  }, [activeSession?.session?.id])

  const closeSession = useCallback(() => {
    setActiveSession(null)
  }, [])

  /**
   * Start generation and return the template ID.
   * The template appears as a processing card in history.
   */
  const generateTest = useCallback(
    async (req: GenerateTemplateRequest): Promise<string> => {
      const result = await startGeneration(req)
      await loadTemplates()
      return result.template_id
    },
    [loadTemplates],
  )

  const cancelGeneration = useCallback(
    async (templateId: string) => {
      await cancelGenerationApi(templateId)
      await loadTemplates()
    },
    [loadTemplates],
  )

  const retryGeneration = useCallback(
    async (templateId: string) => {
      await retryGenerationApi(templateId)
      await loadTemplates()
    },
    [loadTemplates],
  )

  /**
   * Start a session from a ready template.
   */
  const startTestSession = useCallback(
    async (templateId: string, mode: string = "practice") => {
      setActiveSessionLoading(true)
      try {
        const sessionDetail = await startSession(templateId, mode)
        setActiveSession(sessionDetail)
        await loadSessions(type)
      } catch (e) {
        setActiveSession(null)
        throw e
      } finally {
        setActiveSessionLoading(false)
      }
    },
    [loadSessions, type],
  )

  const submitAnswers = useCallback(
    async (sessionId: string, req: SubmitSessionRequest) => {
      const result = await submitSession(sessionId, req)
      setActiveSession(result)
      loadSessions(type)
    },
    [loadSessions, type],
  )

  return {
    sessions,
    sessionsLoading,
    sessionsError,
    activeSession,
    activeSessionLoading,
    templates,
    loadSessions,
    loadTemplates,
    openSession,
    refreshActiveSession,
    closeSession,
    generateTest,
    startTestSession,
    submitAnswers,
    cancelGeneration,
    retryGeneration,
  }
}
