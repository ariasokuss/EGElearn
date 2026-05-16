"use client";

import { memo, useEffect, useRef, useState, useCallback } from "react";

import { TrashIcon, HighlighterIcon, NoteAddIcon, ChatBubbleLeftRightIcon } from "@/shared/assets/icons";

import type { LessonSelectionState } from "./use-lesson-selection";
import { Button } from "@/shared";

type ToolbarProps = {
  selection: LessonSelectionState;
  containerRef: React.RefObject<HTMLElement | null>;
  onClear: VoidFunction;
  onAskNova?: (text: string) => void;
  onMark?: (text: string) => void;
  onNote?: (text: string) => void;
  onDelete?: VoidFunction;
  mode?: "selection" | "note";
};

function Divider() {
  return <div className="h-4 w-px shrink-0 bg-[#E4E4E77A]" />;
}

export const LessonSelectionToolbar = memo(function LessonSelectionToolbar({
  selection,
  containerRef,
  onClear,
  onAskNova,
  onMark,
  onNote,
  onDelete,
  mode = "selection",
}: ToolbarProps) {
  const isNote = mode === "note";
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const computePos = useCallback(() => {
    const container = containerRef.current;
    if (!container) return null;

    const rects = selection.containerRects;
    if (rects.length === 0) return null;

    const minTop = Math.min(...rects.map((r) => r.top));

    const minLeft = Math.min(...rects.map((r) => r.left));
    const maxRight = Math.max(...rects.map((r) => r.right));

    const toolbarWidth = 243;
    let top = minTop - 44 - 8;

    const containerWidth = container.offsetWidth;
    let left = (minLeft + maxRight) / 2 - toolbarWidth / 2;
    left = Math.max(8, Math.min(left, containerWidth - toolbarWidth - 8));

    const minVisibleTop = container.scrollTop + 8;
    if (top < minVisibleTop) {
      const maxBottom = Math.max(...rects.map((r) => r.bottom));
      top = maxBottom + 8;
    }

    return { top, left };
  }, [selection, containerRef]);

  useEffect(() => {
    setPos(computePos());
  }, [computePos]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
  }, []);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(selection.text);
    onClear();
  }, [selection.text, onClear]);

  const handleAskNova = useCallback(() => {
    onAskNova?.(selection.text);
    onClear();
  }, [selection.text, onAskNova, onClear]);

  const handleMark = useCallback(() => {
    onMark?.(selection.text);
    onClear();
  }, [selection.text, onMark, onClear]);

  const handleNote = useCallback(() => {
    onNote?.(selection.text);
    onClear();
  }, [selection.text, onNote, onClear]);

  if (!pos) return null;

  return (
    <div
      ref={toolbarRef}
      data-selection-toolbar=""
      className="pointer-events-auto absolute z-50"
      style={{
        top: pos.top,
        left: pos.left,
        animation: "fade-in 120ms ease-out",
      }}
      onMouseDown={handleMouseDown}
    >
      <div className="flex h-11 items-center gap-1.5 rounded-full border border-[#E4E4E77A] bg-white p-1 backdrop-blur-xs shadow-[0px_4px_6px_-1px_#0000000A,0px_2px_4px_-2px_#00000005]">
        {isNote && (
          <>
            <Button 
              variant="outline"
              iconOnly
              onClick={onDelete}
              aria-label="Удалить заметку"
            >
              <TrashIcon className="size-4" />
            </Button>
            <Divider />
          </>
        )}

        <Button
          variant="outline"
          onClick={handleAskNova}
          className="gap-1"
          aria-label="Ask Nova"
          title="Ask Nova"
        >
          <ChatBubbleLeftRightIcon />
          <span>Ask Nova</span>
        </Button>

        {!isNote && (
          <>
            <Divider />
            <Button
              variant="outline"
              iconOnly
              onClick={handleMark}
              aria-label="Отметить"
            >
              <HighlighterIcon />
            </Button>
          </>
        )}

        {isNote && <Divider />}

        <Button
          variant="outline"
          iconOnly
          onClick={isNote ? handleCopy : handleNote}
          aria-label={isNote ? "Копировать" : "Добавить заметку"}
        >
          <NoteAddIcon />
        </Button>
      </div>
    </div>
  );
});
