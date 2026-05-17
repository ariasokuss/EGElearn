"use client"

import { memo, useEffect, useCallback, type ReactNode } from "react"

import { cn } from "@/shared/lib"
import type { ChatMessage, ChatStatus, TaggedPart } from "@/entities/chat"
import { useAutoScroll } from "@/features/chat/model"
import { useTextSelection } from "../model/use-text-selection"
import { MessageBubble } from "./message-bubble"
import { SelectionToolbar } from "./selection-toolbar"

/** Calculate the text offset of a position relative to a container element. */
function getTextOffset(container: Element, node: Node, offset: number): number {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  let charCount = 0
  let current: Text | null
  while ((current = walker.nextNode() as Text | null)) {
    if (current === node) return charCount + offset
    charCount += current.length
  }
  return charCount + offset
}

const FADE_IN_STYLE = { animation: "fade-in 300ms ease-out" } as const;

type ChatMessagesProps = {
  messages: ChatMessage[]
  status: ChatStatus
  conversationId?: string | null
  onEdit?: (index: number, newContent: string) => void
  onRegenerate?: (index: number) => void
  onScrollStateChange?: (
    isAtBottom: boolean,
    scrollToBottom: () => void,
    scrollToLatestAssistantStart: () => void,
    scrollToLastUserMessage: () => void,
    prepareForSend: () => void,
  ) => void
  onSetTaggedPart?: (part: TaggedPart) => void
  followUpdates?: boolean
  /** Rendered after the last message, inside the scroll area (e.g. practice hint under the thread). */
  afterMessages?: ReactNode
  /** Changes when afterMessages content grows — keeps autoscroll in sync while streaming. */
  afterMessagesScrollKey?: string | number
  /** Per-message extra content: maps message ID → ReactNode rendered right after that message. */
  afterMessageSlots?: Record<string, ReactNode>
  onSwitchBranch?: (messageId: string, direction: "next" | "prev") => void
}

export const ChatMessages = memo(function ChatMessages({
  messages,
  status,
  conversationId,
  onEdit,
  onRegenerate,
  onScrollStateChange,
  onSetTaggedPart,
  followUpdates = true,
  afterMessages,
  afterMessagesScrollKey,
  afterMessageSlots,
  onSwitchBranch,
}: ChatMessagesProps) {
  const {
    containerRef,
    isAtBottom,
    scrollToBottom,
    scrollToLatestAssistantStart,
    scrollToLastUserMessage,
    prepareForSend,
  } = useAutoScroll(
    [messages, afterMessagesScrollKey ?? ""],
    status,
    conversationId,
    followUpdates,
  )

  useEffect(() => {
    onScrollStateChange?.(
      isAtBottom,
      scrollToBottom,
      scrollToLatestAssistantStart,
      scrollToLastUserMessage,
      prepareForSend,
    )
  }, [
    isAtBottom,
    scrollToBottom,
    scrollToLatestAssistantStart,
    scrollToLastUserMessage,
    prepareForSend,
    onScrollStateChange,
  ])

  const { selection, clearSelection } = useTextSelection(containerRef)

  // Clear selection when switching conversations
  useEffect(() => {
    clearSelection()
  }, [conversationId, clearSelection])

  const handleAskNova = useCallback((text: string, messageId: string) => {
    if (!selection || !onSetTaggedPart) {
      clearSelection()
      return
    }

    // Compute offsets from the message container
    const messageEl = document.querySelector(`[data-message-id="${messageId}"]`)
    const start = messageEl
      ? getTextOffset(messageEl, selection.range.startContainer, selection.range.startOffset)
      : 0
    const end = messageEl
      ? getTextOffset(messageEl, selection.range.endContainer, selection.range.endOffset)
      : text.length

    onSetTaggedPart({ text, messageId, start, end })
    clearSelection()
  }, [clearSelection, selection, onSetTaggedPart])

  // Show loading dots while waiting for LLM content:
  // - "submitted" = request sent, no tokens yet
  // - "streaming" but last message is user = first token arrived but assistant
  //   bubble hasn't been added to the array yet (RAF pending)
  const lastMsg = messages[messages.length - 1]
  const showLoadingDots =
    status === "submitted" ||
    (status === "streaming" && (!lastMsg || lastMsg.role === "user"))

  return (
    <div ref={containerRef} className="relative flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[744px] flex-col gap-8 px-4 pt-6 pb-16 md:gap-11.5">
        {messages.map((msg, i) => {
          const isFirst = i === 0;
          const isLast = i === messages.length - 1;

          const slot = afterMessageSlots?.[msg.id];

          return (
            <div
              key={msg._renderKey ?? msg.id}
              className={cn(isFirst && "pt-2")}
              style={FADE_IN_STYLE}
            >
              <MessageBubble
                message={msg}
                index={i}
                isLast={isLast}
                status={status}
                onEdit={onEdit}
                onRegenerate={onRegenerate}
                onSwitchBranch={onSwitchBranch}
              />
              {slot && (
                <div className="mt-3 w-full">{slot}</div>
              )}
            </div>
          );
        })}

        {afterMessages && (
          <div className="w-full" data-practice-hint-after-messages>
            {afterMessages}
          </div>
        )}

        {showLoadingDots && (
          <div className="flex justify-start">
            <div className="flex gap-1.5 py-2">
              <span
                className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]"
                style={{ animationDelay: "0ms" }}
              />
              <span
                className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]"
                style={{ animationDelay: "150ms" }}
              />
              <span
                className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]"
                style={{ animationDelay: "300ms" }}
              />
            </div>
          </div>
        )}

        {/* Bottom spacer: always in DOM, activated imperatively from handleSend */}
        <div data-chat-spacer />
      </div>

      {/* Selection floating toolbar — only render when the host actually wires
          a tagged-part callback. Otherwise the assistant action would appear but clicks
          would silently no-op (previously the case for Feynman before FRO-26). */}
      {selection && onSetTaggedPart && (
        <SelectionToolbar
          selection={selection}
          scrollContainerRef={containerRef}
          onAskNova={handleAskNova}
        />
      )}
    </div>
  )
})
