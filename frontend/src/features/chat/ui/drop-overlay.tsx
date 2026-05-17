"use client"

import { useState, useCallback } from "react";

import { validateFiles } from "@/features/chat/lib"
import { DropOverlayIcon } from "./drop-overlay-icon";

type DropOverlayProps = {
  onFilesAdded: (files: File[]) => void
}

export function DropOverlay({ onFilesAdded }: DropOverlayProps) {
  const [isHighlighted, setIsHighlighted] = useState(false)

  const handleDropOnZone = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const valid = validateFiles(e.dataTransfer.files, [], true)
      if (valid.length > 0) {
        onFilesAdded(valid)
      }
    },
    [onFilesAdded]
  )

  const handleDropOutside = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
    },
    []
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--ege-canvas)_88%,transparent)] backdrop-blur-sm animate-[fade-in_150ms_ease-out]"
      onDrop={handleDropOutside}
      onDragOver={(e) => e.preventDefault()}
    >
      <div
        className="relative animate-[fade-in_150ms_ease-out]"
        onDrop={handleDropOnZone}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDragEnter={(e) => {
          e.stopPropagation();
          setIsHighlighted(true);
        }}
        onDragLeave={(e) => {
          e.stopPropagation();
          setIsHighlighted(false);
        }}
      >
        <div
          className={`absolute -inset-2 rounded-[21px] border border-dashed transition-colors ${isHighlighted ? "border-[var(--ege-accent)]" : "border-[var(--ege-border)]"}`}
        />
        <div
          className={`flex w-90.25 flex-col items-center justify-center gap-8 rounded-[13px] border px-6 py-9 transition-colors ${isHighlighted ? "border-[var(--ege-accent)] bg-[var(--ege-surface-raised)]" : "border-[var(--ege-border)] bg-[var(--ege-surface)]"}`}
        >
          <DropOverlayIcon />
          <p className="max-w-67.25 text-center nova-text-label-small text-[var(--ege-text)]">
            Добавь файл сюда
            <br />
            Перетащи материал, чтобы прикрепить его
            <br />
            к диалогу
          </p>
        </div>
      </div>
    </div>
  );
}
