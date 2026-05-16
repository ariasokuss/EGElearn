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

function pluralizeDays(days: number): string {
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "дня";
  return "дней";
}

function formatDaysLeft(days: number): string {
  if (days < 0) return "экзамен прошел";
  if (days === 0) return "сегодня";
  return `${days} ${pluralizeDays(days)} до экзамена`;
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
        "rounded-[17px] border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-[14px_20px_14px_14px] backdrop-blur-xs transition-colors",
        editable && "group/exam-card cursor-pointer hover:bg-[var(--ege-surface)]",
      )}
      style={{ minWidth: 340 }}
      onClick={editable ? () => onEdit(exam) : undefined}
    >
      <div className="flex items-center gap-3">
        <LessonGenerateIcon
          className={cn(
            "shrink-0 text-[var(--ege-muted)] transition-opacity",
            editable
              ? "opacity-60 group-hover/exam-card:opacity-100"
              : "opacity-60",
          )}
        />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <span className="min-w-0 truncate nova-text-label-small text-[var(--ege-text)]">
            {exam.name}
          </span>
          <span className="shrink-0 nova-text-label-small text-[var(--ege-text)]">
            {exam.progress ?? 0}%
          </span>
        </div>
      </div>
      <div className="ml-10">
        <div className="relative mt-4.5 h-1 w-full rounded-full bg-[var(--ege-track)]">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-[var(--ege-accent)]"
            style={{ width: `${exam.progress ?? 0}%` }}
          />
        </div>

        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <span className="nova-text-label-small-regular text-[var(--ege-muted)]">
            {format(parseISO(exam.exam_date), "d MMM yyyy", { locale: ru })}
          </span>
          <span className="shrink-0 nova-text-label-small-regular text-[var(--ege-muted)]">
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
      className="rounded-[17px] border border-dashed border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-[14px_20px_14px_14px]"
      style={{ minWidth: 340 }}
      onKeyDown={handleKeyDown}
    >
      <div className="flex items-center gap-3">
        <LessonGenerateIcon className="text-[var(--ege-muted)]" />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <input
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Название экзамена"
            className="min-w-0 flex-1 bg-transparent nova-text-label-small text-[var(--ege-text)] outline-none placeholder:text-[var(--ege-muted)]"
          />
          {selectedCount > 0 && (
            <span className="shrink-0 nova-text-label-small text-[var(--ege-text)]">
              ({selectedCount} тем выбрано)
            </span>
          )}
        </div>
      </div>
      <div className="mt-2.5 ml-10 flex items-center justify-between gap-2">
        <Popover open={calendarOpen} onOpenChange={onCalendarOpenChange}>
          <PopoverTrigger asChild>
            <Button
              variant="plain"
              className="h-7 w-42.75 cursor-pointer justify-start gap-1 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface)] py-1 pr-2 pl-1.5 nova-text-label-medium text-[var(--ege-text)] transition-colors hover:bg-[var(--ege-surface-raised)] active:translate-y-px"
            >
              <CalendarIcon />
              {date ? format(date, "d MMM yyyy", { locale: ru }) : <span>Дата экзамена</span>}
            </Button>
          </PopoverTrigger>
          <PopoverContent
            data-exam-panel
            className="w-auto border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-0 text-[var(--ege-text)]"
            align="start"
            sideOffset={6}
            onClick={(e) => e.stopPropagation()}
          >
            <Calendar
              mode="single"
              locale={ru}
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
            className="flex items-center justify-center text-[var(--ege-muted)] hover:text-[var(--ege-text)]"
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
  onUpdateExam: (examName: string, selectedIds: Iterable<string> | ArrayLike<string>, mode: ExamMode, examDate?: Date | string) => Promise<void>
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
  onUpdateExam,
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
      className="sticky top-6 z-10 flex w-98 shrink-0 flex-col gap-3 self-start rounded-[17px] border border-[var(--ege-border)] bg-[var(--ege-surface)] p-3"
    >
      {optionalExam &&
        <ExamChoose
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
              {optionalExamId ? "Изменить темы по выбору" : "Выбрать темы по выбору"}
            </Button>
          }
          <div className="h-px w-full rounded-full bg-[var(--ege-border)]" />
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
      className="rounded-[17px] border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-[14px_20px_14px_14px]"
      style={{ minWidth: 340 }}
    >
      <div className="flex items-center gap-3">
        <div className="h-7 w-7 shrink-0 animate-pulse rounded bg-[var(--ege-track)]" />
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2.5">
          <div className="h-4 w-32 animate-pulse rounded bg-[var(--ege-track)]" />
          <div className="h-4 w-8 shrink-0 animate-pulse rounded bg-[var(--ege-track)]" />
        </div>
      </div>
      <div className="ml-10">
        <div className="mt-4.5 h-1 w-full animate-pulse rounded-full bg-[var(--ege-track)]" />
        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <div className="h-4 w-20 animate-pulse rounded bg-[var(--ege-track)]" />
          <div className="h-4 w-16 shrink-0 animate-pulse rounded bg-[var(--ege-track)]" />
        </div>
      </div>
    </div>
  );
}

function RoadmapEmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex w-full justify-center py-20">
      <div className="max-w-96 rounded-[18px] border border-[var(--ege-border)] bg-[var(--ege-surface)] px-6 py-5 text-center">
        <p className="nova-text-label-base text-[var(--ege-text)]">{title}</p>
        <p className="mt-2 nova-text-p-base text-[var(--ege-muted)]">
          {description}
        </p>
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

  const OptionalExam = optionalThemesData
    ? {
        name: optionalThemesData.title,
        folder_id: folderId,
        exam_date: optionalThemesData.exam_date,
        blocks: optionalThemesData.blocks,
      }
    : undefined;

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
            <LoaderIcon className="animate-spin text-[var(--ege-muted)]" />
          </div>
        ) : !roadmap ? (
          <RoadmapEmptyState
            title="Дорожная карта пока недоступна"
            description="Мы оставили предметы пустыми, чтобы позже наполнить их структурой ФИПИ."
          />
        ) : roadmap.sections.length === 0 ? (
          <RoadmapEmptyState
            title="Дорожная карта пока пустая"
            description="Контент для этого предмета добавим следующим этапом."
          />
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
        <div className="sticky top-6 z-10 flex w-98 shrink-0 flex-col gap-3 self-start rounded-[17px] border border-[var(--ege-border)] bg-[var(--ege-surface)] p-3">
          <div className="flex flex-col gap-3.5">
            <ExamCardSkeleton />
            <ExamCardSkeleton />
            <ExamCardSkeleton />
            <div className="h-px w-full rounded-full bg-[var(--ege-border)]" />
          </div>
          <div className="h-9 w-26 animate-pulse rounded-full bg-[var(--ege-track)]" />
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
          onUpdateExam={handleUpdateExam}
          onSaveOptionalSelection={handleSaveOptionalSelection}
        />
      )}
    </div>
  );
}
