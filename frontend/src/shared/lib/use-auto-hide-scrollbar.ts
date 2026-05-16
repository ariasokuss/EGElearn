"use client"

import { useEffect, type RefObject } from "react";

export function useAutoHideScrollbar(
  ref: RefObject<HTMLElement | null>,
  idleMs = 700,
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const handleScroll = () => {
      el.dataset.scrolling = "true";
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        el.dataset.scrolling = "false";
      }, idleMs);
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", handleScroll);
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [ref, idleMs]);
}
