"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import { TabButton } from "@/shared/ui/tab-button";
import { cn } from "@/shared/lib";

import { SETTINGS_NAV_MAIN } from "../lib/settings-nav";
import { MenuLimitsIcon, MenuSupportIcon, MenuTermsIcon, MenuUpgradeIcon, MenuUserIcon } from "@/shared/assets/icons";

const ICONS = {
  profile: MenuUserIcon,
  limits: MenuLimitsIcon,
  "upgrade-plan": MenuUpgradeIcon,
  support: MenuSupportIcon,
  terms: MenuTermsIcon,
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
      aria-label="Настройки"
      className="relative flex max-w-170.5 items-center gap-2 border-b border-[var(--ege-border)] pb-[8px]"
    >
      <div ref={tabRef} className="w-fit">
        <TabButton type="button" role="tab" aria-selected isActive aria-current="page">
          Настройки
        </TabButton>
      </div>
      <div
        className="pointer-events-none absolute -bottom-px h-px rounded-full bg-[var(--ege-text)] transition-all duration-400 ease-in-out"
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
        aria-label="Разделы настроек"
        className="flex w-[min(260px,34vw)] shrink-0 flex-col border-r border-[var(--ege-border)] bg-[var(--ege-surface)] px-3 py-6 text-[var(--ege-text)]"
      >
        <SettingsSingleTabNav />
        <p className="mt-5 mb-2 px-2 nova-text-label-small tracking-wide text-[var(--ege-muted)]">
          Основные
        </p>
        <ul className="mt-2 flex list-none flex-col gap-0.5">
          {SETTINGS_NAV_MAIN.map((item) => {
            const Icon = ICONS[item.id];
            const active = !item.disabled && (pathname === item.href || pathname.startsWith(`${item.href}/`));
            return (
              <Fragment key={item.id}>
                {item.id === "support" && (
                  <li aria-hidden className="list-none">
                    <div className="mt-4 h-px bg-[var(--ege-border)]" />
                  </li>
                )}
                <li>
                  {item.disabled ? (
                    <span
                      className="flex cursor-default items-center gap-3 rounded-xl px-[8px] py-[10px] nova-text-label-small text-[var(--ege-muted)] opacity-60"
                      aria-disabled="true"
                    >
                      <Icon className="h-5 w-5 shrink-0 text-[var(--ege-muted)]" />
                      {item.label}
                      <span className="ml-auto nova-text-label-tiny font-normal text-[var(--ege-muted)]">Скоро</span>
                    </span>
                  ) : (
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-[8px] py-[10px] nova-text-label-small transition-colors",
                        active
                          ? "bg-[var(--ege-surface-raised)] text-[var(--ege-text)]"
                          : "text-[var(--ege-muted)] hover:bg-[var(--ege-surface-raised)] hover:text-[var(--ege-text)]",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-5 w-5 shrink-0",
                          active ? "text-[var(--ege-text)]" : "text-[var(--ege-muted)]",
                        )}
                      />
                      {item.label}
                    </Link>
                  )}
                </li>
              </Fragment>
            );
          })}
        </ul>
        
      </nav>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-[var(--ege-surface-raised)] text-[var(--ege-text)]">{children}</div>
    </div>
  );
}
