"use client";

import { useEffect, useMemo, useState } from "react";

import { AcademicCapIcon, LoaderIcon, StarsIcon } from "@/shared/assets/icons";
import { cn } from "@/shared/lib";
import type {
  LessonListSchema,
  RoadmapLessonOut,
  RoadmapSectionOut,
  RoadmapSubsectionOut,
} from "@/shared/api/generated/model";

import { getLastAccessedLessonsApi } from "../../api/lessons-api";
import { lessonStepDisplayFlags, useLessons } from "../../model/lessons-context";

function pickUpToNNeededLessonsInFolder(
  byAccessOrder: LessonListSchema[],
  lessonMap: Record<string, { lesson: RoadmapLessonOut }>,
  n: number,
): RoadmapLessonOut[] {
  const out: RoadmapLessonOut[] = [];
  for (const item of byAccessOrder) {
    if (out.length >= n) break;
    const fromKey = lessonMap[item.id];
    const fromScan =
      fromKey ??
      Object.values(lessonMap).find(
        (e) => e.lesson.lesson_id === item.id || e.lesson.id === item.id,
      );
    if (fromScan) out.push(fromScan.lesson);
  }
  return out;
}

function sameRoadmapLesson(a: RoadmapLessonOut, b: RoadmapLessonOut): boolean {
  if (a.id === b.id) return true;
  if (a.lesson_id != null && b.lesson_id != null && a.lesson_id === b.lesson_id) {
    return true;
  }
  return false;
}

/**
 * Surfaces the open lesson first in the strip. The list from GET /last-accessed may still be one
 * request behind right after open; `lastAccessedRefreshNonce` schedules a refetch after a short delay.
 */
function mergeSelectedLessonFirst(
  fromApi: RoadmapLessonOut[],
  lessonMap: Record<string, { lesson: RoadmapLessonOut }>,
  selectedRoadmapNodeId: string | null | undefined,
  max: number,
): RoadmapLessonOut[] {
  if (!selectedRoadmapNodeId) return fromApi.slice(0, max);
  const entry = Object.values(lessonMap).find(
    (e) =>
      e.lesson.id === selectedRoadmapNodeId ||
      e.lesson.lesson_id === selectedRoadmapNodeId,
  );
  if (!entry) return fromApi.slice(0, max);
  const cur = entry.lesson;
  const rest = fromApi.filter((l) => !sameRoadmapLesson(l, cur));
  return [cur, ...rest].slice(0, max);
}

const LAST_ACCESSED_COUNT = 3;
const LAST_ACCESSED_REFETCH_DELAY_MS = 450;

type Variant = "grid" | "list";

type LastAccessedBlockProps = {
  folderId: string;
  selectedLessonId?: string | null;
  onSelect?: (id: string) => void;
  variant: Variant;
  lastAccessedRefreshNonce: number;
};

function LastAccessedLessonsBlock({
  folderId,
  selectedLessonId,
  onSelect,
  variant,
  lastAccessedRefreshNonce,
}: LastAccessedBlockProps) {
  const { lessonMap } = useLessons();
  const [lastAccessed, setLastAccessed] = useState<{
    folderId: string | null;
    fetched: boolean;
    order: LessonListSchema[];
  }>({
    folderId: null,
    fetched: false,
    order: [],
  });
  const fetched = lastAccessed.folderId === folderId && lastAccessed.fetched;

  useEffect(() => {
    let cancelled = false;
    getLastAccessedLessonsApi(folderId)
      .then((rows) => {
        if (cancelled) return;
        setLastAccessed({ folderId, fetched: true, order: rows });
      })
      .catch(() => {
        if (cancelled) return;
        setLastAccessed({ folderId, fetched: true, order: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [folderId]);

  useEffect(() => {
    if (lastAccessedRefreshNonce === 0) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      getLastAccessedLessonsApi(folderId)
        .then((rows) => {
          if (cancelled) return;
          setLastAccessed({ folderId, fetched: true, order: rows });
        })
        .catch(() => {
          if (cancelled) return;
          setLastAccessed({ folderId, fetched: true, order: [] });
        });
    }, LAST_ACCESSED_REFETCH_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [folderId, lastAccessedRefreshNonce]);

  const lessons = useMemo(() => {
    const order = fetched ? lastAccessed.order : [];
    const fromApi = pickUpToNNeededLessonsInFolder(
      order,
      lessonMap,
      LAST_ACCESSED_COUNT,
    );
    return mergeSelectedLessonFirst(
      fromApi,
      lessonMap,
      selectedLessonId,
      LAST_ACCESSED_COUNT,
    );
  }, [fetched, lastAccessed.order, lessonMap, selectedLessonId]);

  const gridClass = variant === "list" ? "flex flex-col gap-3" : "grid grid-cols-3 gap-3";

  return (
    <div>
      <h2 className="mb-[10px] nova-text-label-base text-[#1D1B20]">
        Last Accessed Lessons
      </h2>
      {!fetched ? (
        <div className="flex min-h-[100px] items-center justify-center">
          <LoaderIcon className="size-5 animate-spin text-[#71717A]" />
        </div>
      ) : lessons.length > 0 ? (
        <div className={gridClass}>
          {lessons.map((lesson) => (
            <LessonCard
              key={lesson.id}
              lesson={lesson}
              isSelected={selectedLessonId === lesson.id}
              onSelect={onSelect}
              variant={variant}
            />
          ))}
        </div>
      ) : (
        <div className="flex min-h-[140px] w-full items-center justify-center rounded-xl border border-[#E8E5E1] bg-white px-6 py-10">
          <p className="max-w-md text-center text-pretty nova-text-p-base text-[#71717A]">
            Recently visited lessons will appear here for quick access.
            <br />
            Start exploring your first lesson today!
          </p>
        </div>
      )}
    </div>
  );
}

type LessonsProps = {
  folderId: string;
  selectedLessonId?: string | null;
  onLessonClick?: (id: string) => void;
  variant?: Variant;
  lastAccessedRefreshNonce: number;
};



type LessonCardProps = {
  lesson: RoadmapLessonOut;
  isSelected?: boolean;
  onSelect?: (id: string) => void;
  variant?: Variant;
};

function LessonCard({ lesson, isSelected, onSelect, variant = "grid" }: LessonCardProps) {
  const { lessonMap, stepStatus } = useLessons()
  const detail =
    lesson.lesson_id != null && lesson.lesson_id !== ""
      ? (lessonMap[lesson.lesson_id]?.detail ?? null)
      : null;
  const fromRoadmap = lesson.description?.trim() ?? "";
  const fromLessonList = detail?.description?.trim() ?? "";
  const description = fromRoadmap || fromLessonList || null;
  const lessonId = lesson.lesson_id ?? "";
  const displayLesson =
    lessonId && lessonMap[lessonId] ? lessonMap[lessonId].lesson : lesson;
  const st = lessonId ? stepStatus[lessonId] : undefined;
  const starSteps = lessonStepDisplayFlags(displayLesson, st);

  return (
    <div
      onClick={() => onSelect?.(lesson.lesson_id ?? "")}
      className={cn(
        "flex h-22.5 items-center rounded-2xl p-4 transition-shadow duration-300 ease-out cursor-pointer active:bg-[#F1ECE9A3] active:shadow-none active:[transition:none]",
        variant === "grid" && "border border-[#F4F4F5] hover:shadow-[0px_2px_4px_0px_#1C28400F,0px_1px_2px_-1px_#1C28401A,0px_0px_0px_4px_#E8E5E138]",
        variant === "list" && "hover:bg-[#F1ECE9A3]",
        isSelected && "bg-[#F1ECE9A3] shadow-none",
        isSelected && variant === "grid" && "border-[#E8DFD9]"
      )}
    >
      <div className="flex shrink-0 flex-col items-center justify-center gap-1 pr-2" style={{ width: 42 }}>
        <div className="flex h-7 w-7 items-center justify-center">
          <AcademicCapIcon />
        </div>
        <StarsIcon steps={starSteps} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
        <span className="truncate nova-text-label-small text-[#242529]">
          {lesson.name}
        </span>
        {description ? (
          <span className="line-clamp-1 nova-text-label-small-regular text-[#72706F]">
            {description.replace(/^[# ]+/, "")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function SectionDivider() {
  return (
    <div className="my-[10px] px-2">
      <div className="h-px w-full rounded-full bg-[#F4F4F5]" />
    </div>
  );
}

type SubsectionGroupProps = {
  subsection: RoadmapSubsectionOut;
  isLast: boolean;
  selectedLessonId?: string | null;
  onSelect?: (id: string) => void;
  variant?: Variant;
};

function SubsectionGroup({ subsection, isLast, selectedLessonId, onSelect, variant = "grid" }: SubsectionGroupProps) {
  return (
    <>
      <div className="pt-[6px] pb-[16px]">
        <p className="mb-3 nova-text-p-base text-[#71717A]">
          {subsection.name}
        </p>
        <div className={variant === "list" ? "flex flex-col gap-3" : "grid grid-cols-3 gap-3"}>
          {subsection.lessons.map((lesson) => (
            <LessonCard
              key={lesson.id}
              lesson={lesson}
              isSelected={selectedLessonId === lesson.id}
              onSelect={onSelect}
              variant={variant}
            />
          ))}
        </div>
      </div>
      {!isLast && <SectionDivider />}
    </>
  );
}

type ThemeBlockProps = {
  section: RoadmapSectionOut;
  selectedLessonId?: string | null;
  onSelect?: (id: string) => void;
  variant?: Variant;
};

function ThemeBlock({ section, selectedLessonId, onSelect, variant = "grid" }: ThemeBlockProps) {
  const hasSubsections = section.subsections.length > 0;
  const hasDirectLessons = section.lessons.length > 0;
  const lessonContainer = variant === "list" ? "flex flex-col gap-3" : "grid grid-cols-3 gap-3";

  return (
    <div>
      <h2 className="mb-[10px] nova-text-label-base text-[#1D1B20]">
        {section.name}
      </h2>

      {hasSubsections && (
        <>
          {hasDirectLessons && (
            <>
              <div className="pb-[16px]">
                <div className={lessonContainer}>
                  {section.lessons.map((lesson) => (
                    <LessonCard
                      key={lesson.id}
                      lesson={lesson}
                      isSelected={selectedLessonId === lesson.id}
                      onSelect={onSelect}
                      variant={variant}
                    />
                  ))}
                </div>
              </div>
              <SectionDivider />
            </>
          )}
          {section.subsections.map((sub, index) => (
            <SubsectionGroup
              key={sub.id}
              subsection={sub}
              isLast={index === section.subsections.length - 1}
              selectedLessonId={selectedLessonId}
              onSelect={onSelect}
              variant={variant}
            />
          ))}
        </>
      )}

      {!hasSubsections && hasDirectLessons && (
        <div className="pb-[16px]">
          <div className={lessonContainer}>
            {section.lessons.map((lesson) => (
              <LessonCard
                key={lesson.id}
                lesson={lesson}
                isSelected={selectedLessonId === lesson.id}
                onSelect={onSelect}
                variant={variant}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function Lessons({
  folderId,
  selectedLessonId,
  onLessonClick,
  variant = "grid",
  lastAccessedRefreshNonce,
}: LessonsProps) {
  const { loading, roadmap } = useLessons()

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoaderIcon className="animate-spin" />
      </div>
    );
  }

  if (!roadmap) {
    return (
      <div className="py-16 text-center nova-text-p-base text-[#71717A]">
        Failed to load lessons.
      </div>
    );
  }

  if (roadmap.sections.length === 0) {
    return (
      <div className="py-16 text-center nova-text-p-base text-[#71717A]">
        No lessons available for this folder yet.
      </div>
    );
  }

  return (
    <div className="mt-6 flex flex-col gap-6">
      <LastAccessedLessonsBlock
        key={folderId}
        folderId={folderId}
        selectedLessonId={selectedLessonId}
        lastAccessedRefreshNonce={lastAccessedRefreshNonce}
        onSelect={onLessonClick}
        variant={variant}
      />
      <SectionDivider />
      {roadmap.sections.map((section) => (
        <ThemeBlock
          key={section.id}
          section={section}
          selectedLessonId={selectedLessonId}
          onSelect={onLessonClick}
          variant={variant}
        />
      ))}
    </div>
  );
}
