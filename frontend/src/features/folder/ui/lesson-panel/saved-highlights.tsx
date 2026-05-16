"use client";

import { memo, useCallback, useEffect, useState } from "react";

import type { ContainerRect } from "./use-lesson-selection";
import { LessonSelectionOverlay } from "./lesson-selection-overlay";
import { LessonSelectionToolbar } from "./lesson-selection-toolbar";
import type { SavedHighlight } from "./use-saved-highlights";

type SavedHighlightsProps = {
  highlights: SavedHighlight[];
  containerRef: React.RefObject<HTMLElement | null>;
  onDelete: (noteId: string) => void;
  onAskNova?: (text: string) => void;
};

function HighlightRects({
  rects,
  hovered,
  onMouseEnter,
  onMouseLeave,
  onClick,
}: {
  rects: ContainerRect[];
  hovered: boolean;
  onMouseEnter: VoidFunction;
  onMouseLeave: VoidFunction;
  onClick: VoidFunction;
}) {
  return (
    <>
      {rects.map((r, i) => (
        <div
          key={i}
          data-highlight-rect=""
          className="absolute rounded-md bg-[#F1ECE9] cursor-pointer"
          style={{
            top: r.top,
            left: r.left - 1,
            width: r.width + 2,
            height: r.height,
            mixBlendMode: "darken",
            opacity: hovered ? 1 : 0.85,
          }}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
          onClick={onClick}
        />
      ))}
    </>
  );
}

function SavedHighlightsInner({
  highlights,
  containerRef,
  onDelete,
  onAskNova,
}: SavedHighlightsProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const handleClick = useCallback((noteId: string) => {
    setActiveId((prev) => (prev === noteId ? null : noteId));
  }, []);

  const handleClearActive = useCallback(() => {
    setActiveId(null);
  }, []);

  useEffect(() => {
    if (!activeId) return;
    const handleClickOutside = (e: MouseEvent) => {
      const toolbar = containerRef.current?.querySelector("[data-selection-toolbar]");
      if (toolbar?.contains(e.target as Node)) return;

      const target = e.target as HTMLElement;
      if (target.closest("[data-highlight-rect]")) return;

      setActiveId(null);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [activeId, containerRef]);

  const handleDelete = useCallback(
    (noteId: string) => {
      setActiveId(null);
      setHoveredId(null);
      onDelete(noteId);
    },
    [onDelete],
  );

  const activeHighlight = highlights.find((h) => h.noteId === activeId);
  const hoveredHighlight =
    !activeId ? highlights.find((h) => h.noteId === hoveredId) : null;

  return (
    <>
      {highlights.map((h) => (
        <HighlightRects
          key={h.noteId}
          rects={h.rects}
          hovered={h.noteId === hoveredId || h.noteId === activeId}
          onMouseEnter={() => setHoveredId(h.noteId)}
          onMouseLeave={() => setHoveredId(null)}
          onClick={() => handleClick(h.noteId)}
        />
      ))}

      {hoveredHighlight && (
        <LessonSelectionOverlay
          selection={{ text: hoveredHighlight.text, range: new Range(), containerRects: hoveredHighlight.rects }}
          handlesOnly
        />
      )}

      {activeHighlight && (
        <>
          <LessonSelectionOverlay
            selection={{ text: activeHighlight.text, range: new Range(), containerRects: activeHighlight.rects }}
            handlesOnly
          />
          <LessonSelectionToolbar
            selection={{ text: activeHighlight.text, range: new Range(), containerRects: activeHighlight.rects }}
            containerRef={containerRef}
            onClear={handleClearActive}
            onAskNova={onAskNova}
            onDelete={() => handleDelete(activeId!)}
            mode="note"
          />
        </>
      )}
    </>
  );
}

export const SavedHighlights = memo(SavedHighlightsInner);
