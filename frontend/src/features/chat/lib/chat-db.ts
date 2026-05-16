import Dexie, { type EntityTable } from "dexie"

import type { ChatMessage, ConversationSummary } from "@/entities/chat"

type CachedConversation = ConversationSummary & {
  folder_id: string
}

type CachedMessage = ChatMessage & {
  conversationId: string
}

const db = new Dexie("novalearn-chat") as Dexie & {
  conversations: EntityTable<CachedConversation, "id">
  messages: EntityTable<CachedMessage, "id">
}

db.version(3).stores({
  conversations: "id, folder_id, updated_at",
  messages: "id, conversationId, createdAt",
})

export { db }
export type { CachedConversation, CachedMessage }
