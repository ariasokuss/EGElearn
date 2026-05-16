"use client"

import { useState, useRef, useCallback } from "react"
import { cn } from "@/shared/lib"
import { TrashIcon } from "@/shared/assets/icons";
import { Button } from "@/shared";

/* ── Types ── */

type ChatHistoryItemState = "enabled" | "active" | "creating"

type ChatHistoryItemProps = {
  id: string
  title: string
  date: string
  state?: ChatHistoryItemState
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  onRename?: (id: string, title: string) => void
}

/* ── Reusable action button ── */

function ItemAction({
  onClick,
  label,
  children,
}: {
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <Button
      variant="plain"
      iconOnly
      size="sm"
      type="button"
      onMouseDown={(e) => {
        e.stopPropagation()
        e.preventDefault()
        onClick()
      }}
      onClick={(e) => e.stopPropagation()}
      aria-label={label}
      title={label}
      className="flex items-center justify-center"
    >
      <span className="flex h-4 w-4 items-center justify-center">{children}</span>
    </Button>
  )
}

/* ── Action buttons block (always takes space, visibility changes) ── */

function ActionButtons({
  id,
  onStartRename,
  onDelete,
  visible,
}: {
  id: string
  onStartRename?: VoidFunction
  onDelete?: (id: string) => void
  visible: boolean
}) {
  if (!onStartRename && !onDelete) return null

  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-0.5 transition-opacity",
        visible ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      {onStartRename && (
        <ItemAction onClick={onStartRename} label="Rename conversation">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1.22116 9.57278L0.699951 12.7L3.82719 12.1788C4.37025 12.0883 4.87145 11.8303 5.26075 11.441L12.3131 4.38854C12.8289 3.87277 12.8289 3.03655 12.3131 2.52079L10.8791 1.08678C10.3633 0.571001 9.52702 0.57101 9.01124 1.0868L1.95889 8.13926C1.5696 8.52855 1.31167 9.02974 1.22116 9.57278Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </ItemAction>
      )}
      {onDelete && (
        <ItemAction onClick={() => onDelete(id)} label="Delete conversation">
          <TrashIcon className="size-4" />
        </ItemAction>
      )}
    </div>
  )
}

/* ── Main component ── */

export function ChatHistoryItem({
  id,
  title,
  date,
  state = "enabled",
  onSelect,
  onDelete,
  onRename,
}: ChatHistoryItemProps) {
  void date
  const isActive = state === "active"
  const isCreating = state === "creating"
  const hasActions = !!(onRename || onDelete)

  /* ── Inline rename state ── */
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  const startRename = useCallback(() => {
    setRenameValue(title)
    setIsRenaming(true)
    // Focus after React renders the input, cursor at end
    setTimeout(() => {
      const el = inputRef.current
      if (el) {
        el.focus()
        el.setSelectionRange(el.value.length, el.value.length)
      }
    }, 0)
  }, [title])

  const commitRename = useCallback(() => {
    if (!isRenaming) return
    setIsRenaming(false)
    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== title && onRename) {
      onRename(id, trimmed)
    }
  }, [isRenaming, renameValue, title, onRename, id])

  const cancelRename = useCallback(() => {
    setRenameValue(title)
    setIsRenaming(false)
  }, [title])

  const handleSelect = useCallback(() => {
    if (isRenaming) return
    onSelect(id)
  }, [isRenaming, onSelect, id])

  const handleSelectKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        if (isRenaming) return
        onSelect(id)
      }
    },
    [isRenaming, onSelect, id],
  )

  /* ── Creating / placeholder state ── */
  if (isCreating) {
    return (
      <div className="group w-full rounded-[9999px] border border-dashed border-[var(--ege-border)]">
        <div className="flex w-full items-center gap-3 overflow-clip rounded-[9999px] px-3 py-3">
          <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
            <span className="min-w-0 flex-1 truncate nova-text-label-small-regular text-[var(--ege-text)]">
              {title || "Untitled"}
            </span>

          </div>
        </div>
      </div>
    )
  }

  /* ── Active state ── */
  if (isActive) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={handleSelect}
        onKeyDown={handleSelectKeyDown}
        className="group w-full cursor-pointer rounded-[18px] border border-transparent"
      >
        <div
          className="flex w-full items-center gap-3 overflow-clip rounded-[9999px] py-2 px-3"
          style={{ backgroundColor: "var(--ege-surface)" }}
        >
          <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
            {isRenaming ? (
              <input
                ref={inputRef}
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  e.stopPropagation()
                  if (e.key === "Enter") { e.preventDefault(); commitRename() }
                  if (e.key === "Escape") cancelRename()
                }}
                onBlur={commitRename}
                onClick={(e) => e.stopPropagation()}
                className="min-w-0 flex-1 truncate bg-transparent nova-text-label-small-regular text-[var(--ege-text)] outline-none border-none shadow-none p-0"
              />
            ) : (
              <span className="min-w-0 flex-1 truncate nova-text-label-small-regular text-[var(--ege-text)]">
                {title || "Untitled"}
              </span>
            )}
            {hasActions && (
              <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100">
                <ActionButtons
                  id={id}
                  onStartRename={onRename ? startRename : undefined}
                  onDelete={onDelete}
                  visible={!isRenaming}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  /* ── Enabled state (default) ── */
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={handleSelectKeyDown}
      className={cn(
        "group w-full cursor-pointer rounded-[18px] border border-transparent",
        "transition-[border-color,border-radius,box-shadow,background-color] duration-300 ease-out hover:duration-0",
        "hover:rounded-[9999px] hover:border-[var(--ege-border)]",
        "active:rounded-[9999px] active:border-[var(--ege-border)]",
      )}
    >
      <div
        className={cn(
          "flex w-full items-center gap-3 overflow-clip rounded-[9999px] py-2 px-3",
          "transition-[background-color,box-shadow] duration-300 ease-out hover:duration-0",
          "group-hover:bg-[var(--ege-surface-raised)] group-active:bg-[var(--ege-surface)]",
          "group-hover:shadow-[0_0_0_3px_rgba(217,16,36,0.12),0_1px_2px_-1px_rgba(11,15,26,0.10),0_2px_4px_0_rgba(11,15,26,0.06)]",
          "group-active:shadow-[0_0_0_3px_rgba(217,16,36,0.12),0_1px_2px_-1px_rgba(11,15,26,0.10),0_2px_4px_0_rgba(11,15,26,0.06)]",
        )}
      >
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
          {isRenaming ? (
            <input
              ref={inputRef}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                e.stopPropagation()
                if (e.key === "Enter") { e.preventDefault(); commitRename() }
                if (e.key === "Escape") cancelRename()
              }}
              onBlur={commitRename}
              onClick={(e) => e.stopPropagation()}
              className="min-w-0 flex-1 truncate bg-transparent nova-text-label-small-regular text-[var(--ege-text)] outline-none border-none shadow-none p-0"
            />
          ) : (
            <span className="min-w-0 flex-1 truncate nova-text-label-small-regular text-[var(--ege-text)]">
              {title || "Untitled"}
            </span>
          )}

          {hasActions && (
            <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100">
              <ActionButtons
                id={id}
                onStartRename={onRename ? startRename : undefined}
                onDelete={onDelete}
                visible={!isRenaming}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
