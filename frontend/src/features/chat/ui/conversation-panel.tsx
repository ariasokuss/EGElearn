"use client"

import type { ConversationSummary } from "@/entities/chat"
import { PencilEditIcon, HideBarIcon } from "@/shared/assets/icons"
import { ChatHistoryList } from "./history"
import { Button } from "@/shared"

type ConversationPanelProps = {
  conversations: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onNewChat: VoidFunction
  onDelete: (id: string) => void
  visible: boolean
  loading?: boolean
  error?: string | null
  onRetry?: VoidFunction
  onCollapse?: VoidFunction
  onRename?: (id: string, title: string) => void
}

function PanelIconButton({
  onClick,
  label,
  children,
}: {
  onClick: VoidFunction
  label: string
  children: React.ReactNode
}) {
  return (
    <Button
      iconOnly
      variant="outline"
      size="sm"
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex items-center justify-center duration-150"
    >
      <span className="flex h-4 w-4 items-center justify-center">{children}</span>
    </Button>
  )
}

export function ConversationPanel({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
  visible,
  loading,
  error,
  onRetry,
  onCollapse,
  onRename,
}: ConversationPanelProps) {
  if (!visible) return null

  return (
    <div className="flex w-full flex-col">
      {/* Header block */}
      <div className="relative flex shrink-0 items-center justify-between bg-[var(--ege-surface-raised)] px-3 py-3">
        {/* Gray divider — rendered inside at bottom:0 */}
        <span className="pointer-events-none absolute bottom-0 left-0 h-px w-full bg-[var(--ege-border)]" />

        <div className="relative">
          <Button
            type="button"
          >
            History
          </Button>
          {/* Active indicator */}
          <span
            className="pointer-events-none absolute -bottom-3 left-0 z-10 h-px w-full bg-[var(--ege-text)] transition-opacity duration-200"
          />
        </div>

        <div className="flex items-center gap-[8px]">
          <PanelIconButton onClick={onNewChat} label="New chat">
            <PencilEditIcon className="h-4 w-4" />
          </PanelIconButton>

          {onCollapse && (
            <>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width={1}
                height={16}
                viewBox="0 0 1 16"
                fill="none"
                aria-hidden
                className="shrink-0"
              >
                <path
                  d="M0 0.5C0 0.223858 0.223858 0 0.5 0V0C0.776142 0 1 0.223858 1 0.5V15.5C1 15.7761 0.776142 16 0.5 16V16C0.223858 16 0 15.7761 0 15.5V0.5Z"
                  fill="var(--ege-border)"
                />
              </svg>
              <PanelIconButton onClick={onCollapse} label="Collapse panel">
                <HideBarIcon className="h-4 w-4" />
              </PanelIconButton>
            </>
          )}
        </div>
      </div>

      {/* Chat history list */}
      <div className="no-scrollbar flex-1 overflow-y-auto pt-1">
        <ChatHistoryList
          conversations={conversations}
          activeId={activeId}
          onSelect={onSelect}
          onDelete={onDelete}
          onRename={onRename}
          loading={loading}
          error={error}
          onRetry={onRetry}
        />
      </div>
    </div>
  )
}
