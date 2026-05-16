"use client"

import { cn } from "@/shared/lib"
import type { TestMode } from "../lib";
import { Button } from "@/shared";

type QuestionsSetupProps = {
  questionCounts: Record<string, number>
  onCountChange: (type: string, count: number) => void
  mode: TestMode
  onModeChange: (mode: TestMode) => void
  loading?: boolean
}

function CounterRow({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="nova-text-p-medium text-[var(--ege-muted)]">
        {label}
      </span>
      <div className="flex items-center gap-3 ml-3">
        <Button
          iconOnly
          size="xs"
          variant="plain"
          type="button"
          onClick={() => onChange(Math.max(0, value - 1))}
          className="flex items-center justify-center text-[var(--ege-muted)]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3.33337 8H12.6667" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Button>
        <span className="w-4 text-center nova-text-label-small text-[var(--ege-text)]">
          {value}
        </span>
        <Button
          iconOnly
          size="xs"
          variant="plain"
          type="button"
          onClick={() => onChange(value + 1)}
          className="flex items-center justify-center text-[var(--ege-muted)]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8.62415 3.62415C8.62415 3.2789 8.34427 2.99902 7.99902 2.99902C7.65378 2.99902 7.3739 3.2789 7.3739 3.62415V7.37488H3.62317C3.27792 7.37488 2.99805 7.65475 2.99805 8C2.99805 8.34525 3.27792 8.62512 3.62317 8.62512L7.3739 8.62512V12.3759C7.3739 12.7211 7.65378 13.001 7.99902 13.001C8.34427 13.001 8.62415 12.7211 8.62415 12.3759V8.62512L12.3749 8.62512C12.7201 8.62512 13 8.34525 13 8C13 7.65476 12.7201 7.37488 12.3749 7.37488H8.62415V3.62415Z" fill="currentColor" />
          </svg>
        </Button>
      </div>
    </div>
  )
}

function ModeOption({
  title,
  description,
  selected,
  onSelect,
}: {
  title: string;
  description: string;
  selected: boolean;
  onSelect: VoidFunction;
}) {
  return (
    <div
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg py-2 transition-colors",
      )}
      onClick={onSelect}
    >
      <div
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[10px] border transition-colors",
          selected
            ? "border-[var(--ege-accent)] bg-[var(--ege-accent)] text-white"
            : "border-[var(--ege-border)] bg-transparent text-[var(--ege-muted)] hover:bg-[var(--ege-surface)]",
        )}
      >
        {selected && (
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <path d="M3 8.5L6 11.5L13 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
      <div>
        <p className="nova-text-label-small text-[var(--ege-text)]">
          {title}
        </p>
        <p className="nova-text-label-small text-[var(--ege-muted)]">
          {description}
        </p>
      </div>
    </div>
  )
}

export function QuestionsSetup({
  questionCounts,
  onCountChange,
  mode,
  onModeChange,
  loading,
}: QuestionsSetupProps) {
  const total = Object.values(questionCounts).reduce((sum, n) => sum + n, 0)

  if (loading) {
    return (
      <div className="max-w-sm">
        <h2 className="mb-4 nova-text-h-tiny text-[var(--ege-text)]">
          Загружаем типы вопросов...
        </h2>
      </div>
    )
  }

  if (Object.keys(questionCounts).length === 0) {
    return (
      <div className="max-w-sm">
        <h2 className="mb-4 nova-text-h-tiny text-[var(--ege-text)]">
          Для этого предмета пока нет типов вопросов
        </h2>
      </div>
    )
  }

  return (
    <div className="max-w-sm">
      <h2 className="mb-4 nova-text-h-tiny text-[var(--ege-text)]">
        Выбери типы вопросов
      </h2>

      <div className="space-y-0.5">
        {Object.entries(questionCounts).map(([type, count]) => (
          <CounterRow
            key={type}
            label={type}
            value={count}
            onChange={(v) => onCountChange(type, v)}
          />
        ))}
      </div>

      {/* Total */}
      <div
        className="mt-2 flex max-w-[200px] items-center gap-2.5 rounded-full border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] py-2 pr-4 pl-2.5 opacity-80"
        style={{
          boxShadow: "0 2px 4px -2px rgba(0,0,0,0.02), 0 4px 6px -1px rgba(0,0,0,0.04)",
          backdropFilter: "blur(4px)",
        }}
      >
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[10px] border border-[var(--ege-accent)] bg-[var(--ege-accent)] text-white">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <path d="M3 8.5L6 11.5L13 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <span className="nova-text-label-small text-[var(--ege-text)]">
          Всего: {total}
        </span>
      </div>
      <div className="mt-[25px] h-px w-full bg-[var(--ege-border)]" />

      <div className="mt-[20px]">
        <h3 className="mb-3 nova-text-label-base text-[var(--ege-text)]">
          Выбери режим
        </h3>

        <ModeOption
          title="Режим тренировки"
          description="Можно просить подсказки и проверять ответы по одному"
          selected={mode === "practice"}
          onSelect={() => onModeChange("practice")}
        />
        <ModeOption
          title="Режим экзамена"
          description="Без подсказок, результаты только в конце"
          selected={mode === "exam"}
          onSelect={() => onModeChange("exam")}
        />
      </div>
    </div>
  )
}
