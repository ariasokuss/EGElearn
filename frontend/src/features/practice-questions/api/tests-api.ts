import { apiStreamOrigin } from "@/shared/api/api-fetch-origin"
import { getAccessToken } from "@/shared/lib/auth-storage"
import {
  generateTemplateApiV1TestsTemplatesGeneratePost,
  getTemplateApiV1TestsTemplatesTemplateIdGet,
  listSessionsApiV1TestsSessionsGet,
  getSessionApiV1TestsSessionsSessionIdGet,
  startSessionApiV1TestsSessionsStartPost,
  submitSessionApiV1TestsSessionsSessionIdSubmitPost,
  getSessionStatusApiV1TestsSessionsSessionIdStatusGet,
} from "@/shared/api/generated/api"
import type {
  GenerateTemplateRequest,
  TestTemplateOut,
  TemplateDetailOut,
  TestSessionOut,
  SessionDetailOut,
  SubmitSessionRequest,
  TestStatusOut,
} from "@/shared/api/generated/model"
import type { TestSessionTypes } from "../model/types"

/** Question type definition from backend */
export type QuestionType = {
  label: string
  key: string
  points: number
}

/**
 * Fetch available question types for a folder.
 * Returns empty array if folder doesn't support typed generation.
 */
export async function getQuestionTypes(folderId: string): Promise<QuestionType[]> {
  const token = getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`
  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/tests/question-types?folder_id=${folderId}`,
    { headers },
  )
  if (!res.ok) return []
  return res.json()
}

/**
 * Generate a test template (creates questions).
 * Returns the template metadata.
 */
export async function generateTemplate(req: GenerateTemplateRequest): Promise<TestTemplateOut> {
  const res = await generateTemplateApiV1TestsTemplatesGeneratePost(req)
  if (res.status !== 201) throw new Error("Failed to generate template")
  return res.data
}

/** Per-node progress from the SSE stream. */
export type NodeProgress = { generated: number; total: number }

/** SSE events emitted by the streaming generation endpoint. */
export type GenerateStreamEvent =
  | { event: "progress"; nodes: Record<string, NodeProgress> }
  | { event: "complete"; template_id: string; total_questions: number; total_marks: number; name: string }
  | { event: "error"; message: string }

/** Response from POST /templates/generate/stream (now returns JSON, not SSE) */
export type GenerateStartedOut = {
  template_id: string
  name: string
  status: string
}

/** Template with generation_progress for list view */
export type TemplateWithProgress = {
  id: string
  name: string
  status: string
  type: string
  total_questions: number
  total_marks: number | null
  created_at: string
  generation_progress: {
    nodes: Record<string, NodeProgress>
    error: string | null
  } | null
}

/**
 * Start generation — POST to /templates/generate/stream.
 * Now returns JSON (not SSE). Use streamTemplateProgress to follow progress.
 */
export async function startGeneration(req: GenerateTemplateRequest): Promise<GenerateStartedOut> {
  const token = getAccessToken()
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(`${apiStreamOrigin()}/api/v1/tests/templates/generate/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(req),
  })

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED")
    const text = await res.text().catch(() => "Unknown error")
    throw new Error(`Generate failed (${res.status}): ${text}`)
  }

  return res.json()
}

/**
 * Stream template generation progress via SSE.
 * Connects to GET /templates/{id}/progress.
 */
export async function* streamTemplateProgress(
  templateId: string,
  options?: { signal?: AbortSignal },
): AsyncGenerator<GenerateStreamEvent> {
  const token = getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/tests/templates/${templateId}/progress`,
    { headers, signal: options?.signal },
  )

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED")
    throw new Error(`Progress stream failed (${res.status})`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split("\n\n")
      buffer = blocks.pop() ?? ""

      for (const block of blocks) {
        const trimmed = block.trim()
        if (!trimmed) continue
        let dataLine = ""
        for (const line of trimmed.split("\n")) {
          if (line.startsWith("data: ")) dataLine = line.slice(6)
        }
        if (!dataLine) continue
        try { yield JSON.parse(dataLine) as GenerateStreamEvent } catch { /* skip */ }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * Cancel an in-progress generation.
 */
export async function cancelGeneration(templateId: string): Promise<void> {
  const token = getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`
  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/tests/templates/${templateId}/cancel`,
    { method: "POST", headers },
  )
  if (!res.ok) throw new Error(`Cancel failed (${res.status})`)
}

/**
 * Retry a failed generation.
 */
export async function retryGeneration(templateId: string): Promise<GenerateStartedOut> {
  const token = getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`
  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/tests/templates/${templateId}/retry`,
    { method: "POST", headers },
  )
  if (!res.ok) throw new Error(`Retry failed (${res.status})`)
  return res.json()
}

/**
 * List templates for a folder, optionally filtered by type.
 * Returns templates with generation_progress for showing processing/failed state.
 */
export async function listTemplates(folderId: string, type?: string): Promise<TemplateWithProgress[]> {
  const token = getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`
  const params = new URLSearchParams({ folder_id: folderId })
  if (type) params.set("type", type)
  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/tests/templates?${params}`,
    { headers },
  )
  if (!res.ok) throw new Error(`List templates failed (${res.status})`)
  return res.json()
}

/**
 * @deprecated Use startGeneration + streamTemplateProgress instead.
 * Kept for backward compatibility.
 */
export async function* streamGenerateTemplate(
  req: GenerateTemplateRequest,
  options?: { signal?: AbortSignal },
): AsyncGenerator<GenerateStreamEvent> {
  const result = await startGeneration(req)
  yield* streamTemplateProgress(result.template_id, options)
}

/**
 * Get template detail — includes questions generated so far.
 * Use for polling generation progress.
 */
export async function getTemplate(templateId: string): Promise<TemplateDetailOut> {
  const res = await getTemplateApiV1TestsTemplatesTemplateIdGet(templateId)
  if (res.status !== 200) throw new Error("Failed to get template")
  return res.data
}

/**
 * Start a test session from a template.
 * Returns the session with questions ready to answer.
 */
export async function startSession(templateId: string, mode: string = "practice"): Promise<SessionDetailOut> {
  const res = await startSessionApiV1TestsSessionsStartPost(
    { template_id: templateId, mode },
  )
  // Success is 2xx; OpenAPI may only list 201 while server returns 200.
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`Failed to start session (${res.status})`)
  }
  return res.data as SessionDetailOut
}

/**
 * List all test sessions, optionally filtered by folder_id.
 */
export async function listSessions(folderId?: string, type?: TestSessionTypes): Promise<TestSessionOut[]> {
  const res = await listSessionsApiV1TestsSessionsGet(
    {folder_id: folderId, type},
  )
  if (res.status !== 200) throw new Error("Failed to list sessions")
  return res.data
}

/**
 * Get full session details (session + template + questions + answers).
 */
export async function getSession(sessionId: string): Promise<SessionDetailOut> {
  const res = await getSessionApiV1TestsSessionsSessionIdGet(sessionId)
  if (res.status !== 200) throw new Error("Failed to get session")
  return res.data
}

/**
 * Submit a session for grading.
 * Optionally includes remaining answers that haven't been auto-saved yet.
 * Returns the full session detail (re-fetched after submit).
 */
export async function submitSession(sessionId: string, req: SubmitSessionRequest): Promise<SessionDetailOut> {
  const res = await submitSessionApiV1TestsSessionsSessionIdSubmitPost(sessionId, req)
  if (res.status !== 200) throw new Error("Failed to submit session")
  return getSession(res.data.id)
}

/**
 * Get the grading status of a session.
 */
export async function getSessionStatus(sessionId: string): Promise<TestStatusOut> {
  const res = await getSessionStatusApiV1TestsSessionsSessionIdStatusGet(sessionId)
  if (res.status !== 200) throw new Error("Failed to get session status")
  return res.data
}
