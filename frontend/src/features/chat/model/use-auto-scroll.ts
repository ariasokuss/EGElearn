"use client"

import { useRef, useEffect, useState, useCallback } from "react"

import type { ChatStatus } from "@/entities/chat"

/**
 * Scrolls so the bottom of the last message aligns with the viewport bottom.
 */
function scrollToContentEnd(container: HTMLElement, behavior: ScrollBehavior) {
  const allMessages = container.querySelectorAll<HTMLElement>("[data-message-role]")
  const lastMsg = allMessages.item(allMessages.length - 1)

  if (lastMsg) {
    const wrapper = lastMsg.parentElement
    const target = wrapper ?? lastMsg
    const contentBottom = target.offsetTop + target.offsetHeight + 48
    const scrollTarget = contentBottom - container.clientHeight
    container.scrollTo({ top: Math.max(0, scrollTarget), behavior })
  } else {
    container.scrollTo({ top: container.scrollHeight, behavior })
  }
}

/**
 * Scrolls so the top of the last user message is near the top of the viewport.
 */
function scrollToLastUser(container: HTMLElement, behavior: ScrollBehavior) {
  const msgs = container.querySelectorAll<HTMLElement>('[data-message-role="user"]')
  const latest = msgs.item(msgs.length - 1)
  if (!latest) {
    container.scrollTo({ top: container.scrollHeight, behavior })
    return
  }
  const wrapper = latest.parentElement
  const target = wrapper ?? latest
  container.scrollTo({ top: Math.max(0, target.offsetTop - 16), behavior })
}

/**
 * Sets the spacer so `target`'s top can reach the top of the viewport.
 * Computed lazily (not per-token) to avoid layout thrashing.
 */
function applySpacerForTarget(container: HTMLElement, target: HTMLElement) {
  const spacer = container.querySelector<HTMLElement>("[data-chat-spacer]")
  if (!spacer) return

  // Temporarily zero-out to measure natural content height
  spacer.style.minHeight = "0"

  const desiredMaxScroll = target.offsetTop
  const naturalMaxScroll = container.scrollHeight - container.clientHeight
  const needed = Math.max(0, desiredMaxScroll - naturalMaxScroll)
  spacer.style.minHeight = `${needed}px`
}

function applySpacerForLastUser(container: HTMLElement) {
  const userMsgs = container.querySelectorAll<HTMLElement>('[data-message-role="user"]')
  const lastUser = userMsgs.item(userMsgs.length - 1)
  if (!lastUser) return
  const target = lastUser.parentElement ?? lastUser
  applySpacerForTarget(container, target)
}

function applySpacerForLastAssistant(container: HTMLElement) {
  const msgs = container.querySelectorAll<HTMLElement>('[data-message-role="assistant"]')
  const latest = msgs.item(msgs.length - 1)
  if (!latest) return
  const target = latest.parentElement ?? latest
  applySpacerForTarget(container, target)
}

export function useAutoScroll(
  deps: unknown[],
  status?: ChatStatus,
  resetKey?: unknown,
  followUpdates: boolean = true,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const initialScrollDone = useRef(false)
  const prevStatusRef = useRef(status)
  const statusRef = useRef(status)
  const lastAssistantIdRef = useRef<string | null>(null)

  useEffect(() => {
    initialScrollDone.current = false
    lastAssistantIdRef.current = null
  }, [resetKey])

  // Keep ref in sync
  useEffect(() => { statusRef.current = status }, [status])

  // Keep prevStatus in sync (no actions on transitions — spacer + scroll handled by handleSend)
  useEffect(() => {
    prevStatusRef.current = status
  }, [status])

  // ── Track scroll position (for "↓ Down" button) ──
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    function handleScroll() {
      if (!container) return
      const { scrollTop, clientHeight } = container

      const allMessages = container.querySelectorAll<HTMLElement>("[data-message-role]")
      const lastMsg = allMessages.item(allMessages.length - 1)
      const viewportBottom = scrollTop + clientHeight

      if (lastMsg) {
        const wrapper = lastMsg.parentElement
        const target = wrapper ?? lastMsg
        const contentBottom = target.offsetTop + target.offsetHeight
        setIsAtBottom(viewportBottom >= contentBottom - 80)
      } else {
        setIsAtBottom(true)
      }
    }

    container.addEventListener("scroll", handleScroll, { passive: true })
    return () => container.removeEventListener("scroll", handleScroll)
  }, [])

  // ── Initial scroll + auto-scroll to assistant start on first appearance ──
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    if (!initialScrollDone.current) {
      applySpacerForLastUser(container)
      scrollToContentEnd(container, "instant")
      initialScrollDone.current = true
      // Seed last-assistant so we don't fire the auto-scroll for history on load.
      const msgs = container.querySelectorAll<HTMLElement>('[data-message-role="assistant"]')
      const latest = msgs.item(msgs.length - 1)
      lastAssistantIdRef.current = latest?.getAttribute("data-message-id") ?? null
      return
    }

    // When a new assistant message bubble first appears (e.g. first stream
    // chunk arrives, or regenerate started), bring its start into view so the
    // user sees the beginning of the LLM response — even if their own message
    // was huge.
    const msgs = container.querySelectorAll<HTMLElement>('[data-message-role="assistant"]')
    const latest = msgs.item(msgs.length - 1)
    const latestId = latest?.getAttribute("data-message-id") ?? null
    if (latest && latestId && latestId !== lastAssistantIdRef.current) {
      lastAssistantIdRef.current = latestId
      applySpacerForLastAssistant(container)
      requestAnimationFrame(() => {
        const target = latest.parentElement ?? latest
        container.scrollTo({
          top: Math.max(0, target.offsetTop - 8),
          behavior: "smooth",
        })
      })
    }
  }, [...deps, status, followUpdates]) // eslint-disable-line react-hooks/exhaustive-deps

  const scrollToBottom = useCallback(() => {
    if (!containerRef.current) return
    scrollToContentEnd(containerRef.current, "smooth")
  }, [])

  const scrollToLatestAssistantStart = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const msgs = container.querySelectorAll<HTMLElement>('[data-message-role="assistant"]')
    const latest = msgs.item(msgs.length - 1)
    if (!latest) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" })
      return
    }
    const wrapper = latest.parentElement
    const target = wrapper ?? latest
    container.scrollTo({ top: Math.max(0, target.offsetTop - 8), behavior: "smooth" })
  }, [])

  const scrollToLastUserMessage = useCallback(() => {
    if (!containerRef.current) return
    scrollToLastUser(containerRef.current, "smooth")
  }, [])

  /**
   * Call right after a user message is sent: expands the bottom spacer just
   * enough for the new user message to reach the top (replacing the old
   * hard-coded 60vh hack, which fell short for very long messages) and
   * scrolls there. When the assistant bubble appears, the `[...deps,status]`
   * effect will take over and pull its start into view.
   */
  const prepareForSend = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    requestAnimationFrame(() => {
      applySpacerForLastUser(container)
      requestAnimationFrame(() => {
        scrollToLastUser(container, "smooth")
      })
    })
  }, [])

  return {
    containerRef,
    isAtBottom,
    scrollToBottom,
    scrollToLatestAssistantStart,
    scrollToLastUserMessage,
    prepareForSend,
  }
}
