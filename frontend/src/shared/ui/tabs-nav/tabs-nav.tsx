"use client";

import {
  Fragment,
  memo,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { cn } from "@/shared/lib";
import { TabButton } from "@/shared/ui/tab-button";

export type TabItem = {
  key: string;
  label: ReactNode;
  tabClassName?: string;
};

type TabsNavProps = {
  tabs: TabItem[];
  activeIndex: number;
  onTabChange: (index: number) => void;
  /** Rendered between tabs (e.g. chevron arrows) */
  separator?: ReactNode;
  /** Enable horizontal scroll with overflow clipping (indicator goes under outer content) */
  scrollable?: boolean;
  /** Slot rendered before the tabs */
  before?: ReactNode;
  /** Slot rendered after the tabs (pushed right with ml-auto) */
  after?: ReactNode;
  /** Center tabs absolutely within the container */
  centered?: boolean;
  /** Accessible label for the tablist */
  ariaLabel?: string;
  className?: string;
};

function TabsNavInner({
  tabs,
  activeIndex,
  onTabChange,
  separator,
  scrollable = false,
  before,
  after,
  centered = false,
  ariaLabel,
  className,
}: TabsNavProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollEndTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const animatingRef = useRef(false);
  const lastContainerWidth = useRef(0);

  const [animate, setAnimate] = useState(false);
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);

  useEffect(() => {
    if (tabRefs.current.length !== tabs.length) {
      tabRefs.current = tabRefs.current.slice(0, tabs.length);
    }
  }, [tabs.length]);

  const setTabRef = useCallback(
    (index: number, el: HTMLDivElement | null) => {
      tabRefs.current[index] = el;
    },
    [],
  );

  const measure = useCallback(() => {
    const activeEl = tabRefs.current[activeIndex];
    const containerEl = containerRef.current;
    if (!activeEl || !containerEl) return;
    const containerRect = containerEl.getBoundingClientRect();
    const tabRect = activeEl.getBoundingClientRect();
    if (tabRect.width === 0) return;
    setIndicator({
      left: tabRect.left - containerRect.left,
      width: tabRect.width,
    });
  }, [activeIndex]);

  /* Measure on mount + resize */
  useEffect(() => {
    const containerEl = containerRef.current;
    if (!containerEl) return;

    lastContainerWidth.current = containerEl.offsetWidth;
    measure();

    let rafId = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const newWidth = containerEl.offsetWidth;
        const containerResized = newWidth !== lastContainerWidth.current;
        lastContainerWidth.current = newWidth;

        if (animatingRef.current) return;

        if (containerResized) {
          setAnimate(false);
        }
        measure();
      });
    });
    observer.observe(containerEl);
    return () => {
      cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, [measure]);

  /* Strip transition during scroll to avoid jank, re-enable after 150 ms idle */
  useEffect(() => {
    if (!scrollable) return;
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      if (indicatorRef.current) indicatorRef.current.style.transition = "none";
      clearTimeout(scrollEndTimerRef.current);
      scrollEndTimerRef.current = setTimeout(() => {
        if (indicatorRef.current) indicatorRef.current.style.transition = "transform 400ms ease-in-out, width 150ms ease-in-out";
      }, 150);
      measure();
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      clearTimeout(scrollEndTimerRef.current);
    };
  }, [scrollable, measure]);

  const handleClick = useCallback(
    (index: number) => {
      setAnimate(true);
      animatingRef.current = true;
      setTimeout(() => {
        animatingRef.current = false;
      }, 450);
      onTabChange(index);
    },
    [onTabChange],
  );

  const tabElements = tabs.map((tab, index) => (
    <Fragment key={tab.key}>
      <div ref={(el) => setTabRef(index, el)} className={scrollable ? "shrink-0" : undefined}>
        <TabButton
          type="button"
          role="tab"
          aria-selected={activeIndex === index}
          isActive={activeIndex === index}
          onClick={() => handleClick(index)}
          className={tab.tabClassName}
        >
          {tab.label}
        </TabButton>
      </div>
      {separator && index < tabs.length - 1 && separator}
    </Fragment>
  ));

  const indicatorEl = indicator && (
    <div
      ref={indicatorRef}
      className="pointer-events-none absolute -bottom-px h-px rounded-full bg-[var(--ege-text)]"
      style={{
        left: 0,
        width: indicator.width,
        transform: `translateX(${indicator.left}px)`,
        willChange: "transform",
        transition: (scrollable || animate) ? "transform 400ms ease-in-out, width 150ms ease-in-out" : undefined,
      }}
    />
  );

  if (scrollable) {
    return (
      <div
        role="tablist"
        aria-label={ariaLabel}
        className={cn("min-w-0 flex-1 overflow-x-clip", className)}
      >
        <div
          ref={scrollRef}
          className="overflow-x-auto [scrollbar-color:var(--ege-track)_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-[var(--ege-track)] [&::-webkit-scrollbar-track]:bg-transparent"
        >
          <div
            ref={containerRef}
            className="relative flex w-max min-w-full items-center gap-2 border-b border-[var(--ege-border)] pt-0.5 pb-2"
          >
            {tabElements}
            {indicatorEl}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label={ariaLabel}
      className={cn("relative flex shrink-0 items-center", className)}
    >
      {before}
      <div
        className={cn(
          "flex items-center gap-2",
          centered && "absolute left-1/2 -translate-x-1/2",
        )}
      >
        {tabElements}
      </div>
      {after && <div className="ml-auto">{after}</div>}
      {indicatorEl}
    </div>
  );
}

export const TabsNav = memo(TabsNavInner);
