/**
 * Browser: same-origin `/api/...` is proxied by Next rewrites (no cross-origin / CORS).
 * Server: full API URL if streaming is ever invoked during SSR.
 */
export function apiFetchOrigin(): string {
  if (typeof window !== "undefined") return ""
  return process.env.NEXT_PUBLIC_API_URL ?? "https://dev-api.novalearn.ai"
}

/**
 * Direct backend URL — bypasses Next.js rewrites.
 * Required for SSE/streaming endpoints because Next.js rewrites buffer the entire response.
 */
export function apiStreamOrigin(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "https://dev-api.novalearn.ai"
}
