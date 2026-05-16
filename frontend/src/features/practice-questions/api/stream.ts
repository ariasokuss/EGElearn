import { apiStreamOrigin } from "@/shared/api/api-fetch-origin";
import { throwHttpError } from "@/shared/api/http-error";

export async function* streamSSE<T>(path: string, method?: string, body?: BodyInit | null): AsyncGenerator<T> {
  const streamOrigin = apiStreamOrigin()
  const ssepath = path.startsWith(streamOrigin) ? path : streamOrigin + path
  const res = await fetch(ssepath, {
    method,
    body,
  });

  if (!res.ok) await throwHttpError(res);
  if (!res.body) return;

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
          yield { event, ...JSON.parse(dataStr) } as T;
        } catch {
          /* malformed SSE JSON */
        }
      }
    }
  }
}