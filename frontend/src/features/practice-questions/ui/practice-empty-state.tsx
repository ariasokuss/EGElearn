"use client"

import { Button } from "@/shared"
import { TestsFolderIconIcon } from "@/shared/assets/icons"

type PracticeEmptyStateProps = {
  onCreateTest: VoidFunction
}

export function PracticeEmptyState({ onCreateTest }: PracticeEmptyStateProps) {
  return (
    <div className="flex items-start justify-center pt-[12%]">
      {/* Card — 706px max, 19px radius, 6px outer padding */}
      <div
        className="flex w-full max-w-[706px] shrink-0 flex-col items-start gap-1.5 rounded-[19px] bg-white p-1.5 border"
        style={{ boxShadow: "0 2px 4px -2px rgba(0, 0, 0, 0.02)", border: "1px solid rgba(228, 228, 231, 0.48)" }}
      >
        {/* Title area */}
        <div className="flex w-full flex-col items-start justify-center gap-2.5 px-2.5 py-2.5">
          <h2 className="nova-text-h-small-sb text-[#242529]">
            Проверь себя!
          </h2>
        </div>

        {/* Inner content container — transparent bg with border, nested inside outer card */}
        <div 
          className="flex w-full flex-1 items-center justify-center gap-3 rounded-2xl border border-[#F4F4F5] bg-white px-3.5 pb-6 pt-3.5"
          style={{ boxShadow: "0 2px 4px -2px rgba(0, 0, 0, 0.02), 0 4px 6px -1px rgba(0, 0, 0, 0.04)" }}
        >
          <div className="flex w-full flex-col items-center gap-4">
            {/* Illustration */}
            <div className="flex items-center justify-center py-4">
              <TestsFolderIconIcon
                alt="Проверь себя"
                width={155}
                height={118}
                className="pointer-events-none select-none"
              />
            </div>

            {/* Description */}
            <p className="mx-auto max-w-[420px] text-center nova-text-label-small-regular text-[#A1A1AA]">
              Давай закрепим пройденный материал на практике.
            </p>

            {/* Create test button — beige pill */}
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
