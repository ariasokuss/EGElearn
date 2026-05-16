import { apiFetchOrigin } from "@/shared/api/api-fetch-origin";
import { getAccessToken } from "@/shared/lib/auth-storage";

/**
 * Save the pre-generated hint as a real user+assistant message pair
 * in a practice-scoped chat conversation (creates one if needed).
 *
 * Returns the conversation_id so the chat panel can switch to it.
 */
export async function savePracticeHint(
  sessionId: string,
  questionId: string,
  body: { folder_id: string; conversation_id?: string },
): Promise<{ conversation_id: string }> {
  const token = getAccessToken();
  const res = await fetch(
    `${apiFetchOrigin()}/api/v1/tests/sessions/${sessionId}/save-hint/${questionId}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `save-hint failed (${res.status})`);
  }

  return res.json();
}
