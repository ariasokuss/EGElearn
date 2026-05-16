"use client"

import type { ConversationSummary } from "@/entities/chat"
import { ChatHistoryItem } from "./chat-history-item"

type ChatHistorySectionProps = {
  label: string
  items: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  onRename?: (id: string, title: string) => void
}

function isOptimistic(id: string) {
  return id.startsWith("__optimistic_")
}

export function ChatHistorySection({
  label,
  items,
  activeId,
  onSelect,
  onDelete,
  onRename,
}: ChatHistorySectionProps) {
  return (
    <div className="flex flex-col items-start self-stretch">
      {/* Section header */}
      <div className="pt-3 pb-1">
        <span className="nova-text-label-medium text-[var(--ege-text)]">
          {label}
        </span>
      </div>

      {/* Items container — 8px gap, full-width stretch */}
      <div className="flex w-full flex-col items-start gap-2 self-stretch rounded-[9999px]">
        {items.map((conv) => {
          const creating = isOptimistic(conv.id)
          const active = conv.id === activeId && !creating

          return (
            <div key={conv.id} className="flex w-full self-stretch">
              <ChatHistoryItem
                id={conv.id}
                title={conv.title || ""}
                date={conv.updated_at || conv.created_at}
                state={creating ? "creating" : active ? "active" : "enabled"}
                onSelect={onSelect}
                onDelete={onDelete}
                onRename={onRename}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
