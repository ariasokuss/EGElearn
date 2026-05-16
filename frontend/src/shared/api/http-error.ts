export class HttpError extends Error {
  status: number
  statusText: string
  details?: string

  constructor(status: number, statusText: string, details?: string) {
    super(`HTTP ${status}${details ? `: ${details}` : statusText ? `: ${statusText}` : ""}`)
    this.name = "HttpError"
    this.status = status
    this.statusText = statusText
    this.details = details
  }
}

const MAX_HTTP_ERROR_DETAILS_LENGTH = 240

function sanitizeDetails(text: string): string | undefined {
  const normalized = text.trim()
  if (!normalized) return undefined

  const maybeHtml = /<(!doctype|html|body|head)\b/i.test(normalized)
  if (maybeHtml) return undefined

  if (normalized.length > MAX_HTTP_ERROR_DETAILS_LENGTH) {
    return `${normalized.slice(0, MAX_HTTP_ERROR_DETAILS_LENGTH)}...`
  }

  return normalized
}

function stringifyErrorPayload(payload: unknown): string | undefined {
  if (typeof payload === "string") return sanitizeDetails(payload)
  if (!payload || typeof payload !== "object") return undefined

  const known = payload as Record<string, unknown>
  const detail =
    known.detail ??
    known.message ??
    known.error_description ??
    known.error

  if (typeof detail === "string") return sanitizeDetails(detail)
  if (Array.isArray(detail)) {
    const text = detail
      .map(item => (typeof item === "string" ? item : JSON.stringify(item)))
      .filter(Boolean)
      .join(", ")
    return sanitizeDetails(text)
  }

  return sanitizeDetails(JSON.stringify(payload))
}

export async function throwHttpError(res: Response): Promise<never> {
  let details: string | undefined
  const contentType = res.headers.get("content-type") ?? ""

  try {
    if (contentType.includes("application/json")) {
      const json = await res.json()
      details = stringifyErrorPayload(json)
    } else {
      const text = await res.text()
      details = sanitizeDetails(text)
    }
  } catch {
    details = undefined
  }

  throw new HttpError(res.status, res.statusText, details)
}

export function isHttpStatus(error: unknown, status: number): boolean {
  return error instanceof HttpError && error.status === status
}

export function getHttpStatus(error: unknown): number | null {
  return error instanceof HttpError ? error.status : null
}
