"use client"

import type { ConversationSummary } from "@/entities/chat"
import { ChatHistoryList } from "./history"

type MobileConversationListProps = {
  conversations: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  loading?: boolean
  error?: string | null
  onRetry?: VoidFunction
}

export function MobileConversationList({
  conversations,
  activeId,
  onSelect,
  onDelete,
  loading,
  error,
  onRetry,
}: MobileConversationListProps) {
  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto pt-1">
      <ChatHistoryList
        conversations={conversations}
        activeId={activeId}
        onSelect={onSelect}
        onDelete={onDelete}
        loading={loading}
        error={error}
        onRetry={onRetry}
      />
    </div>
  )
}
