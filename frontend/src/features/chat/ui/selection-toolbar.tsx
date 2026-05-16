"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import type { TextSelectionState } from "../model/use-text-selection"
import { Button } from "@/shared"
import { ChatBubbleLeftRightIcon, HighlighterIcon, NoteAddIcon } from "@/shared/assets/icons"

function HandlePin({ flipped, clipId }: { flipped?: boolean; clipId: string }) {
  return (
    <svg
      width="8"
      height="26"
      viewBox="0 0 8 26"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={flipped ? { transform: "rotate(180deg)" } : undefined}
    >
      <g clipPath={`url(#${clipId})`}>
        <path
          d="M3 5H4.9958C4.99812 5 5 5.00188 5 5.0042V25C5 25.5523 4.55228 26 4 26C3.44772 26 3 25.5523 3 25V5Z"
          fill="var(--ege-accent)"
        />
      </g>
      <circle cx="4" cy="3" r="3" fill="var(--ege-accent)" />
      <defs>
        <clipPath id={clipId}>
          <path
            d="M3 5H5V25C5 25.5523 4.55228 26 4 26C3.44772 26 3 25.5523 3 25V5Z"
            fill="white"
          />
        </clipPath>
      </defs>
    </svg>
  )
}

function Divider() {
  return <div className="h-4 w-px shrink-0 bg-[var(--ege-border)]" />
}

type SelectionToolbarProps = {
  selection: TextSelectionState
  scrollContainerRef: React.RefObject<HTMLElement | null>
  onAskNova: (text: string, messageId: string) => void
}

export function SelectionToolbar({
  selection,
  scrollContainerRef,
  onAskNova,
}: SelectionToolbarProps) {
  const toolbarRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  const computePosition = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container || !selection) return null

    const rects = selection.containerRects
    if (rects.length === 0) return null

    const minTop = Math.min(...rects.map((r) => r.top))
    const minLeft = Math.min(...rects.map((r) => r.left))
    const maxRight = Math.max(...rects.map((r) => r.right))

    const toolbarWidth = toolbarRef.current?.offsetWidth ?? 243
    let top = minTop - 44 - 8
    let left = (minLeft + maxRight) / 2 - toolbarWidth / 2

    // Clamp boundaries
    const maxLeft = container.offsetWidth - toolbarWidth - 8
    left = Math.max(8, Math.min(left, maxLeft))

    const minVisibleTop = container.scrollTop + 8
    if (top < minVisibleTop) {
      const maxBottom = Math.max(...rects.map((r) => r.bottom))
      top = maxBottom + 8
    }

    return { top, left }
  }, [selection, scrollContainerRef])

  useEffect(() => {
    setPos(computePosition())
  }, [computePosition])

  useEffect(() => {
    const handleMouseDown = (e: MouseEvent) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target as Node)) {
        // Let native selection change handle dismissal
      }
    }
    document.addEventListener("mousedown", handleMouseDown)
    return () => document.removeEventListener("mousedown", handleMouseDown)
  }, [])

  if (!pos) return null

  const rects = selection.containerRects
  const first = rects[0]
  const last = rects[rects.length - 1]

  return (
    <>
      {first && last && (
        <>
          <div
            className="pointer-events-none absolute inset-0"
            style={{ mixBlendMode: "darken" }}
            aria-hidden="true"
          >
            {rects.map((r, i) => (
              <div
                key={i}
                className="absolute rounded-md bg-[var(--ege-track)]"
                style={{
                  top: r.top - 3,
                  left: r.left - 1,
                  width: r.width + 2,
                  height: r.height + 7,
                }}
              />
            ))}
          </div>

          <div className="pointer-events-none absolute inset-0 z-10" aria-hidden="true">
            <div
              className="absolute"
              style={{
                top: first.top - 6,
                left: first.left - 8,
              }}
            >
              <HandlePin clipId="chat-handle-start" />
            </div>
            <div
              className="absolute"
              style={{
                top: last.bottom - 20,
                left: last.right,
              }}
            >
              <HandlePin clipId="chat-handle-end" flipped />
            </div>
          </div>
        </>
      )}

      <div
        ref={toolbarRef}
        className="pointer-events-auto absolute z-50"
        style={{
          top: pos.top,
          left: pos.left,
          animation: "fade-in 120ms ease-out",
        }}
      >
        <div className="flex h-11 items-center gap-1.5 rounded-full border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-1 backdrop-blur-xs shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]">
          <Button
            variant="outline"
            onClick={(e) => {
              e.stopPropagation()
              onAskNova(selection.text, selection.messageId)
            }}
            className="gap-1"
            aria-label="Ask Nova"
            title="Ask Nova"
          >
            <ChatBubbleLeftRightIcon />
            <span>Ask Nova</span>
          </Button>

          <Divider />
          <Button variant="outline" iconOnly disabled aria-label="Highlight">
            <HighlighterIcon />
          </Button>
          <Divider />
          <Button variant="outline" iconOnly disabled aria-label="Add note">
            <NoteAddIcon />
          </Button>
        </div>
      </div>
    </>
  )
}
