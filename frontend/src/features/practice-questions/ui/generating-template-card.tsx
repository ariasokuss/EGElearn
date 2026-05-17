"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { PastPaperCardIcon } from "@/shared/assets/icons"
import { streamTemplateProgress } from "../api"
import type { NodeProgress } from "../api"

type GeneratingTemplateCardProps = {
  templateId: string
  name: string
  status: string
  initialProgress: { nodes: Record<string, NodeProgress>; error: string | null } | null
  errorMessage?: string | null
  createdAt: string
  onComplete: () => void
  onCancel: (templateId: string) => void
  onRetry: (templateId: string) => void
  onDelete?: (templateId: string) => void
}

function computeCounts(nodes: Record<string, NodeProgress>): { generated: number; total: number } {
  let generated = 0
  let total = 0
  for (const node of Object.values(nodes)) {
    generated += node.generated
    total += node.total
  }
  return { generated, total }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getDate()} ${d.toLocaleString("en-US", { month: "short" }).toLowerCase()}`
}

export function GeneratingTemplateCard({
  templateId,
  name,
  status,
  initialProgress,
  errorMessage,
  createdAt,
  onComplete,
  onCancel,
  onRetry,
}: GeneratingTemplateCardProps) {
  const [counts, setCounts] = useState(() =>
    initialProgress?.nodes ? computeCounts(initialProgress.nodes) : { generated: 0, total: 0 },
  )
  const [, setError] = useState<string | null>(errorMessage ?? initialProgress?.error ?? null)
  const [currentStatus, setCurrentStatus] = useState(status)
  const [retrying, setRetrying] = useState(false)
  const [hoveringCancel, setHoveringCancel] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const connectSSE = useCallback(() => {
    abortRef.current?.abort()
    const abort = new AbortController()
    abortRef.current = abort

    ;(async () => {
      try {
        for await (const event of streamTemplateProgress(templateId, { signal: abort.signal })) {
          if (abort.signal.aborted) break

          if (event.event === "progress") {
            setCounts(computeCounts(event.nodes))
          } else if (event.event === "complete") {
            setCounts((prev) => ({ ...prev, generated: prev.total }))
            setCurrentStatus("ready")
            onComplete()
            break
          } else if (event.event === "error") {
            setError(event.message)
            setCurrentStatus("failed")
            break
          }
        }
      } catch {
        // Connection lost — don't mark as failed, parent will refresh
      }
    })()
  }, [templateId, onComplete])

  // Auto-retry on failed: trigger regeneration automatically
  useEffect(() => {
    if (currentStatus === "failed" && !retrying) {
      setRetrying(true)
      onRetry(templateId)
    }
  }, [currentStatus, retrying, templateId, onRetry])

  useEffect(() => {
    if (currentStatus === "processing") {
      connectSSE()
    }
    return () => {
      abortRef.current?.abort()
    }
  }, [currentStatus, connectSSE])

  const isProcessing = currentStatus === "processing"

  return (
    <>
      <button
        type="button"
        onClick={undefined}
        className="group flex w-full flex-col items-start justify-center self-stretch rounded-[16px] border border-[#F4F2F1] bg-white py-1.5 pl-1.5 pr-6 text-left"
      >
        <div className="flex w-full items-center gap-6 self-stretch">
          <div
            className="shrink-0 self-stretch"
            style={isProcessing ? { animation: "icon-pulse 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite" } : undefined}
          >
            <PastPaperCardIcon className="shrink-0 **:transition-colors" />
          </div>

          <div className="min-w-0 flex-1">
            <p className="max-w-full truncate nova-text-label-small text-[#242529]">
              {name || "Тест без названия"}
            </p>

            {isProcessing
              ? <div className="mt-2.5 w-16 h-2 bg-[#E4E4E7] rounded-full animate-icon-pulse" />
              : <p className="mt-1 nova-text-label-small-regular text-[#A1A1AA]">не начат</p>
            }

            <div className="mt-3 w-full h-1 rounded-full bg-[#F4F4F5]" />

            <div className="mt-2.5 flex items-center justify-between">
              <span className="nova-text-label-small-regular text-[#71717A]">
                {formatDate(createdAt)}
              </span>

              {isProcessing && (
                <button
                  type="button"
                  onMouseEnter={() => setHoveringCancel(true)}
                  onMouseLeave={() => setHoveringCancel(false)}
                  onClick={(e) => { e.stopPropagation(); onCancel(templateId) }}
                  className="relative nova-text-label-small-regular text-[#71717A]"
                >
                  <span
                    className="inline-block transition-opacity duration-200"
                    style={{ opacity: hoveringCancel ? 0 : 1 }}
                  >
                    {`Создаётся... ${counts.generated}/${counts.total} готово`}
                  </span>
                  <span
                    className="absolute inset-0 flex items-center justify-center transition-opacity duration-200"
                    style={{ opacity: hoveringCancel ? 1 : 0 }}
                  >
                    Отмена
                  </span>
                </button>
              )}
            </div>
          </div>
        </div>
      </button>
    </>
  )
}
