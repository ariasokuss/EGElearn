"use client"

import { memo } from "react"
import { cn } from "@/shared/lib"

type BranchNavigatorProps = {
  versionIndex: number
  siblingCount: number
  disabled?: boolean
  onPrev: () => void
  onNext: () => void
}

export const BranchNavigator = memo(function BranchNavigator({
  versionIndex,
  siblingCount,
  disabled = false,
  onPrev,
  onNext,
}: BranchNavigatorProps) {
  if (siblingCount <= 1) return null

  return (
    <div className="flex items-center gap-1 text-[var(--ege-muted)] select-none">
      <button
        type="button"
        onClick={onPrev}
        disabled={disabled || versionIndex <= 1}
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded transition-colors",
          disabled || versionIndex <= 1
            ? "cursor-not-allowed opacity-30"
            : "hover:bg-[var(--ege-surface)] hover:text-[var(--ege-text)]",
        )}
        aria-label="Предыдущая версия"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 2L3 5L6 8" />
        </svg>
      </button>
      <span className="tabular-nums nova-text-label-tiny min-w-[2ch] text-center">
        {versionIndex}/{siblingCount}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={disabled || versionIndex >= siblingCount}
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded transition-colors",
          disabled || versionIndex >= siblingCount
            ? "cursor-not-allowed opacity-30"
            : "hover:bg-[var(--ege-surface)] hover:text-[var(--ege-text)]",
        )}
        aria-label="Следующая версия"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 2L7 5L4 8" />
        </svg>
      </button>
    </div>
  )
})
