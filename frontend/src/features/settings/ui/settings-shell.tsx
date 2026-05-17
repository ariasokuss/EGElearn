"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { TabButton } from "@/shared/ui/tab-button";
import { cn } from "@/shared/lib";

import { SETTINGS_NAV_MAIN } from "../lib/settings-nav";
import { MenuUserIcon } from "@/shared/assets/icons";

const ICONS = {
  profile: MenuUserIcon,
} as const;

function SettingsSingleTabNav() {
  const containerRef = useRef<HTMLDivElement>(null);
  const tabRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  const updateIndicator = useCallback(() => {
    const containerEl = containerRef.current;
    const el = tabRef.current;
    if (!containerEl || !el) return;
    const containerRect = containerEl.getBoundingClientRect();
    const tabRect = el.getBoundingClientRect();
    setIndicator({
      left: tabRect.left - containerRect.left,
      width: tabRect.width,
    });
  }, []);

  useEffect(() => {
    updateIndicator();
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(updateIndicator);
    ro.observe(container);
    return () => ro.disconnect();
  }, [updateIndicator]);

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label="Settings"
      className="relative flex max-w-170.5 items-center gap-2 border-b border-[#E8E5E180] pb-[8px]"
    >
      <div ref={tabRef} className="w-fit">
        <TabButton type="button" role="tab" aria-selected isActive aria-current="page">
          Аккаунт
        </TabButton>
      </div>
      <div
        className="pointer-events-none absolute -bottom-px h-px rounded-full bg-[#242529] transition-all duration-400 ease-in-out"
        style={{ left: indicator.left, width: indicator.width }}
      />
    </div>
  );
}

export function SettingsShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full min-h-0 w-full flex-1 overflow-hidden">
      <nav
        aria-label="Разделы аккаунта"
        className="flex w-[min(260px,34vw)] shrink-0 flex-col border-r border-[#E8E5E180] px-3 py-6"
      >
        <SettingsSingleTabNav />
        <p className="mt-5 mb-2 px-2 nova-text-label-small tracking-wide text-[#71717A]">
          Настройки
        </p>
        <ul className="mt-2 flex list-none flex-col gap-0.5">
          {SETTINGS_NAV_MAIN.map((item) => {
            const Icon = ICONS[item.id];
            const active = !item.disabled && (pathname === item.href || pathname.startsWith(`${item.href}/`));
            return (
              <li key={item.id}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-[8px] py-[10px] nova-text-label-small transition-colors",
                    active
                      ? "bg-[#F1ECE9]/60 text-[#242529] hover:bg-[#F1ECE9]"
                      : "text-[#242529] hover:bg-[#F1ECE9]",
                  )}
                >
                  <Icon
                    className={cn(
                      "h-5 w-5 shrink-0",
                      active ? "text-[#242529]" : "text-[#71717A]",
                    )}
                  />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        
      </nav>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-white">{children}</div>
    </div>
  );
}
