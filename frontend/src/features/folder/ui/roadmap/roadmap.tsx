"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  CalendarIcon,
  LessonGenerateIcon,
  LoaderIcon,
  TrashIcon,
} from "@/shared/assets/icons";
import type { ExamOut } from "@/shared/api/generated/model";
import { RoadmapSectionBlock } from "./roadmap-tree";

import {
  createExamApi,
  deleteExamApi,
  getExamsApi,
  updateExamApi,
} from "../../api/exam-api";
import { readCachedExams, writeCachedExams } from "../../model/exams-cache";
import { useLessons } from "../../model/lessons-context";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/popover";
import { Button } from "@/shared/ui";
import { cn } from "@/shared/lib";
import { Calendar } from "@/shared/ui/calendar";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import { BlockInfo, ExamChoose } from "./exam-choose";
import { getOptionalThemesApi, saveOptionalThemesSelectionApi, type OptionalThemesOut } from "../../api/exam-api";

function getDaysLeft(examDate: string): number {
  return Math.ceil((parseISO(examDate).getTime() - Date.now()) / 86400000);
}

function pluralRu(value: number, one: string, few: string, many: string): string {
  const mod10 = Math.abs(value) % 10;
  const mod100 = Math.abs(value) % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

function formatDaysLeft(days: number): string {
  if (days < 0) return "уже прошёл";
  if (days === 0) return "сегодня";
  return `${days} ${pluralRu(days, "день", "дня", "дней")} осталось`;
}

type ExamCardProps = {
  exam: ExamOut;
  onEdit: (exam: ExamOut) => void;
  uneditable?: boolean
}

function ExamCard({ exam, onEdit, uneditable }: ExamCardProps) {
  const daysLeft = getDaysLeft(exam.exam_date);
  const isSystemPaper = exam.user_id === null;
  const editable = !isSystemPaper && !uneditable

  return (
    <div
      className={cn(
        "rounded-[17px] bg-white p-[14px_20px_14px_14px] backdrop-blur-xs transition-colors",
        editable && "group/exam-card cursor-pointer hover:bg-[#F4F0EEA3]",
      )}
      style={{ minWidth: 340 }}
      onClick={editable ? () => onEdit(exam) : undefined}
    >
      <div className="flex items-center gap-3">
        <LessonGenerateIcon
          className={cn(
            "shrink-0 text-[#71717A] transition-opacity",
            editable
              ? "opacity-32 group-hover/exam-card:opacity-100"
              : "opacity-32",
          )}
        />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <span className="min-w-0 truncate nova-text-label-small text-[#242529]">
            {exam.name}
          </span>
          <span className="shrink-0 nova-text-label-small text-[#242529]">
            {exam.progress ?? 0}%
          </span>
        </div>
      </div>
      <div className="ml-10">
        <div className="relative mt-4.5 h-1 w-full rounded-full bg-[#F1ECE98F]">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-[#D2CAC5]"
            style={{ width: `${exam.progress ?? 0}%` }}
          />
        </div>

        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <span className="nova-text-label-small-regular text-[#72706F]">
            {format(parseISO(exam.exam_date), "d MMM yyyy", { locale: ru })}
          </span>
          <span className="shrink-0 nova-text-label-small-regular text-[#72706F]">
            {formatDaysLeft(daysLeft)}
          </span>
        </div>
      </div>
    </div>
  );
}

type ExamCreateProps = {
  selectedCount: number;
  name: string;
  onNameChange: (name: string) => void;
  date: Date | undefined;
  onDateChange: (date: Date | undefined) => void;
  calendarOpen: boolean;
  onCalendarOpenChange: (open: boolean) => void;
  onConfirm?: () => void;
  onCancel?: () => void;
  onDelete?: () => void;
};

function ExamCreate({
  selectedCount,
  name,
  onNameChange,
  date,
  onDateChange,
  onConfirm,
  onCancel,
  onDelete,
  calendarOpen,
  onCalendarOpenChange
}: ExamCreateProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && onConfirm) {
      e.preventDefault();
      onConfirm();
    }
    if (e.key === "Escape" && onCancel) {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <div
      className="rounded-[17px] border border-dashed border-[#E4E4E7] bg-white p-[14px_20px_14px_14px]"
      style={{ minWidth: 340 }}
      onKeyDown={handleKeyDown}
    >
      <div className="flex items-center gap-3">
        <LessonGenerateIcon />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Название экзамена"
            className="min-w-0 flex-1 bg-transparent nova-text-label-small text-[#242529] outline-none placeholder:text-[#72706F]"
          />
          {selectedCount > 0 && (
            <span className="shrink-0 nova-text-label-small text-[#242529]">
              ({selectedCount} {pluralRu(selectedCount, "тема выбрана", "темы выбраны", "тем выбрано")})
            </span>
          )}
        </div>
      </div>
      <div className="mt-2.5 ml-10 flex items-center justify-between gap-2">
        <Popover open={calendarOpen} onOpenChange={onCalendarOpenChange}>
          <PopoverTrigger asChild>
            <Button
              variant="plain"
              className="h-7 w-42.75 cursor-pointer justify-start gap-1 rounded-2xl py-1 pr-2 pl-1.5 nova-text-label-medium text-[#242529] bg-white shadow-[0px_1px_3px_0px_#1C28400A,0px_0px_2px_0px_#1C28402E] transition-colors hover:bg-[#F9F9F9] active:translate-y-px"
            >
              <CalendarIcon />
              {date ? format(date, "d MMM yyyy", { locale: ru }) : <span>Выбрать дату экзамена</span>}
            </Button>
          </PopoverTrigger>
          <PopoverContent
            data-exam-panel
            className="w-auto p-0"
            align="start"
            sideOffset={6}
            onClick={(e) => e.stopPropagation()}
          >
            <Calendar
              mode="single"
              selected={date}
              onSelect={onDateChange}
              defaultMonth={date}
            />
          </PopoverContent>
        </Popover>
        {onDelete && (
          <Button
            iconOnly
            size="sm"
            variant="plain"
            type="button"
            onClick={onDelete}
            className="flex items-center justify-center text-[#72706F] hover:text-[#242529]"
          >
            <TrashIcon className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

type OptionalExam = {
  name: string
  folder_id: string
  exam_date: string
  blocks: BlockInfo[]
}

type ExamMode = { type: "idle" } | { type: "creating" } | { type: "editing"; examId: string };

type ExamsPanelProps = {
  exams: ExamOut[];
  mode: ExamMode;
  selectedCount: number;
  examName: string;
  onExamNameChange: (name: string) => void;
  examDate: Date | undefined;
  onExamDateChange: (date: Date | undefined) => void;
  calendarOpen: boolean;
  onCalendarOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  onStartCreating: () => void;
  onCancel: () => void;
  onEditExam: (exam: ExamOut) => void;
  onDeleteExam: () => void;
  submitting: boolean;
  canConfirm: boolean;
  optionalExam?: OptionalExam
  initialOptionalSelection?: string[]
  onSaveOptionalSelection: (optionIds: string[]) => Promise<void>
};

function ExamsPanel({
  exams,
  mode,
  selectedCount,
  examName,
  onExamNameChange,
  examDate,
  onExamDateChange,
  onConfirm,
  onStartCreating,
  onCancel,
  onEditExam,
  onDeleteExam,
  submitting,
  canConfirm,
  calendarOpen,
  onCalendarOpenChange,
  optionalExam,
  initialOptionalSelection,
  onSaveOptionalSelection
}: ExamsPanelProps) {
  const hasExams = exams.length > 0;
  const isEditing = mode.type !== "idle";

  const formProps = {
    selectedCount,
    name: examName,
    onNameChange: onExamNameChange,
    date: examDate,
    onDateChange: onExamDateChange,
    calendarOpen,
    onCalendarOpenChange,
    onConfirm: canConfirm ? onConfirm : undefined,
    onCancel,
    onDelete:
      mode.type === "editing" &&
        exams.find((e) => e.id === mode.examId)?.user_id != null
        ? onDeleteExam
        : undefined,
  };

  // Detect optional exam by the .929929 microsecond sentinel — works immediately from cache,
  // before optionalThemesData finishes loading.
  const optionalExamId = exams.find(exam =>
    typeof exam.exam_date === 'string' && exam.exam_date.includes('929929')
  )?.id ?? false
  const [open, setOpen] = useState(false)
  const handleSaveExamChoose = async (ids?: string[]) => {
    if (!optionalExam) return
    if (ids) await onSaveOptionalSelection(ids)
    setOpen(false)
  }



  return (
    <div
      data-exam-panel
      className="sticky top-6 z-10 flex w-98 shrink-0 flex-col gap-3 self-start rounded-[17px] border border-[#0000000D] bg-white p-3 shadow-[0px_2px_4px_-2px_#00000005]"
    >
      {optionalExam &&
        <ExamChoose
          key={`${open ? "open" : "closed"}-${initialOptionalSelection?.join("|") ?? "empty"}`}
          isOpen={open}
          onClose={handleSaveExamChoose}
          title={optionalExam.name}
          blocks={optionalExam.blocks}
          submiting={submitting}
          initialSelection={initialOptionalSelection}
        />
      }
      {(hasExams || isEditing) && (
        <div className="flex flex-col gap-3.5">
          {exams.map((exam) =>
            mode.type === "editing" && mode.examId === exam.id ? (
              <ExamCreate key={exam.id} {...formProps} />
            ) : (
              <ExamCard
                key={exam.id}
                exam={exam}
                onEdit={onEditExam}
                uneditable={exam.id === optionalExamId}
              />
            ),
          )}
          {!optionalExamId && optionalExam &&
            <ExamCard
              exam={{
                created_at: "",
                exam_date: optionalExam.exam_date,
                folder_id: optionalExam.folder_id,
                id: optionalExam.name,
                name: optionalExam.name,
                user_id: null
              }}
              onEdit={() => { }}
            />
          }
          {mode.type === "creating" && <ExamCreate {...formProps} />}
          {optionalExam &&
            <Button
              size="l"
              isLoading={!isEditing && submitting}
              disabled={isEditing || (!!optionalExamId && !optionalExam)}
              onClick={() => setOpen(true)}
            >
              {optionalExamId ? "Изменить дополнительные темы" : "Выбрать дополнительные темы"}
            </Button>
          }
          <div className="h-px w-full rounded-full bg-[#F1ECE9]" />
        </div>
      )}
      {isEditing ? (
        <Button
          size="l"
          type="button"
          onClick={onConfirm}
          disabled={!canConfirm || submitting}
          isLoading={submitting}
          className={cn(
            "flex items-center gap-1 self-start tracking-[0px] hover:opacity-80",
            (!canConfirm || submitting) && "cursor-not-allowed",
          )}
        >
          Сохранить
        </Button>
      ) : (
        <Button
          size="l"
          type="button"
          onClick={onStartCreating}
          className="flex items-center gap-1 self-start tracking-[0px] hover:opacity-80"
        >
          Добавить экзамен
        </Button>
      )}
    </div>
  );
}

function ExamCardSkeleton() {
  return (
    <div
      className="rounded-[17px] bg-white p-[14px_20px_14px_14px]"
      style={{ minWidth: 340 }}
    >
      <div className="flex items-center gap-3">
        <div className="h-7 w-7 shrink-0 animate-pulse rounded bg-[#F4F4F5]" />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <div className="h-4 w-32 animate-pulse rounded bg-[#F4F4F5]" />
          <div className="h-4 w-8 shrink-0 animate-pulse rounded bg-[#F4F4F5]" />
        </div>
      </div>
      <div className="ml-10">
        <div className="mt-4.5 h-1 w-full animate-pulse rounded-full bg-[#F4F4F5]" />
        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <div className="h-4 w-20 animate-pulse rounded bg-[#F4F4F5]" />
          <div className="h-4 w-16 shrink-0 animate-pulse rounded bg-[#F4F4F5]" />
        </div>
      </div>
    </div>
  );
}

type RoadmapProps = {
  folderId: string;
};

export function Roadmap({ folderId }: RoadmapProps) {
  const { roadmap, loading } = useLessons();
  const [mode, setMode] = useState<ExamMode>({ type: "idle" });
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [exams, setExams] = useState<ExamOut[]>([]);
  const [examsLoading, setExamsLoading] = useState(true);
  const [examName, setExamName] = useState("");
  const [examDate, setExamDate] = useState<Date>();
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [optionalThemesData, setOptionalThemesData] = useState<OptionalThemesOut | null | undefined>(undefined);

  const OptionalExam = useMemo(() => (
    optionalThemesData
      ? {
        name: optionalThemesData.title,
        folder_id: folderId,
        exam_date: optionalThemesData.exam_date,
        blocks: optionalThemesData.blocks,
      }
      : undefined
  ), [folderId, optionalThemesData]);

  // Derive which block options are currently selected from the saved optional exam
  const currentOptionalSelection = useMemo<string[] | undefined>(() => {
    if (!OptionalExam || !roadmap) return undefined;
    const optExam = exams.find(e => e.exam_date === OptionalExam.exam_date);
    if (!optExam?.roadmap_nodes?.length) return undefined;

    const parentIds = new Set(
      optExam.roadmap_nodes.map(n => n.parent_id).filter((id): id is string => id != null)
    );

    return OptionalExam.blocks.map(block => {
      for (const option of block) {
        if (parentIds.has(option.id)) return option.id;
        // Section option with subsections: check if any subsection is a parent
        const section = roadmap.sections.find(s => s.id === option.id);
        if (section?.subsections.some(sub => parentIds.has(sub.id))) return option.id;
      }
      return "";
    });
  }, [OptionalExam, exams, roadmap]);

  const canConfirm = Boolean(examName.trim()) && !submitting;

  useLayoutEffect(() => {
    const cached = readCachedExams(folderId);
    if (cached !== null) {
      setExams(cached);
      setExamsLoading(false);
    } else {
      setExams([]);
      setExamsLoading(true);
    }
  }, [folderId]);

  useEffect(() => {
    let cancelled = false;
    getExamsApi(folderId).then((res) => {
      if (cancelled) return;
      if (res.status === 200) {
        setExams(res.data);
        writeCachedExams(folderId, res.data);
      }
      setExamsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [folderId]);

  useEffect(() => {
    let cancelled = false;
    getOptionalThemesApi(folderId).then((data) => {
      if (!cancelled) setOptionalThemesData(data);
    });
    return () => {
      cancelled = true;
    };
  }, [folderId]);

  const handleToggleLesson = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleToggleGroup = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const allSelected = ids.every((id) => next.has(id));
      if (allSelected) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

  const resetForm = useCallback(() => {
    setSelectedIds(new Set());
    setExamName("");
    setExamDate(undefined);
    setMode({ type: "idle" });
  }, []);

  const handleStartCreating = useCallback(() => {
    setSelectedIds(new Set());
    setExamName("");
    setExamDate(undefined);
    setMode({ type: "creating" });
  }, []);

  const handleEditExam = useCallback((exam: ExamOut) => {
    const nodeIds = (exam.roadmap_nodes ?? []).map((n) => n.id);
    setMode((prev) => {
      if (prev.type === "editing" && prev.examId === exam.id) return prev;
      return { type: "editing", examId: exam.id };
    });
    setExamName(exam.name);
    setExamDate(parseISO(exam.exam_date));
    setSelectedIds(new Set(nodeIds));
  }, []);

  const handleDeleteExam = useCallback(async () => {
    if (mode.type !== "editing" || submitting) return;
    const examId = mode.examId;
    setSubmitting(true);
    try {
      const res = await deleteExamApi(examId);
      if (res.status === 204) {
        setExams((prev) => {
          const next = prev.filter((e) => e.id !== examId);
          writeCachedExams(folderId, next);
          return next;
        });
        resetForm();
      }
    } finally {
      setSubmitting(false);
    }
  }, [mode, submitting, folderId, resetForm]);

  const handleUpdateExam = useCallback(async (examName: string, selectedIds: Iterable<string> | ArrayLike<string>, mode: ExamMode, examDate?: Date | string) => {
    if (!examName.trim() || submitting) return;

    const payload = {
      folder_id: folderId,
      name: examName.trim(),
      exam_date: typeof examDate === "string" ? examDate : format(examDate ?? new Date(), "yyyy-MM-dd"),
      roadmap_nodes: Array.from(selectedIds),
    };

    setSubmitting(true);
    try {
      if (mode.type === "creating") {
        const res = await createExamApi(payload);
        if (res.status === 201) {
          setExams((prev) => {
            const next = [...prev, res.data];
            writeCachedExams(folderId, next);
            return next;
          });
        }
      } else if (mode.type === "editing") {
        const res = await updateExamApi(mode.examId, payload);
        if (res.status === 200) {
          setExams((prev) => {
            const next = prev.map((e) => (e.id === mode.examId ? res.data : e));
            writeCachedExams(folderId, next);
            return next;
          });
        }
      }
      resetForm();
    } finally {
      setSubmitting(false);
    }
  }, [folderId, submitting, resetForm])

  const handleConfirm = useCallback(async () => {
    handleUpdateExam(examName, selectedIds, mode, examDate)
  }, [examName, examDate, selectedIds, mode, handleUpdateExam]);

  const handleSaveOptionalSelection = useCallback(async (optionIds: string[]) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const ok = await saveOptionalThemesSelectionApi(folderId, optionIds);
      if (ok) {
        const res = await getExamsApi(folderId);
        if (res.status === 200) {
          setExams(res.data);
          writeCachedExams(folderId, res.data);
        }
      }
    } finally {
      setSubmitting(false);
    }
  }, [folderId, submitting]);

  const handleCalendarOpenChange = (open: boolean) => setTimeout(() => setCalendarOpen(open), 100)

  const isEditing = mode.type !== "idle";

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (!isEditing || submitting || calendarOpen) return;
    const target = e.target as HTMLElement;
    if (target.closest("[data-exam-panel]") || target.closest("[data-roadmap-block]") || target.closest("input[type='checkbox']") || target.closest("label")) return;
    resetForm();
  }, [isEditing, submitting, calendarOpen, resetForm]);

  return (
    <div className="mt-6 flex items-start gap-6" onClick={handleBackdropClick}>
      <div className="flex flex-1 flex-col gap-4 items-start">
        {loading ? (
          <div className="flex w-full items-center justify-center py-16">
            <LoaderIcon className="animate-spin" />
          </div>
        ) : !roadmap ? (
          <div className="py-16 text-center nova-text-p-base text-[#71717A] w-full">
            Не получилось загрузить подготовку. Немного позже попробуем ещё раз.
          </div>
        ) : roadmap.sections.length === 0 ? (
          <div className="py-16 text-center nova-text-p-base text-[#71717A] w-full">
            План подготовки пока пустой. Скоро здесь появятся темы.
          </div>
        ) : (
          roadmap.sections.map((section) => (
            <RoadmapSectionBlock
              key={section.id}
              section={section}
              isCreating={isEditing}
              selectedIds={selectedIds}
              onToggleLesson={handleToggleLesson}
              onToggleGroup={handleToggleGroup}
            />
          ))
        )}
      </div>
      {examsLoading ? (
        <div className="sticky top-6 z-10 flex w-98 shrink-0 flex-col gap-3 self-start rounded-[17px] border border-[#0000000D] bg-white p-3 shadow-[0px_2px_4px_-2px_#00000005]">
          <div className="flex flex-col gap-3.5">
            <ExamCardSkeleton />
            <ExamCardSkeleton />
            <ExamCardSkeleton />
            <div className="h-px w-full rounded-full bg-nova-100" />
          </div>
          <div className="h-9 w-21.5 animate-pulse rounded-full bg-[#F4F4F5]" />
        </div>
      ) : (
        <ExamsPanel
          exams={exams}
          mode={mode}
          selectedCount={selectedIds.size}
          examName={examName}
          onExamNameChange={setExamName}
          examDate={examDate}
          calendarOpen={calendarOpen}
          onCalendarOpenChange={handleCalendarOpenChange}
          onExamDateChange={setExamDate}
          onConfirm={handleConfirm}
          onStartCreating={handleStartCreating}
          onCancel={resetForm}
          onEditExam={handleEditExam}
          onDeleteExam={handleDeleteExam}
          submitting={submitting}
          canConfirm={canConfirm}
          optionalExam={OptionalExam}
          initialOptionalSelection={currentOptionalSelection}
          onSaveOptionalSelection={handleSaveOptionalSelection}
        />
      )}
    </div>
  );
}
