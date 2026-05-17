"use client"

import { useMemo } from "react"

import type { ConversationSummary } from "@/entities/chat"
import { groupConversations } from "./group-conversations"
import { ChatHistorySection } from "./chat-history-section"
import { Button } from "@/shared"

type ChatHistoryListProps = {
  conversations: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  onRename?: (id: string, title: string) => void
  loading?: boolean
  error?: string | null
  onRetry?: VoidFunction
}

function LoadingDots() {
  return (
    <div className="flex justify-center pt-8">
      <div className="flex gap-1.5">
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ege-muted)]"
          style={{ animationDelay: "0ms" }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ege-muted)]"
          style={{ animationDelay: "150ms" }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--ege-muted)]"
          style={{ animationDelay: "300ms" }}
        />
      </div>
    </div>
  )
}

export function ChatHistoryList({
  conversations,
  activeId,
  onSelect,
  onDelete,
  onRename,
  loading,
  error,
  onRetry,
}: ChatHistoryListProps) {
  const groups = useMemo(() => groupConversations(conversations), [conversations])

  if (loading && conversations.length === 0) {
    return <LoadingDots />
  }

  if (error && conversations.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 pt-6">
        <p className="text-center nova-text-label-tiny text-red-500">{error}</p>
        {onRetry && (
          <Button
            rounded={false}
            size="xs"
            type="button"
            onClick={onRetry}
            className="bg-red-50 text-red-600 hover:bg-red-100"
          >
            Попробовать ещё раз
          </Button>
        )}
      </div>
    )
  }

  if (conversations.length === 0) {
    return (
      <p className="pt-8 text-center nova-text-label-tiny text-[var(--ege-muted)]">
        Пока нет диалогов
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2 px-4">
      {groups.map((group, idx) => (
        <div key={group.label} className="flex flex-col gap-2">
          {idx > 0 && <div className="h-px self-stretch bg-[var(--ege-border)]" />}
          <ChatHistorySection
            label={group.label}
            items={group.items}
            activeId={activeId}
            onSelect={onSelect}
            onDelete={onDelete}
            onRename={onRename}
          />
        </div>
      ))}
    </div>
  )
}
