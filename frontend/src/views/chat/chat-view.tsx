"use client"

import { useCallback } from "react"

import { ChatModule } from "@/features/chat"

type ChatViewProps = {
  initialConversationId?: string
}

/**
 * ChatView — routing adapter that wraps ChatModule with URL synchronization.
 *
 * IMPORTANT: Uses window.history directly (not Next.js router) for URL updates
 * within the chat feature. This prevents page remounts when the conversation ID
 * changes, which would destroy all chat state (messages, streaming, etc.).
 *
 * Next.js router.push navigates between page components (/chat → /chat/[id]),
 * causing ChatModule to unmount and remount. window.history.replaceState updates
 * the URL cosmetically without triggering navigation.
 */
export function ChatView({ initialConversationId }: ChatViewProps = {}) {
  const handleConversationChange = useCallback(
    (id: string | null) => {
      if (id && !id.startsWith("__optimistic_")) {
        const target = `/chat/${id}`
        if (typeof window !== "undefined" && window.location.pathname !== target) {
          window.history.replaceState(null, "", target)
        }
      }
    },
    [],
  )

  const handleNewChat = useCallback(() => {
    if (typeof window !== "undefined" && window.location.pathname !== "/chat") {
      window.history.replaceState(null, "", "/chat")
    }
  }, [])

  const handleSelectConversation = useCallback(
    (id: string) => {
      const target = `/chat/${id}`
      if (typeof window !== "undefined" && window.location.pathname !== target) {
        window.history.pushState(null, "", target)
      }
    },
    [],
  )

  return (
    <ChatModule
      initialConversationId={initialConversationId}
      onConversationChange={handleConversationChange}
      onNewChat={handleNewChat}
      onSelectConversation={handleSelectConversation}
    />
  )
}
