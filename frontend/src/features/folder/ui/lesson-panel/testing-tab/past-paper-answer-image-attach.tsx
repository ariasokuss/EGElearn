"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AttachmentIcon,
  FileUploadIcon,
  PlusIcon,
  XMarkIcon,
} from "@/shared/assets/icons";
import { cn } from "@/shared/lib";

const MAX_IMAGES = 3;

export type PastPaperAnswerImageAttachProps = {
  files: File[];
  onAddFiles: (files: File[]) => void;
  onRemoveAt: (index: number) => void;
  disabled?: boolean;
};

function filterImageFiles(list: FileList | File[]): File[] {
  const arr = Array.from(list);
  return arr.filter((f) => f.type.startsWith("image/"));
}

export function PastPaperAnswerImageAttach({
  files,
  onAddFiles,
  onRemoveAt,
  disabled = false,
}: PastPaperAnswerImageAttachProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const previewUrls = useMemo(
    () => files.map((f) => URL.createObjectURL(f)),
    [files],
  );

  useEffect(() => {
    return () => {
      previewUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [previewUrls]);

  const hasFiles = files.length > 0;
  const atLimit = files.length >= MAX_IMAGES;

  const openFilePicker = useCallback(() => {
    if (disabled || atLimit) return;
    fileInputRef.current?.click();
  }, [disabled, atLimit]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const picked = e.target.files;
      if (!picked?.length) return;
      const next = filterImageFiles(picked).slice(0, MAX_IMAGES - files.length);
      if (next.length) onAddFiles(next);
      e.target.value = "";
    },
    [onAddFiles, files.length],
  );

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (disabled || atLimit) return;
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(true);
    },
    [disabled, atLimit],
  );

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      if (disabled || atLimit) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "copy";
      setIsDragging(true);
    },
    [disabled, atLimit],
  );

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const next = e.relatedTarget as Node | null;
    if (next && e.currentTarget.contains(next)) return;
    setIsDragging(false);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (disabled || atLimit) return;
      const dt = e.dataTransfer.files;
      if (!dt?.length) return;
      const next = filterImageFiles(dt).slice(0, MAX_IMAGES - files.length);
      if (next.length) onAddFiles(next);
    },
    [disabled, atLimit, onAddFiles, files.length],
  );

  return (
    <div
      className={cn(
        "relative w-full rounded-xl border-2 border-dashed border-[#E8E5E1] bg-white px-4 py-4 transition-colors",
        isDragging && !disabled && "border-[#A1A1AA] bg-[#FAFAF8]",
        disabled && "opacity-60",
      )}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="sr-only"
        onChange={handleInputChange}
        disabled={disabled}
        aria-hidden
        tabIndex={-1}
      />

      <div className="mb-3 flex select-none items-center gap-2">
        <AttachmentIcon
          className="h-4 w-4 shrink-0 text-[#71717A]"
          aria-hidden
        />
        <span className="nova-text-label-small font-semibold text-[#3F3C47]">
          Прикрепить изображение (необязательно)
        </span>
      </div>

      {hasFiles ? (
        <ul className="flex list-none flex-wrap gap-2 p-0">
          {previewUrls.map((src, index) => {
            const f = files[index];
            const thumbKey = f
              ? `${f.name}-${f.lastModified}-${f.size}-${index}`
              : `thumb-${index}`;
            return (
              <li
                key={thumbKey}
                className="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg border border-[#E8E5E1] bg-[#FAFAF8]"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt=""
                  draggable={false}
                  className="h-full w-full object-cover"
                />
                {!disabled ? (
                  <button
                    type="button"
                    onClick={() => onRemoveAt(index)}
                    className="absolute top-0.5 right-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#242529]/80 text-white transition-colors hover:bg-[#242529]"
                    aria-label={`Удалить изображение ${index + 1}`}
                  >
                    <XMarkIcon className="h-3 w-3" aria-hidden />
                  </button>
                ) : null}
              </li>
            );
          })}
          {!disabled && !atLimit ? (
            <li className="h-16 w-16 shrink-0 list-none">
              <button
                type="button"
                onClick={openFilePicker}
                className="flex h-full w-full cursor-pointer select-none flex-col items-center justify-center rounded-lg border border-dashed border-[#E8E5E1] bg-[#FAFAF8] text-[#71717A] transition-colors hover:border-[#C0B8B0] hover:bg-[#F4F2F1] focus-visible:ring-2 focus-visible:ring-[#3F3C47] focus-visible:ring-offset-2 focus-visible:outline-none"
                aria-label="Добавить ещё изображения"
              >
                <PlusIcon className="h-5 w-5" aria-hidden />
              </button>
            </li>
          ) : null}
        </ul>
      ) : (
        <div
          role="button"
          tabIndex={disabled || atLimit ? undefined : 0}
          className={cn(
            "flex cursor-pointer select-none flex-col items-center justify-center rounded-lg px-4 text-center outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[#3F3C47] focus-visible:ring-offset-2",
            "min-h-[118px] py-4",
            !disabled && !atLimit && "hover:bg-[#FAFAF8]/80",
            (disabled || atLimit) && "pointer-events-none cursor-not-allowed",
          )}
          onClick={openFilePicker}
          onKeyDown={(e) => {
            if (disabled) return;
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              openFilePicker();
            }
          }}
          aria-label="Прикрепить изображения: перетащи сюда или выбери файл"
        >
          <FileUploadIcon
            className="h-8 w-8 shrink-0 text-[#71717A]"
            aria-hidden
          />
          <p className="nova-text-label-small font-semibold text-[#242529]">
            Перетащи изображение сюда
          </p>
          <p className="mt-1 nova-text-label-tiny font-normal text-[#71717A]">
            или нажми, чтобы выбрать файл
          </p>
        </div>
      )}

      {isDragging && !disabled ? (
        <div
          className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 rounded-xl bg-[#FAF8F7]/92 px-4 text-center"
          aria-hidden
        >
          <p className="nova-text-label-small font-semibold text-[#242529]">
            Отпусти изображение здесь
          </p>
          <p className="nova-text-label-tiny font-normal text-[#71717A]">
            Оно добавится к твоему ответу
          </p>
        </div>
      ) : null}
    </div>
  );
}
