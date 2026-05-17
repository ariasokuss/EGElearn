"use client"

import { useState } from "react"

import { CheckboxIcon, CheckedIcon, CheckIcon, RightIcon } from "@/shared/assets/icons"
import { cn } from "@/shared/lib"
import type { RoadmapLessonOut, RoadmapSectionOut, RoadmapSubsectionOut } from "@/shared/api/generated/model"
import { Tippy } from "@/shared/ui"

const CIRCLE_R = 8
const CIRCLE_C = 2 * Math.PI * CIRCLE_R

function ProgressCircle({ percent }: { percent: number }) {
  const offset = CIRCLE_C - (CIRCLE_C * percent) / 100

  return (
    <svg width="21" height="21" viewBox="0 0 21 21" fill="none" className="shrink-0">
      <circle cx="10.5" cy="10.5" r={CIRCLE_R} stroke="#E4E4E7" strokeWidth="3" fill="none" />
      {percent > 0 ? (
        <circle
          cx="10.5"
          cy="10.5"
          r={CIRCLE_R}
          stroke="#A1A1AA"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
          strokeDasharray={CIRCLE_C}
          strokeDashoffset={offset}
          transform="rotate(-90 10.5 10.5)"
        />
      ) : null}
    </svg>
  )
}

export function CheckboxChecked({ className }: { className?: string }) {
  return (
    <div className={cn("relative h-5 w-5 shrink-0", className)}>
      <CheckboxIcon className="absolute inset-0 h-5 w-5" />
      <div className="absolute h-5 w-5 rounded-full bg-[#E8DFD9]" />
      <CheckedIcon className="absolute inset-0 m-auto size-3.5" />
    </div>
  )
}

export function TopicDot({
  isCreating,
  isAllSelected,
  onToggleGroup,
}: {
  isCreating?: boolean
  isAllSelected?: boolean
  onToggleGroup?: () => void
}) {
  if (isCreating) {
    return (
      <button type="button" onClick={onToggleGroup} className="shrink-0 cursor-pointer">
        {isAllSelected ? <CheckboxChecked className="h-5 w-5" /> : <CheckboxIcon className="h-5 w-5" />}
      </button>
    )
  }

  return (
    <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#EEECE7]">
      <div className="h-1.5 w-1.5 rounded-full bg-[#62666D]" />
    </div>
  )
}

export function RoadmapLessonRow({
  lesson,
  isCreating,
  isSelected = false,
  onToggle,
}: {
  lesson: RoadmapLessonOut
  isCreating?: boolean
  isSelected?: boolean
  onToggle?: () => void
}) {
  // mastery engine is the source of truth; legacy progress field is ignored
  const displayPercent = lesson.mastery != null ? Math.round(lesson.mastery) : 0
  const isDone = displayPercent >= 100
  if (isCreating) {
    return (
      <div className="flex cursor-pointer items-center gap-2.5 px-4 py-2.5" onClick={onToggle}>
        {isSelected ? <CheckboxChecked className="h-5 w-5 shrink-0" /> : <CheckboxIcon className="h-5 w-5 shrink-0" />}
        <span className="flex-1 nova-text-p-medium text-[#8A8F98]">{lesson.name}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between gap-2 pl-4 pr-1.5 rounded-full hover:bg-[#F1ECE9CC]">
      <span className="flex-1 nova-text-p-medium text-[#8A8F98] py-2.5">
        {lesson.name}
      </span>
      <Tippy
        content="Насколько уверенно ты знаешь эту тему по урокам, объяснениям и тестам. Чем больше практики, тем крепче результат."
      >
        <div className="flex shrink-0 items-center gap-3 p-2.5">
          <span className="nova-text-label-small text-[#242529]">
            {displayPercent}%
          </span>
          {isDone ? <CheckIcon /> : <ProgressCircle percent={displayPercent} />}
        </div>
      </Tippy>
    </div>
  );
}

const BLOCK_CLASS =
  "group/block min-w-[431px] max-w-[596px] rounded-[14px] py-2 pr-2 pl-1 transition-colors hover:bg-[#F1ECE985]";

export function RoadmapSubsectionBlock({
  subsection,
  isLast,
  isCreating,
  selectedIds,
  onToggleLesson,
  onToggleGroup,
}: {
  subsection: RoadmapSubsectionOut
  isLast: boolean
  isCreating: boolean
  selectedIds: Set<string>
  onToggleLesson: (id: string) => void
  onToggleGroup: (ids: string[]) => void
}) {
  const [isOpen, setIsOpen] = useState(true)
  const lessonIds = subsection.lessons.map((l) => l.id)
  const isAllSelected = lessonIds.length > 0 && lessonIds.every((id) => selectedIds.has(id))

  return (
    <div className={cn(BLOCK_CLASS, "relative")}>
      {!isLast && (
        <div
          className="absolute w-px bg-[#F1ECE9]"
          style={{ left: 46, top: 42, height: "calc(100% - 30px)" }}
        />
      )}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setIsOpen((v) => !v)}
          className="flex h-7 w-7 shrink-0 items-center justify-center opacity-0 transition-[opacity,transform] duration-300 group-hover/block:opacity-100"
        >
          <RightIcon className={cn("transition-transform duration-300", isOpen && "rotate-90")} />
        </button>
        <div className="flex items-center gap-1.5">
          <TopicDot isCreating={isCreating} isAllSelected={isAllSelected} onToggleGroup={() => onToggleGroup(lessonIds)} />
          <h3 className="nova-text-label-medium text-[#242529]">{subsection.name}</h3>
        </div>
      </div>
      {isOpen && (
        <div className="mt-2 flex flex-col pl-[54px]">
          {subsection.lessons.map((lesson) => (
            <RoadmapLessonRow
              key={lesson.id}
              lesson={lesson}
              isCreating={isCreating}
              isSelected={selectedIds.has(lesson.id)}
              onToggle={() => onToggleLesson(lesson.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function RoadmapSectionBlock({
  section,
  isCreating,
  selectedIds,
  onToggleLesson,
  onToggleGroup,
}: {
  section: RoadmapSectionOut
  isCreating: boolean
  selectedIds: Set<string>
  onToggleLesson: (id: string) => void
  onToggleGroup: (ids: string[]) => void
}) {
  const [isOpen, setIsOpen] = useState(true)
  const hasSubsections = section.subsections.length > 0
  const allLessonIds = [
    ...section.lessons.map((l) => l.id),
    ...section.subsections.flatMap((ss) => ss.lessons.map((l) => l.id)),
  ]
  const isAllSelected = allLessonIds.length > 0 && allLessonIds.every((id) => selectedIds.has(id))

  return (
    <div data-roadmap-block className="relative flex flex-col gap-3 cursor-default">
      <div
        className="absolute w-px bg-[#F1ECE9]"
        style={{ left: 46, top: 42, height: "calc(100% - 26px)" }}
      />
      <div className={BLOCK_CLASS}>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setIsOpen((v) => !v)}
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center opacity-0 transition-[opacity,transform] duration-300 group-hover/block:opacity-100",
              !hasSubsections && section.lessons.length === 0 && "invisible",
            )}
          >
            <RightIcon className={cn("transition-transform duration-300", isOpen && "rotate-90")} />
          </button>
          <div className="flex items-center gap-1.5">
            <TopicDot isCreating={isCreating} isAllSelected={isAllSelected} onToggleGroup={() => onToggleGroup(allLessonIds)} />
            <h2 className="nova-text-label-medium text-[#242529]">{section.name}</h2>
          </div>
        </div>
        {section.lessons.length > 0 && isOpen && (
          <div className="mt-2 flex flex-col pl-12.5">
            {section.lessons.map((lesson) => (
              <RoadmapLessonRow
                key={lesson.id}
                lesson={lesson}
                isCreating={isCreating}
                isSelected={selectedIds.has(lesson.id)}
                onToggle={() => onToggleLesson(lesson.id)}
              />
            ))}
          </div>
        )}
      </div>
      {hasSubsections && isOpen && (
        <div className="ml-[62px] flex flex-col gap-3">
          {section.subsections.map((sub, index) => (
            <RoadmapSubsectionBlock
              key={sub.id}
              subsection={sub}
              isLast={index === section.subsections.length - 1}
              isCreating={isCreating}
              selectedIds={selectedIds}
              onToggleLesson={onToggleLesson}
              onToggleGroup={onToggleGroup}
            />
          ))}
        </div>
      )}
    </div>
  )
}
