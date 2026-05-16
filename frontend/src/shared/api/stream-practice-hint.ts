import type { PracticeHintRequest } from "@/shared/api/generated/model";
import { apiStreamOrigin } from "@/shared/api/api-fetch-origin";
import { getAccessToken } from "@/shared/lib/auth-storage";

export type PracticeHintStreamEvent =
  | {
      type: "hint_meta";
      session_id: string;
      question_id: string;
      /** Present when request included folder_id and/or conversation_id for chat sync. */
      conversation_id?: string;
    }
  | { type: "hint_chat_token"; content: string }
  | { type: "hint_panel_token"; content: string }
  | { type: "hint_complete"; assistant_chat: string; hint_panel: string }
  | { type: "error"; message: string; recoverable?: boolean };

function parseSseBlock(block: string): PracticeHintStreamEvent | null {
  const lines = block.split(/\r?\n/).filter(Boolean);
  let eventName = "";
  let dataLine = "";
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  if (!dataLine) return null;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataLine) as Record<string, unknown>;
  } catch {
    return null;
  }

  if (eventName === "hint_meta") {
    const conv = data.conversation_id;
    return {
      type: "hint_meta",
      session_id: String(data.session_id ?? ""),
      question_id: String(data.question_id ?? ""),
      ...(conv != null && String(conv).length > 0
        ? { conversation_id: String(conv) }
        : {}),
    };
  }
  if (eventName === "hint_chat_token") {
    return { type: "hint_chat_token", content: String(data.content ?? "") };
  }
  if (eventName === "hint_panel_token") {
    return { type: "hint_panel_token", content: String(data.content ?? "") };
  }
  if (eventName === "hint_complete") {
    return {
      type: "hint_complete",
      assistant_chat: String(data.assistant_chat ?? ""),
      hint_panel: String(data.hint_panel ?? ""),
    };
  }
  if (eventName === "error") {
    return {
      type: "error",
      message: String(data.message ?? "Hint request failed"),
      recoverable: data.recoverable === true,
    };
  }
  return null;
}

/**
 * POST /api/v1/tests/sessions/{session_id}/hint/{question_id} — SSE (text/event-stream).
 */
export async function* streamPracticeHint(
  sessionId: string,
  questionId: string,
  body: PracticeHintRequest,
  options?: { signal?: AbortSignal },
): AsyncGenerator<PracticeHintStreamEvent> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const url = `${apiStreamOrigin()}/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/hint/${encodeURIComponent(questionId)}`;
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body ?? {}),
    signal: options?.signal,
  });

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED");
    if (res.status === 409) throw new Error("HINT_ALREADY_USED");
    const text = await res.text().catch(() => "");
    throw new Error(`Hint request failed (${res.status}): ${text || res.statusText}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Normalize CRLF so "\r\n\r\n" event boundaries split like "\n\n"
      buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const ev = parseSseBlock(block);
        if (ev) yield ev;
        sep = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) {
      const ev = parseSseBlock(buffer.trim());
      if (ev) yield ev;
    }
  } finally {
    reader.releaseLock();
  }
}
