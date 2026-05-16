"use client";

import { useState, useEffect, useCallback } from "react";

export type ContainerRect = {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

export type LessonSelectionState = {
  text: string;
  range: Range;
  containerRects: ContainerRect[];
};

export function useLessonSelection(
  containerRef: React.RefObject<HTMLElement | null>,
) {
  const [selection, setSelection] = useState<LessonSelectionState | null>(null);

  const clearSelection = useCallback(() => {
    window.getSelection()?.removeAllRanges();
    setSelection(null);
  }, []);

  useEffect(() => {
    const handleMouseUp = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.rangeCount) return;

      const range = sel.getRangeAt(0);
      const text = sel.toString().trim();
      if (!text) return;

      const container = containerRef.current;
      if (!container || !container.contains(range.commonAncestorContainer))
        return;

      const containerRect = container.getBoundingClientRect();
      const rawRects = Array.from(range.getClientRects()).filter(
        (r) => r.width > 1,
      );
      if (rawRects.length === 0) return;

      const containerRects = rawRects.map((r) => ({
        top: r.top - containerRect.top + container.scrollTop,
        left: r.left - containerRect.left,
        right: r.right - containerRect.left,
        bottom: r.bottom - containerRect.top + container.scrollTop,
        width: r.width,
        height: r.height,
      }));

      setSelection({ text, range: range.cloneRange(), containerRects });
    };

    document.addEventListener("mouseup", handleMouseUp);
    return () => document.removeEventListener("mouseup", handleMouseUp);
  }, [containerRef]);

  useEffect(() => {
    const handleSelectionChange = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) setSelection(null);
    };

    document.addEventListener("selectionchange", handleSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", handleSelectionChange);
  }, []);

  return { selection, clearSelection };
}
