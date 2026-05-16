"use client"

import { useCallback, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"

type UseChatRouterOptions = {
  /** Current active conversation ID from useChat */
  conversationId: string | null
  /** Raw switchConversation from useChat */
  switchConversation: (id: string) => void
  /** Raw startNewChat from useChat */
  startNewChat: VoidFunction
}

type UseChatRouterReturn = {
  /** Select conversation — updates state + URL */
  selectConversation: (id: string) => void
  /** Start new chat — resets state + navigates to /chat */
  createNewChat: VoidFunction
}

/**
 * useChatRouter — synchronizes chat state with URL routing.
 *
 * - Pushes URL on manual conversation switch
 * - Replaces URL when conversationId changes (e.g. after optimistic → real ID reconciliation)
 * - Navigates to /chat on new chat creation
 */
export function useChatRouter({
  conversationId,
  switchConversation,
  startNewChat,
}: UseChatRouterOptions): UseChatRouterReturn {
  const router = useRouter()

  // Sync URL when conversationId changes (e.g. after new chat creation resolves)
  const prevIdRef = useRef(conversationId)
  useEffect(() => {
    if (
      conversationId &&
      conversationId !== prevIdRef.current &&
      !conversationId.startsWith("__optimistic_")
    ) {
      const target = `/chat/${conversationId}`
      if (typeof window !== "undefined" && window.location.pathname !== target) {
        router.replace(target, { scroll: false })
      }
    }
    prevIdRef.current = conversationId
  }, [conversationId, router])

  const selectConversation = useCallback(
    (id: string) => {
      switchConversation(id)
      router.push(`/chat/${id}`, { scroll: false })
    },
    [switchConversation, router],
  )

  const createNewChat = useCallback(() => {
    startNewChat()
    router.push("/chat", { scroll: false })
  }, [startNewChat, router])

  return { selectConversation, createNewChat }
}
