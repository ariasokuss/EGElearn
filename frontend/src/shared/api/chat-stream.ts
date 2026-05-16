import type { ChatMessageRequest, SrcLearningFeynmanRouterAnswerRequest, StartStandardSessionRequest } from "./generated/model"
import { apiStreamOrigin } from "./api-fetch-origin"
import { getAccessToken } from "@/shared/lib/auth-storage"

export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "metadata"; conversation_id: string; message_id?: string; user_message_id?: string; title?: string; complete?: boolean }
  | { type: "stream_end" }
  | { type: "done" }
  | { type: "error"; message: string }

function parseSSEData(payload: string, eventName: string | null): StreamEvent | null {
  if (payload === "[DONE]") return { type: "done" }

  // stream_end is emitted right after the last token, before any DB work.
  if (eventName === "stream_end") return { type: "stream_end" }

  // message_complete carries real DB IDs — parse as metadata so the
  // frontend can reconcile optimistic IDs, but also mark complete.
  if (eventName === "message_complete" || eventName === "followup_suggestions") {
    try {
      const json = JSON.parse(payload)
      if (json.conversation_id) {
        return {
          type: "metadata",
          conversation_id: json.conversation_id,
          message_id: json.message_id,
          user_message_id: json.user_message_id,
          title: json.title ?? json.conversation_title ?? undefined,
          complete: eventName === "message_complete",
        }
      }
    } catch { /* fall through */ }
    return eventName === "message_complete" ? { type: "done" } : null
  }

  try {
    const json = JSON.parse(payload)

    if (json.conversation_id) {
      return {
        type: "metadata",
        conversation_id: json.conversation_id,
        message_id: json.message_id,
        user_message_id: json.user_message_id,
        title: json.title ?? json.conversation_title ?? undefined,
      }
    }

    if (json.covered)
      return { type: "done" }
    if (json.error) {
      return { type: "error", message: json.error }
    }

    if (typeof json.text === "string") {
      return { type: "token", text: json.text }
    }

    if (typeof json.content === "string") {
      return { type: "token", text: json.content }
    }

    if (typeof json.token === "string") {
      return { type: "token", text: json.token }
    }

    return null
  } catch {
    return { type: "token", text: payload }
  }
}

async function* readSSEBody(res: Response): AsyncGenerator<StreamEvent> {
  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""
  let currentEventName: string | null = null

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() ?? ""

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) {
          // blank line resets event name per SSE spec
          currentEventName = null
          continue
        }
        if (trimmed.startsWith("event: ") || trimmed.startsWith("event:")) {
          currentEventName = trimmed.slice(trimmed.indexOf(":") + 1).trim()
          continue
        }
        if (trimmed.startsWith("data: ") || trimmed.startsWith("data:")) {
          const payload = trimmed.slice(trimmed.indexOf(":") + 1).trim()
          const event = parseSSEData(payload, currentEventName)
          if (event) yield event
        }
        // skip comment lines (starting with ":") and unknown fields
      }
    }

    if (buffer.trim()) {
      const payload = buffer.trim()
      if (payload.startsWith("data: ") || payload.startsWith("data:")) {
        const event = parseSSEData(payload.slice(payload.indexOf(":") + 1).trim(), null)
        if (event) yield event
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function* streamChatMessage(
  request: ChatMessageRequest & Record<string, unknown>,
  options?: { signal?: AbortSignal }
): AsyncGenerator<StreamEvent> {
  const token = getAccessToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${apiStreamOrigin()}/api/v1/chat/message`, {
    method: "POST",
    headers,
    body: JSON.stringify(request),
    signal: options?.signal,
  })

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED")
    const text = await res.text().catch(() => "Unknown error")
    throw new Error(`Chat request failed (${res.status}): ${text}`)
  }

  yield* readSSEBody(res)
}

export async function* streamRegenerateMessage(
  conversationId: string,
  messageId: string,
  request: {
    message?: string
    model?: string | null
    reasoning?: string | null
    images?: string[]
    citations?: string[]
  },
  options?: { signal?: AbortSignal }
): AsyncGenerator<StreamEvent> {
  const token = getAccessToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/chat/conversations/${conversationId}/messages/${messageId}/regenerate`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(request),
      signal: options?.signal,
    }
  )

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED")
    const text = await res.text().catch(() => "Unknown error")
    throw new Error(`Regenerate request failed (${res.status}): ${text}`)
  }

  yield* readSSEBody(res)
}

export type FeynmanStreamEvent =
  | { type: "token"; text: string }
  | { type: "session_started", sessionId: string }
  | { type: "done" }
  | { type: "error"; message: string }

function parseSSEFeynman(statement: string): FeynmanStreamEvent | null {
  const lines = statement.split("\n")
  const eventType = lines[0].slice(7).trim()
  const payload = lines[1].slice(6).trim()

  try {
    const json = JSON.parse(payload)

    if (eventType === "token")
      return { type: "token", text: json.content }

    if (eventType === "session_started")
      return { type: "session_started", sessionId: json.session_id  }

    if (eventType === "summary")
      return { type: "done" }

    if (eventType === "error")
      return { type: "error", message: json.detail }

    return null
  } catch {
    return { type: "token", text: payload }
  }
}

type FeynmanRequestInfo = {
  type: "answer",
  sessionId: string
  request: SrcLearningFeynmanRouterAnswerRequest
} | {
  type: "start"
  request: StartStandardSessionRequest
}

export async function* streamFeynman(
  info: FeynmanRequestInfo,
  options?: { signal?: AbortSignal }
): AsyncGenerator<FeynmanStreamEvent> {
  const token = getAccessToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }


  const base = apiStreamOrigin()
  const res = await fetch(
    info.type === "answer"
      ? `${base}/api/v1/feynman/session/${info.sessionId}/answer`
      : `${base}/api/v1/feynman/session`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(info.request),
      signal: options?.signal,
    }
  )

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("AUTH_EXPIRED")
    }
    const text = await res.text().catch(() => "Unknown error")
    throw new Error(`Feynman answer request failed (${res.status}): ${text}`)
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
      const statements = buffer.split("\n\n")
      buffer = statements.pop() ?? ""

      for (const statement of statements) {
        const trimmed = statement.trim()
        if (!trimmed) continue
        const event = parseSSEFeynman(trimmed)
        if (event) yield event
      }
    }
    if (buffer.trim()) {
        const event = parseSSEFeynman(buffer.trim())
      if (event) yield event
    }
    } finally {
      reader.releaseLock()
    }
}

// export async function* streamTest(
//   options?: { signal?: AbortSignal }
// ): AsyncGenerator<string> {
//   const res = await fetch(`${apiFetchOrigin()}/api/v1/chat/stream-test`, {
//     signal: options?.signal,
//   })

//   if (!res.ok) throw new Error(`Stream test failed (${res.status})`)

//   const reader = res.body?.getReader()
//   if (!reader) throw new Error("No response body")

//   const decoder = new TextDecoder()
//   let buffer = ""

//   try {
//     while (true) {
//       const { done, value } = await reader.read()
//       if (done) break

//       buffer += decoder.decode(value, { stream: true })
//       const lines = buffer.split("\n")
//       buffer = lines.pop() ?? ""

//       for (const line of lines) {
//         const trimmed = line.trim()
//         if (!trimmed || !trimmed.startsWith("data: ")) continue
//         const payload = trimmed.slice(6)
//         if (payload === "[DONE]") return
//         yield payload
//       }
//     }
//   } finally {
//     reader.releaseLock()
//   }
// }
