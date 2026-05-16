"use client"

import { Button } from "@/shared"
import { TestsFolderIconIcon } from "@/shared/assets/icons"

type PracticeEmptyStateProps = {
  onCreateTest: VoidFunction
}

export function PracticeEmptyState({ onCreateTest }: PracticeEmptyStateProps) {
  return (
    <div className="flex items-start justify-center pt-[12%]">
      <div
        className="flex w-full max-w-[706px] shrink-0 flex-col items-start gap-1.5 rounded-[19px] border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-1.5 nova-shadow-sm"
      >
        <div className="flex w-full flex-col items-start justify-center gap-2.5 px-2.5 py-2.5">
          <h2 className="nova-text-h-small-sb text-[var(--ege-text)]">
            Проверь себя
          </h2>
        </div>

        <div
          className="flex w-full flex-1 items-center justify-center gap-3 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface)] px-3.5 pb-6 pt-3.5"
        >
          <div className="flex w-full flex-col items-center gap-4">
            <div className="flex items-center justify-center py-4">
              <TestsFolderIconIcon
                alt="Проверь себя"
                width={155}
                height={118}
                className="pointer-events-none select-none"
              />
            </div>

            <p className="mx-auto max-w-[420px] text-center nova-text-label-small-regular text-[var(--ege-muted)]">
              Закрепи тему на практике и сразу найди места, где стоит повторить материал.
            </p>

            <Button
              type="button"
              onClick={onCreateTest}
              className="flex items-center justify-center gap-1"
            >
              Создать тест
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
