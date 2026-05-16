import { apiStreamOrigin } from "./api-fetch-origin"
import { getAccessToken } from "@/shared/lib/auth-storage"

export type SwitchBranchResponse = {
  active_path: string[]
  messages: Array<{
    id: string
    role: string
    content: string
    metadata: Record<string, unknown>
    citations: string[]
    images: string[]
    attachments: Array<{
      filename: string
      mime_type: string
      type: string
      url: string | null
    }>
    created_at: string
    parent_id: string | null
    sibling_count: number
    version_index: number
  }>
}

export async function switchBranch(
  conversationId: string,
  messageId: string,
  direction: "next" | "prev",
): Promise<SwitchBranchResponse> {
  const token = getAccessToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(
    `${apiStreamOrigin()}/api/v1/chat/conversations/${conversationId}/switch-branch`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ message_id: messageId, direction }),
    },
  )

  if (!res.ok) {
    if (res.status === 401) throw new Error("AUTH_EXPIRED")
    const text = await res.text().catch(() => "Unknown error")
    throw new Error(`Switch branch failed (${res.status}): ${text}`)
  }

  return res.json()
}
