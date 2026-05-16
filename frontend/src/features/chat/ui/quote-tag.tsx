"use client"

import { cn } from "@/shared/lib"
import type { TaggedPart } from "@/entities/chat"
import { Button } from "@/shared"

type QuoteTagProps = {
  taggedPart: TaggedPart
  onRemove: VoidFunction
  /** Bottom divider — only when files are attached above the input area */
  hasAttachedFiles?: boolean
}

/**
 * Quote icon — curved arrow, from Figma design.
 * 18×18 icon centered in a 42×42 container.
 */
function QuoteArrowIcon() {
  return (
    <div className="flex h-[42px] w-[42px] shrink-0 items-center justify-center">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 18 18"
        fill="none"
      >
        <path
          d="M11.25 6.75L15.75 11.25M15.75 11.25L11.25 15.75M15.75 11.25H6.75C4.26472 11.25 2.25 9.23528 2.25 6.75C2.25 4.26472 4.26472 2.25 6.75 2.25H9"
          stroke="var(--ege-muted)"
          strokeWidth="1.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  )
}

/**
 * Close (X) button for the quote block.
 */
function CloseButton({ onClick }: { onClick: VoidFunction }) {
  return (
    <Button
      variant="plain"
      size="xs"
      iconOnly
      type="button"
      onClick={onClick}
      className="flex shrink-0 items-center justify-center text-[var(--ege-muted)] duration-150 hover:text-[var(--ege-text)]"
      aria-label="Remove quote"
      title="Remove quote"
    >
      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      >
        <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" />
      </svg>
    </Button>
  )
}

/**
 * QuoteTag — displays a tagged/quoted text fragment above the chat input.
 *
 * Matches Figma node 206:14131 / chatLinkMessage:
 *   - 42×42 icon container with flipped arrow-uturn-right
 *   - Inter Regular 14px, color #A1A1AA, line-height 20px, tracking -0.112px
 *   - 2-line clamp with text-ellipsis overflow
 *   - 1px divider at bottom (#F4F4F5)
 *   - Close button on the right
 */
export function QuoteTag({ taggedPart, onRemove, hasAttachedFiles }: QuoteTagProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-1 py-2 pr-4 pl-1.5",
        hasAttachedFiles && "border-b border-[var(--ege-border)]",
      )}
    >
      <QuoteArrowIcon />

      <p
        className="min-w-0 flex-1 overflow-hidden nova-text-label-medium-regular text-[var(--ege-muted)]"
        style={{
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          letterSpacing: "-0.112px",
        }}
      >
        &ldquo;{taggedPart.text}&rdquo;
      </p>

      <CloseButton onClick={onRemove} />
    </div>
  )
}

/**
 * QuoteBlock — renders a quoted fragment inside a sent message bubble.
 * Matches the same citation design language as the input QuoteTag:
 *   - Same arrow icon (smaller container for in-message use)
 *   - Same typography: Inter Regular 14px, #A1A1AA, tracking -0.112px
 *   - 2-line clamp with ellipsis
 *   - Subtle bottom divider to separate from message body
 */
export function QuoteBlock({ text }: { text: string }) {
  return (
    <div className="mb-1">
      <div className="flex items-center gap-1 py-1.5 pl-0.5 pr-2">
        <QuoteArrowIcon />
        <p
          className="min-w-0 flex-1 overflow-hidden nova-text-label-medium-regular text-[var(--ege-muted)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            letterSpacing: "-0.112px",
          }}
        >
          &ldquo;{text}&rdquo;
        </p>
      </div>
      
    </div>
  )
}
