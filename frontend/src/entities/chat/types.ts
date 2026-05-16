export type { ChatMessageRequest } from "@/shared/api/generated/model"
export type { MessageSchema } from "@/shared/api/generated/model"
export type { ConversationSummary } from "@/shared/api/generated/model"
export type { GetMessagesResponse } from "@/shared/api/generated/model"
export type { ListConversationsResponse } from "@/shared/api/generated/model"
export type { FolderDocumentRead } from "@/shared/api/generated/model"
export type { ListFolderDocumentsResponse } from "@/shared/api/generated/model"
export type { RenameTitleRequest } from "@/shared/api/generated/model"

export type ModelOption = {
  id: string
  name: string
  provider: string
}

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  metadata?: Record<string, unknown>
  attachments?: FileAttachment[]
  /** Base64-encoded image strings or URLs from the backend */
  images?: string[]
  /** Citation/quote text fragments */
  citations?: string[]
  createdAt: string
  /** Parent message ID in the tree (null for root) */
  parentId?: string | null
  /** Number of sibling versions at this position (1 = no branches) */
  siblingCount: number
  /** 1-based version index among siblings */
  versionIndex: number
  /** Stable key for React rendering — survives id reconciliation */
  _renderKey?: string
}

export type FileAttachment = {
  name: string
  type: string
  size: number
  url: string
}

export type ChatStatus = "ready" | "submitted" | "streaming" | "error"

export type TaggedPart = {
  text: string
  messageId: string
  start: number
  end: number
}
