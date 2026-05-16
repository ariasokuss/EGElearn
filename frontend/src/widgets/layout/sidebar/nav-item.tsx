"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import { cn, useTestGuard } from "@/shared/lib";

import {
  HomeIcon,
  LearningIcon,
  NotesIcon,
  ChatIcon,
} from "@/shared/assets/icons";
import { APP_PATHS } from "@/shared/config";

export type NavLink = "home" | "learning" | "chat" | "notes";

type NavConfig = {
  href: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  activePrefixes?: string[];
};

export const NAV_CONFIG: Record<NavLink, NavConfig> = {
  home: { href: APP_PATHS.home, icon: HomeIcon, label: "Главная" },
  learning: {
    href: APP_PATHS.learning,
    icon: LearningIcon,
    label: "Обучение",
    activePrefixes: [APP_PATHS.learning, "/folders"],
  },
  chat: { href: APP_PATHS.chat, icon: ChatIcon, label: "Чат" },
  notes: { href: APP_PATHS.notes, icon: NotesIcon, label: "Заметки" },
};

type SidebarNavItemProps = {
  link: NavLink;
  hrefOverride?: string;
};

export function SidebarNavItem({ link, hrefOverride }: SidebarNavItemProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { isTestActive, requestNavigation } = useTestGuard();
  const { href: defaultHref, icon: Icon, label, activePrefixes } = NAV_CONFIG[link];
  const href = hrefOverride ?? defaultHref;
  const prefixes = activePrefixes ?? [href];
  const isActive = prefixes.some((p) =>
    p === APP_PATHS.home ? pathname === APP_PATHS.home : pathname.startsWith(p),
  );

  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault()
    if (!isTestActive) {
      router.push(href)
      return
    }
    const canProceed = await requestNavigation()
    if (canProceed) {
      router.push(href)
    }
  }

  return (
    <Link
      href={href}
      data-nav={link}
      onClick={handleClick}
      className={cn(
        "relative flex min-h-[64px] min-w-[64px] flex-col items-center justify-center gap-0.5 rounded-xl border px-2.5 pt-1 pb-2 transition-colors",
        isActive
          ? "border-[var(--ege-border)] bg-[var(--ege-surface-raised)] text-[var(--ege-text)]"
          : "border-transparent text-[var(--ege-muted)] hover:bg-[var(--ege-surface)] hover:text-[var(--ege-text)]",
      )}
    >
      <div className="flex h-9 w-9 max-h-9 max-w-9 items-center justify-center rounded-full py-2.5">
        <Icon />
      </div>
      <span className="nova-text-label-tiny text-inherit">{label}</span>
    </Link>
  );
}
