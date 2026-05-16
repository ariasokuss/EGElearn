"use client"

import { useState, useEffect, useCallback, useRef } from "react"

export type TextSelectionState = {
  /** The selected text string */
  text: string
  /** Bounding rect of the selection relative to the viewport */
  rect: DOMRect
  /** Selection rects relative to the scroll container */
  containerRects: Array<{
    top: number
    left: number
    right: number
    bottom: number
    width: number
    height: number
  }>
  /** The Range object — needed for highlight wrapping */
  range: Range
  /** ID of the message this selection belongs to */
  messageId: string
}

/**
 * useTextSelection — listens for native text selections within a container.
 *
 * Returns the current selection state (text + position) or null.
 * The toolbar should render based on this state.
 *
 * Selection is only captured when it originates inside a data-message-id container.
 */
export function useTextSelection(containerRef: React.RefObject<HTMLElement | null>) {
  const [selection, setSelection] = useState<TextSelectionState | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const updateSelection = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.rangeCount) {
      setSelection(null)
      return
    }

    const range = sel.getRangeAt(0)
    const text = sel.toString().trim()
    if (!text) {
      setSelection(null)
      return
    }

    // Find which message the selection belongs to
    const container = containerRef.current
    if (!container) {
      setSelection(null)
      return
    }

    // Ensure selection is within our container
    if (!container.contains(range.commonAncestorContainer)) {
      setSelection(null)
      return
    }

    // Walk up from the selection to find data-message-id
    let node: Node | null = range.commonAncestorContainer
    let messageEl: HTMLElement | null = null
    while (node && node !== container) {
      if (node instanceof HTMLElement && node.dataset.messageId) {
        messageEl = node
        break
      }
      node = node.parentNode
    }

    if (!messageEl) {
      setSelection(null)
      return
    }

    // Only allow selection on assistant messages
    if (messageEl.dataset.messageRole !== "assistant") {
      setSelection(null)
      return
    }

    const messageId = messageEl.dataset.messageId!

    const rect = range.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()
    const rawRects = Array.from(range.getClientRects()).filter((r) => r.width > 1)
    const containerRects = rawRects.map((r) => ({
      top: r.top - containerRect.top + container.scrollTop,
      left: r.left - containerRect.left,
      right: r.right - containerRect.left,
      bottom: r.bottom - containerRect.top + container.scrollTop,
      width: r.width,
      height: r.height,
    }))

    setSelection({ text, rect, containerRects, range: range.cloneRange(), messageId })
  }, [containerRef])

  const clearSelection = useCallback(() => {
    window.getSelection()?.removeAllRanges()
    setSelection(null)
  }, [])

  useEffect(() => {
    const handleSelectionChange = () => {
      clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(updateSelection, 80)
    }

    document.addEventListener("selectionchange", handleSelectionChange)
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange)
      clearTimeout(debounceRef.current)
    }
  }, [updateSelection])

  return { selection, clearSelection }
}
