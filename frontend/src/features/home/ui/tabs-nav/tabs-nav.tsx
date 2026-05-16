"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { TabButton } from "@/shared/ui/tab-button";

import { HOME_FOLDER_TABS } from "../../lib/home-ui-copy";

export function TabsNav() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const containerRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  const setTabRef = useCallback((index: number) => (el: HTMLDivElement | null) => {
    tabRefs.current[index] = el;
  }, []);

  const activeParam = searchParams.get("tab");
  const activeIndex = HOME_FOLDER_TABS.findIndex(
    (tab) => tab.param === activeParam
  );
  const resolvedActiveIndex = activeIndex === -1 ? 0 : activeIndex;

  useEffect(() => {
    const activeEl = tabRefs.current[resolvedActiveIndex];
    const containerEl = containerRef.current;
    if (!activeEl || !containerEl) return;

    const containerRect = containerEl.getBoundingClientRect();
    const tabRect = activeEl.getBoundingClientRect();
    setIndicator({
      left: tabRect.left - containerRect.left,
      width: tabRect.width,
    });
  }, [activeParam, resolvedActiveIndex]);

  const handleClick = (param: string | null) => {
    if (param === null) {
      router.push(pathname);
    } else {
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", param);
      router.push(`${pathname}?${params.toString()}`);
    }
  };

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label="Категории папок"
      className="relative flex max-w-170.5 items-center gap-2 border-b border-[var(--ege-border)] pb-[8px]"
    >
      {HOME_FOLDER_TABS.map((tab, index) => (
        <div key={tab.label} ref={setTabRef(index)}>
          <TabButton
            type="button"
            role="tab"
            aria-selected={resolvedActiveIndex === index}
            isActive={resolvedActiveIndex === index}
            onClick={() => handleClick(tab.param)}
          >
            {tab.label}
          </TabButton>
        </div>
      ))}

      <div
        className="absolute -bottom-px h-px rounded-full bg-[var(--ege-text)] transition-all duration-400 ease-in-out"
        style={{ left: indicator.left, width: indicator.width }}
      />
    </div>
  );
}
