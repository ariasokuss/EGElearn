import type {
  SessionDetailRead,
  SessionFeedbackRead,
  SessionHistoryItem,
  StartSessionResponse,
} from "@/shared/api/generated/model";

export async function getFeynmanHistory(lessonId: string): Promise<SessionHistoryItem[]> {
  const res = await fetch(
    `/api/v1/mini-feynman/history/lesson/${encodeURIComponent(lessonId)}`,
  );
  if (!res.ok) return [];
  return res.json();
}

export async function getSession(
  sessionId: string,
): Promise<SessionDetailRead | null> {
  const res = await fetch(
    `/api/v1/mini-feynman/session/${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function getSessionFeedback(
  sessionId: string,
): Promise<SessionFeedbackRead | null> {
  const res = await fetch(
    `/api/v1/mini-feynman/session/${encodeURIComponent(sessionId)}/feedback`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function startFeynmanSession(
  lessonId: string,
): Promise<StartSessionResponse | null> {
  if (!lessonId) return null;
  const res = await fetch(
    `/api/v1/mini-feynman/session/lesson/${encodeURIComponent(lessonId)}`,
    { method: "POST" },
  );
  if (!res.ok) return null;
  return res.json();
}

export async function abortFeynmanSession(
  sessionId: string,
): Promise<boolean> {
  const res = await fetch(`/api/v1/mini-feynman/session/${sessionId}/abort`, {
    method: "POST",
  });
  return res.ok;
}

export type SseTokenEvent = { content: string };
export type SseMessageCompleteEvent = {
  role: string;
  content: string;
  iteration: number;
  covered: boolean[];
};
export type SseSummaryEvent = {
  text: string;
  covered: boolean[];
  points: string[];
  all_covered: boolean;
};
export type SseEvent =
  | { event: "token"; data: SseTokenEvent }
  | { event: "message_complete"; data: SseMessageCompleteEvent }
  | { event: "summary"; data: SseSummaryEvent }
  | { event: string; data: Record<string, unknown> };

export async function* streamFeynmanAnswer(
  sessionId: string,
  answer: string,
): AsyncGenerator<SseEvent> {
  const res = await fetch(`/api/v1/mini-feynman/session/${sessionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });

  if (!res.ok || !res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      if (!block.trim()) continue;
      const lines = block.split("\n");
      let event = "message";
      let dataStr = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
      }

      if (dataStr) {
        try {
          yield { event, data: JSON.parse(dataStr) } as SseEvent;
        } catch {
          /* malformed SSE JSON */
        }
      }
    }
  }
}
