"use client";

import { memo, useCallback, useRef, useState, type RefObject } from "react";
import { AnimatePresence, motion } from "motion/react";

import { ChevronDownIcon } from "@/shared/assets/icons";
import { cn } from "@/shared";

import type { ScrollerNavItem } from "./extract-block-nav";
import { ScrollerTooltip } from "./scroller-tooltip";

const DASH_TRANSITION = { duration: 0.15 };
const DASH_WIDTH_SHORT = 8;
const DASH_WIDTH_LONG = 16;
const DASH_WIDTH_ACTIVE = 24;

type ScrollerProps = {
  navItems: ScrollerNavItem[];
  activeBlockId: string | null;
  scrollRef: RefObject<HTMLElement | null>;
};

function closestDashIndex(
  y: number,
  dashes: (HTMLButtonElement | null)[],
): number | null {
  let best: number | null = null;
  let bestDist = Infinity;
  for (let i = 0; i < dashes.length; i++) {
    const el = dashes[i];
    if (!el) continue;
    const center = el.offsetTop + el.offsetHeight / 2;
    const d = Math.abs(y - center);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

function ScrollerInner({ navItems, activeBlockId, scrollRef }: ScrollerProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipTop, setTooltipTop] = useState(0);
  const dashRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const dashContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBlock = useCallback(
    (blockId: string, index: number) => {
      if (index === 0) {
        scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      scrollRef.current
        ?.querySelector(`[data-block-id="${blockId}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    [scrollRef],
  );

  const activeIndex = activeBlockId
    ? navItems.findIndex((item) => item.blockId === activeBlockId)
    : -1;
  const canGoPrev = activeIndex > 0;
  const canGoNext = activeIndex >= 0 && activeIndex < navItems.length - 1;

  const scrollToPrev = useCallback(() => {
    if (!canGoPrev) return;
    const prev = navItems[activeIndex - 1];
    scrollToBlock(prev.blockId, activeIndex - 1);
  }, [canGoPrev, activeIndex, navItems, scrollToBlock]);

  const scrollToNext = useCallback(() => {
    if (!canGoNext) return;
    const next = navItems[activeIndex + 1];
    scrollToBlock(next.blockId, activeIndex + 1);
  }, [canGoNext, activeIndex, navItems, scrollToBlock]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const container = dashContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const idx = closestDashIndex(y, dashRefs.current);
    setHoveredIndex(idx);

    if (idx !== null) {
      const dash = dashRefs.current[idx];
      if (dash) {
        const dashCenter = dash.offsetTop + dash.offsetHeight / 2;
        const tooltipHeight = 83.5;
        setTooltipTop(dashCenter - tooltipHeight / 2);
      }
    }
  }, []);

  const handlePointerLeave = useCallback(() => {
    setHoveredIndex(null);
  }, []);

  const hoveredItem = hoveredIndex !== null ? navItems[hoveredIndex] : null;

  return (
    <div className="relative flex flex-col items-end gap-3">
      <button
        type="button"
        onClick={scrollToPrev}
        disabled={!canGoPrev}
        className="flex h-6 w-6 translate-x-1.75 items-center justify-center rounded-full transition-colors hover:bg-[#24252910] disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Scroll to previous block"
      >
        <ChevronDownIcon className="rotate-180 fill-[#242529]" />
      </button>

      <div
        ref={dashContainerRef}
        className="relative flex flex-col items-end pl-1"
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
      >
        {navItems.map((item, i) => {
          const isActive = item.blockId === activeBlockId;
          const dist =
            hoveredIndex !== null ? Math.abs(i - hoveredIndex) : null;
          const shift = dist === 0 ? -6 : dist === 1 ? -4 : dist === 2 ? -2 : 0;

          return (
            <motion.button
              key={item.blockId}
              ref={(el) => {
                dashRefs.current[i] = el;
              }}
              type="button"
              animate={{ x: shift }}
              transition={DASH_TRANSITION}
              className="py-2"
              style={{ width: 32 }}
              onClick={() => scrollToBlock(item.blockId, i)}
              aria-label={item.title}
            >
              <motion.div
                animate={{
                  width: isActive
                    ? DASH_WIDTH_ACTIVE
                    : i % 2 === 0
                      ? DASH_WIDTH_LONG
                      : DASH_WIDTH_SHORT,
                }}
                transition={DASH_TRANSITION}
                className={cn(
                  "ml-auto h-0.5 rounded-full",
                  isActive
                    ? "bg-[#242529]"
                    : dist === 0
                      ? "bg-[#A1A1AA]"
                      : "bg-[#E4E4E7]",
                )}
              />
            </motion.button>
          );
        })}

        <AnimatePresence>
          {hoveredItem && (
            <ScrollerTooltip
              key="tooltip"
              title={hoveredItem.title}
              description={hoveredItem.description}
              style={{ top: tooltipTop }}
            />
          )}
        </AnimatePresence>
      </div>

      <button
        type="button"
        onClick={scrollToNext}
        disabled={!canGoNext}
        className="flex h-6 w-6 translate-x-1.75 items-center justify-center rounded-full transition-colors hover:bg-[#24252910] disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Scroll to next block"
      >
        <ChevronDownIcon className="fill-[#242529]" />
      </button>
    </div>
  );
}

export const Scroller = memo(ScrollerInner);
