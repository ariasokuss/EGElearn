"use client"


import type { TestSessionOut } from "@/shared/api/generated/model"
import { PastPaperCardIcon } from "@/shared/assets/icons"
import type { TemplateWithProgress } from "../api"
import { GeneratingTemplateCard } from "./generating-template-card"

type TestHistoryProps = {
  sessions: TestSessionOut[]
  loading: boolean
  onSelect: (session: TestSessionOut) => void
  templates?: TemplateWithProgress[]
  onTemplatesRefresh?: () => void
  onCancelGeneration?: (templateId: string) => void
  onRetryGeneration?: (templateId: string) => void
  onDeleteTemplate?: (templateId: string) => void
  historyName?: string
  /** When true, hide percent and progress bar for not_started / active sessions. */
  hideScoreForIncompleteSessions?: boolean
}

type DateGroup = {
  label: string
  sessions: TestSessionOut[]
}

function groupByDate(sessions: TestSessionOut[]): DateGroup[] {
  const groups: Record<string, { sessions: TestSessionOut[]; newest: number }> = {}

  for (const session of sessions) {
    const created = new Date(session.created_at)
    const label = `${created.toLocaleString("ru-RU", { month: "long" })} ${created.getFullYear()}`

    if (!groups[label]) groups[label] = { sessions: [], newest: 0 }
    groups[label].sessions.push(session)
    const t = created.getTime()
    if (t > groups[label].newest) groups[label].newest = t
  }

  return Object.entries(groups)
    .sort(([, a], [, b]) => b.newest - a.newest)
    .map(([label, { sessions: items }]) => ({
      label,
      sessions: items.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    }))
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getDate()} ${d.toLocaleString("ru-RU", { month: "short" }).toLowerCase().replace(".", "")}`
}

function getStatusLabel(session: TestSessionOut): string {
  if (session.status === "graded" && session.score != null) return "завершён"
  if (session.status === "grading" || session.status === "submitted") return "проверяется..."
  if (session.status === "active") return "в процессе"
  if (session.status === "not_started") return "не начат"
  return "частично завершён"
}

function sessionIsIncompleteForScore(session: TestSessionOut): boolean {
  return session.status === "not_started" || session.status === "active"
}

function TestHistoryCard({
  session,
  onSelect,
  hideScoreForIncompleteSessions,
}: {
  session: TestSessionOut
  onSelect: (session: TestSessionOut) => void
  hideScoreForIncompleteSessions?: boolean
}) {
  const scoreValue = session.score != null ? Math.round(session.score * 100) : 0
  const scoreLabel = `${scoreValue}%`
  const progressWidth = Math.min(100, scoreValue)
  const showScore =
    !hideScoreForIncompleteSessions || !sessionIsIncompleteForScore(session)

  return (
    <button
      type="button"
      onClick={() => onSelect(session)}
      className="group flex w-full flex-col items-start justify-center self-stretch rounded-[16px] border border-[#F4F2F1] hover:border-[#E4DFDD] bg-white py-1.5 pl-1.5 pr-6 text-left transition-colors active:bg-[#FAF8F7] hover:nova-shadow-triple"
    >
      <div className="flex w-full items-center gap-6 self-stretch">
        <div className="shrink-0 self-stretch">
          <PastPaperCardIcon className="shrink-0 **:transition-colors" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <span className="min-w-0 flex-1 truncate nova-text-label-small text-[#242529]">
              {session.template_name || "Тест без названия"}
            </span>
            {showScore ? (
              <span className="shrink-0 nova-text-label-small text-[#242529]">
                {scoreLabel}
              </span>
            ) : null}
          </div>

          {showScore && session.score != null && (
            <div className="mt-4 h-[5px] w-full overflow-hidden rounded-full bg-[#F4F4F5]">
              <div
                className="h-full rounded-full bg-[#E8C9B0] transition-all duration-300"
                style={{ width: `${progressWidth}%` }}
              />
            </div>
          )}

          <div className="mt-2.5 flex items-center justify-between">
            <span className="nova-text-label-small-regular text-[#71717A]">
              {formatDate(session.created_at)}
            </span>
            <span className="nova-text-label-small-regular text-[#71717A]">
              {getStatusLabel(session)}
            </span>
          </div>
        </div>
      </div>
    </button>
  )
}

export function TestHistory({
  sessions,
  loading,
  onSelect,
  templates,
  onTemplatesRefresh,
  onCancelGeneration,
  onRetryGeneration,
  onDeleteTemplate,
  historyName,
  hideScoreForIncompleteSessions,
}: TestHistoryProps) {
  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="flex gap-1.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "0ms" }} />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "150ms" }} />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
    )
  }

  const processingTemplates = (templates ?? []).filter(
    (t) => t.status === "processing" || t.status === "failed",
  )
  const groups = sessions.length > 0 ? groupByDate(sessions) : []

  return (
    <div className="p-4 space-y-4">
      {groups.length === 0 && processingTemplates.length === 0 && (
        <p className="py-8 text-center nova-text-label-small-regular text-[#A1A1AA]">
          Пока нет: <span className="lowercase">{historyName || "история тестов"}</span>
        </p>
      )}

      {processingTemplates.length > 0 && (
        <div className="space-y-4">
          {processingTemplates.map((tpl) => (
            <GeneratingTemplateCard
              key={tpl.id}
              templateId={tpl.id}
              name={tpl.name}
              status={tpl.status}
              initialProgress={tpl.generation_progress}
              errorMessage={tpl.generation_progress?.error ?? null}
              createdAt={tpl.created_at}
              onComplete={() => onTemplatesRefresh?.()}
              onCancel={(id) => onCancelGeneration?.(id)}
              onRetry={(id) => onRetryGeneration?.(id)}
              onDelete={(id) => onDeleteTemplate?.(id)}
            />
          ))}
        </div>
      )}

      {groups.map((group) => (
        <div key={group.label} >
          <p className="mb-2.5 nova-text-label-tiny-sb text-[#242529]">
            {group.label}
          </p>
          <div className="space-y-4">
            {group.sessions.map((session) => (
              <TestHistoryCard
                key={session.id}
                session={session}
                onSelect={onSelect}
                hideScoreForIncompleteSessions={hideScoreForIncompleteSessions}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
