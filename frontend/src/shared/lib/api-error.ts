export function formatApiValidationError(
  data: unknown,
  fallback = "Something went wrong"
): string {
  if (typeof data !== "object" || data === null) return fallback;

  const detail = (data as { detail?: unknown }).detail;

  if (typeof detail === "string") {
    const trimmed = detail.trim();
    return trimmed.length > 0 ? trimmed : fallback;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === "object" && "msg" in first) {
      const msg = (first as { msg?: unknown }).msg;
      if (typeof msg === "string" && msg.length > 0) return msg;
    }
    const firstString = detail.find(
      (item): item is string => typeof item === "string"
    );
    if (firstString?.trim()) return firstString.trim();
  }

  return fallback;
}
