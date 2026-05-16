"use client";

import { useState, useCallback, useRef, useEffect } from "react";

const DEFAULT_STORAGE_KEY = "novalearn:panel-width";

type UsePanelResizeOptions = {
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  /** "left" = handle on right edge of panel (default). "right" = handle on left edge of panel. */
  direction?: "left" | "right";
  storageKey?: string;
};

type UsePanelResizeReturn = {
  width: number;
  isResizing: boolean;
  handleMouseDown: (e: React.MouseEvent) => void;
};

/**
 * Read persisted width from localStorage, clamped within bounds.
 * Returns `null` if nothing is stored or value is invalid.
 */
function readStoredWidth(key: string, min: number, max: number): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) {
      return Math.min(max, Math.max(min, parsed));
    }
  } catch {
    /* SSR or private mode — ignore */
  }
  return null;
}

function persistWidth(key: string, value: number): void {
  try {
    localStorage.setItem(key, String(Math.round(value)));
  } catch {
    /* ignore */
  }
}

/**
 * usePanelResize — lightweight drag-to-resize for a sidebar panel.
 *
 * - Initializes from localStorage if a previous width was saved
 * - Falls back to `defaultWidth` on first visit
 * - Persists the width when the user finishes dragging
 */
export function usePanelResize({
  defaultWidth,
  minWidth,
  maxWidth,
  direction = "left",
  storageKey = DEFAULT_STORAGE_KEY,
}: UsePanelResizeOptions): UsePanelResizeReturn {
  const [width, setWidth] = useState(
    () => readStoredWidth(storageKey, minWidth, maxWidth) ?? defaultWidth,
  );
  const [isResizing, setIsResizing] = useState(false);

  // All mutable state in one ref to avoid stale closures
  const stateRef = useRef({
    startX: 0,
    startWidth: defaultWidth,
    min: minWidth,
    max: maxWidth,
    active: false,
    direction,
    storageKey,
  });

  // Keep options in sync
  useEffect(() => {
    stateRef.current.min = minWidth;
    stateRef.current.max = maxWidth;
    stateRef.current.direction = direction;
    stateRef.current.storageKey = storageKey;
  }, [minWidth, maxWidth, direction, storageKey]);

  // Clamp width to current bounds (derived, not in effect)
  const clampedWidth = Math.min(maxWidth, Math.max(minWidth, width));

  useEffect(() => {
    let lastWidth = 0;

    const handleMove = (e: MouseEvent) => {
      if (!stateRef.current.active) return;
      const rawDelta = e.clientX - stateRef.current.startX;
      const delta =
        stateRef.current.direction === "right" ? -rawDelta : rawDelta;
      const clamped = Math.min(
        stateRef.current.max,
        Math.max(stateRef.current.min, stateRef.current.startWidth + delta),
      );
      lastWidth = clamped;
      setWidth(clamped);
    };

    const handleUp = () => {
      if (!stateRef.current.active) return;
      stateRef.current.active = false;
      setIsResizing(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";

      // Persist the final width
      if (lastWidth > 0) {
        persistWidth(stateRef.current.storageKey, lastWidth);
      }
    };

    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);

    return () => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      stateRef.current.startX = e.clientX;
      stateRef.current.startWidth = width;
      stateRef.current.active = true;
      setIsResizing(true);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [width],
  );

  return { width: clampedWidth, isResizing, handleMouseDown };
}
