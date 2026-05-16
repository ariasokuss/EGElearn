"use client"

import { useState, useRef, useEffect } from "react"

import { cn } from "@/shared/lib"
import type { ModelOption } from "@/entities/chat"
import { ChevronDownIcon } from "@/shared/assets/icons"
import { Button } from "@/shared"

type ModelSelectorProps = {
  models: ModelOption[]
  selectedModelId: string
  onModelChange: (modelId: string) => void
  isLoading?: boolean
  error?: string | null
}

const LABEL_CLASSES =
  "flex items-center gap-1 rounded-lg px-2 py-1 nova-text-label-small text-[var(--ege-muted)]"

export function ModelSelector({
  models,
  selectedModelId,
  onModelChange,
  isLoading,
  error,
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedModel =
    models.find((m) => m.id === selectedModelId) ?? models[0]

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [isOpen])

  if (isLoading) {
    return <span className={LABEL_CLASSES}>Загрузка…</span>
  }

  if (error) {
    return <span className={cn(LABEL_CLASSES, "text-red-400")}>Модель недоступна</span>
  }

  if (models.length === 0) {
    return <span className={LABEL_CLASSES}>Нет моделей</span>
  }

  return (
    <div ref={containerRef} className="relative">
      <Button
        variant="plain"
        size="sm"
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          "flex items-center gap-1 tracking-[-0.8%] text-[var(--ege-muted)]",
        )}
        style={
          isOpen
            ? {
                background: "var(--ege-surface-raised)",
              }
            : undefined
        }
      >
        <span>{selectedModel?.name ?? "Модель"}</span>
        <ChevronDownIcon
          className={cn(
            "transition-transform rotate-180 text-[var(--ege-muted)]",
            isOpen && "rotate-180",
          )}
        />
      </Button>

      {isOpen && (
        <div
          className="absolute bottom-full left-0 mb-1.5 flex min-w-48 flex-col gap-3 rounded-[20px] bg-[var(--ege-surface-raised)] p-2"
          style={{
            border: "1px solid var(--ege-border)",
            backdropFilter: "blur(2px)",
            boxShadow:
              "0px 4px 12px -2px rgba(0,0,0,0.08), 0px 2px 6px -1px rgba(0,0,0,0.04)",
          }}
        >
          {models.map((model: ModelOption) => {
            const isSelected = model.id === selectedModelId;
            return (
              <Button
                variant="plain"
                size="l"
                rounded={false}
                key={model.id}
                type="button"
                onClick={() => {
                  onModelChange(model.id);
                  setIsOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-1 self-stretch text-left",
                  isSelected
                    ? "bg-[var(--ege-surface)] text-[var(--ege-text)]"
                    : "text-[var(--ege-muted)]",
                )}
              >
                <span className="flex-1">{model.name}</span>
                {isSelected && (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                    className="shrink-0"
                  >
                    <path
                      d="M3 8.5L7 12.5L13 3.5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </Button>
            );
          })}
        </div>
      )}
    </div>
  );
}
