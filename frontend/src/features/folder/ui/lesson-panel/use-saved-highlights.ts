"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Note } from "../../model/notes-context";
import type { ContainerRect } from "./use-lesson-selection";

export type SavedHighlight = {
  noteId: string;
  text: string;
  rects: ContainerRect[];
};

/** Collapse runs of whitespace (including newlines) into a single space. */
function normalizeWS(s: string): string {
  return s.replace(/\s+/g, " ");
}

export function findTextRange(
  container: HTMLElement,
  searchText: string,
): Range | null {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const textNodes: { node: Text; start: number }[] = [];
  let fullText = "";

  let current = walker.nextNode() as Text | null;
  while (current) {
    textNodes.push({ node: current, start: fullText.length });
    fullText += current.textContent ?? "";
    fullText += " ";
    current = walker.nextNode() as Text | null;
  }

  // Normalize whitespace so selections spanning line breaks still match
  const normSearch = normalizeWS(searchText);
  const normFull = normalizeWS(fullText);
  const normStart = normFull.indexOf(normSearch);
  if (normStart === -1) return null;

  // Map normalized offset back to original fullText offset
  let normIdx = 0;
  let origIdx = 0;
  while (normIdx < normStart && origIdx < fullText.length) {
    if (/\s/.test(fullText[origIdx])) {
      // consume all original whitespace chars that collapsed into one normalized space
      while (origIdx < fullText.length && /\s/.test(fullText[origIdx])) origIdx++;
      normIdx++; // the single space in normalized string
    } else {
      origIdx++;
      normIdx++;
    }
  }
  const matchStart = origIdx;

  // Advance through the matched length in normalized space to find original end
  const normEnd = normStart + normSearch.length;
  while (normIdx < normEnd && origIdx < fullText.length) {
    if (/\s/.test(fullText[origIdx])) {
      while (origIdx < fullText.length && /\s/.test(fullText[origIdx])) origIdx++;
      normIdx++;
    } else {
      origIdx++;
      normIdx++;
    }
  }
  const matchEnd = origIdx;

  let startNode: Text | null = null;
  let startOffset = 0;
  let endNode: Text | null = null;
  let endOffset = 0;

  for (const { node, start } of textNodes) {
    const nodeLen = node.textContent?.length ?? 0;
    const nodeEnd = start + nodeLen;

    if (!startNode && nodeEnd > matchStart) {
      startNode = node;
      startOffset = matchStart - start;
    }
    if (nodeEnd >= matchEnd) {
      endNode = node;
      endOffset = matchEnd - start;
      break;
    }
  }

  if (!startNode || !endNode) return null;

  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  return range;
}

function computeContainerRects(
  range: Range,
  container: HTMLElement,
): ContainerRect[] {
  const containerRect = container.getBoundingClientRect();
  return Array.from(range.getClientRects())
    .filter((r) => r.width > 1)
    .map((r) => ({
      top: r.top - containerRect.top + container.scrollTop,
      left: r.left - containerRect.left,
      right: r.right - containerRect.left,
      bottom: r.bottom - containerRect.top + container.scrollTop,
      width: r.width,
      height: r.height,
    }));
}

export function useSavedHighlights(
  containerRef: React.RefObject<HTMLElement | null>,
  notes: Note[],
  loading: boolean,
  contentVersion: number,
) {
  const [highlights, setHighlights] = useState<SavedHighlight[]>([]);
  const lastWidthRef = useRef(0);
  const resizeRafRef = useRef(0);
  const notesRef = useRef(notes);

  useEffect(() => {
    notesRef.current = notes;
  }, [notes]);

  const recalculate = useCallback(() => {
    const container = containerRef.current;
    const currentNotes = notesRef.current;
    if (!container || currentNotes.length === 0) {
      setHighlights([]);
      return;
    }

    // Temporarily disable content-visibility: auto on lesson blocks so that
    // off-screen text nodes are rendered and getClientRects() returns real rects.
    const blocks = container.querySelectorAll<HTMLElement>("[data-block-id]");
    const saved: string[] = [];
    blocks.forEach((el) => {
      saved.push(el.style.contentVisibility);
      el.style.contentVisibility = "visible";
    });

    const result: SavedHighlight[] = [];
    for (const note of currentNotes) {
      const range = findTextRange(container, note.text);
      if (!range) continue;
      const rects = computeContainerRects(range, container);
      if (rects.length > 0) {
        result.push({ noteId: note.id, text: note.text, rects });
      }
    }

    // Restore original content-visibility values
    blocks.forEach((el, i) => {
      el.style.contentVisibility = saved[i];
    });

    setHighlights(result);
  }, [containerRef]);

  useEffect(() => {
    const container = containerRef.current;
    if (loading) {
      queueMicrotask(() => {
        setHighlights([]);
      });
      return;
    }
    if (notes.length === 0 || !container) return;

    const rafId = requestAnimationFrame(() => {
      recalculate();
      lastWidthRef.current = container.offsetWidth;
    });

    return () => cancelAnimationFrame(rafId);
  }, [containerRef, notes, loading, contentVersion, recalculate]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || loading) return;

    const observer = new ResizeObserver(() => {
      const newWidth = container.offsetWidth;
      if (newWidth === lastWidthRef.current) return;
      lastWidthRef.current = newWidth;
      cancelAnimationFrame(resizeRafRef.current);
      resizeRafRef.current = requestAnimationFrame(recalculate);
    });

    observer.observe(container);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(resizeRafRef.current);
    };
  }, [containerRef, loading, recalculate]);

  const noteIds = useMemo(() => new Set(notes.map((n) => n.id)), [notes]);

  return useMemo(
    () => highlights.filter((h) => noteIds.has(h.noteId)),
    [highlights, noteIds],
  );
}
