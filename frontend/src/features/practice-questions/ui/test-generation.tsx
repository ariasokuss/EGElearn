"use client"

import { Button } from "@/shared"
import { cn } from "@/shared/lib"

export type GenerationItemProgress = {
  label: string
  requested: number
  ready: number
  status: "pending" | "generating" | "done"
}

type TestGenerationProps = {
  items: GenerationItemProgress[]
  onStartTest?: VoidFunction
  allDone: boolean
}

/**
 * ProgressRing — static arc that fills based on progress (0–1).
 * Beige track (#F1ECE9) + dark fill (#72706F).
 * circumference = 2π × 8.5 ≈ 53.4
 */
const RING_R = 8.5
const RING_C = 2 * Math.PI * RING_R

/**
 * ProgressRing — spinning arc that grows with progress.
 *  - At progress=0: small arc (~15%) spins continuously
 *  - As progress increases: arc grows, still spinning
 *  - At progress=1: full ring, stops spinning → replaced by CheckRing
 */
const MIN_ARC = 0.12 // minimum visible arc when progress=0

function ProgressRing({ progress = 0 }: { progress?: number }) {
  const clamped = Math.min(1, Math.max(0, progress))
  // Arc length: from MIN_ARC (idle) to full circle
  const arcFraction = MIN_ARC + clamped * (1 - MIN_ARC)
  const filled = arcFraction * RING_C

  return (
    <svg
      width="21"
      height="21"
      viewBox="0 0 21 21"
      fill="none"
      className={cn("shrink-0", clamped < 1 && "animate-spin")}
      style={clamped < 1 ? { animationDuration: "1.2s" } : undefined}
    >
      <circle cx="10.5" cy="10.5" r={RING_R} fill="none" stroke="#F1ECE9" strokeWidth="3" />
      <circle
        cx="10.5"
        cy="10.5"
        r={RING_R}
        fill="none"
        stroke="#72706F"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${RING_C - filled}`}
        strokeDashoffset={RING_C * 0.25}
        className="transition-[stroke-dasharray] duration-500 ease-out"
      />
    </svg>
  )
}

/** EmptyRing — also spins with a tiny arc to show "waiting" state */
function EmptyRing() {
  return (
    <svg
      width="21"
      height="21"
      viewBox="0 0 21 21"
      fill="none"
      className="shrink-0 animate-spin"
      style={{ animationDuration: "1.4s" }}
    >
      <circle cx="10.5" cy="10.5" r={RING_R} fill="none" stroke="#F1ECE9" strokeWidth="3" />
      <circle
        cx="10.5"
        cy="10.5"
        r={RING_R}
        fill="none"
        stroke="#72706F"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${MIN_ARC * RING_C} ${(1 - MIN_ARC) * RING_C}`}
        strokeDashoffset={RING_C * 0.25}
      />
    </svg>
  )
}

function CheckRing() {
  return (
    <svg width="21" height="21" viewBox="0 0 21 21" fill="none" className="shrink-0">
      <circle cx="10.5" cy="10.5" r="9.5" fill="#F1ECE9" />
      <path d="M7 10.75L9.5 13.25L14 8.75" stroke="#242529" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function TestGeneration({ items, onStartTest, allDone }: TestGenerationProps) {
  const totalReady = items.reduce((s, i) => s + i.ready, 0);
  const totalRequested = items.reduce((s, i) => s + i.requested, 0)
  const overallProgress = totalRequested > 0 ? totalReady / totalRequested : 0

  return (
    <div className="max-w-md">
      <h2 className="mb-6 nova-text-h-small text-[#242529]">
        Создаём тест
      </h2>

      {/* Main status */}
      <div className="flex items-center gap-3">
        {allDone ? <CheckRing /> : <ProgressRing progress={overallProgress} />}
        <span className="nova-text-label-medium text-[#242529]">
          Генерация теста
        </span>
      </div>

      <div className="relative ml-2.5">
        <div
          className="absolute left-0 top-0 w-px bg-[#E8E5E1]"
          style={{ height: `calc(100% - ${onStartTest ? "auto" : "0px"})` }}
          ref={(el) => {
            if (!el) return
            const parent = el.parentElement
            if (!parent) return
            const itemsContainer = parent.querySelector("[data-items]")
            if (!itemsContainer) return
            const lastItem = itemsContainer.lastElementChild as HTMLElement | null
            if (!lastItem) return
            el.style.height = `${lastItem.offsetTop + lastItem.offsetHeight}px`
          }}
        />

        <div className="space-y-4 pl-7 pt-4" data-items>
          {items.map((item) => {
            const itemProgress = item.requested > 0 ? item.ready / item.requested : 0

            return (
              <div key={item.label} className="flex items-center gap-2.5">
                {/* vertical line ends at last item center — no extra icon */}
                {item.status === "done" ? (
                  <CheckRing />
                ) : item.status === "generating" ? (
                  <ProgressRing progress={itemProgress} />
                ) : (
                  <EmptyRing />
                )}
                <span
                  className={cn(
                    "nova-text-label-small",
                    item.status === "done" ? "text-[#242529]" : "text-[#71717A]",
                  )}
                >
                  {item.label}
                  <span className="ml-1 text-[#A1A1AA]">
                    {item.ready}/{item.requested}
                  </span>
                </span>
              </div>
            )
          })}
        </div>

        {allDone && onStartTest && (
          <div className="pl-7 pt-4">
            <Button
              size="l"
              type="button"
              onClick={onStartTest}
            >
              Начать тест
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
