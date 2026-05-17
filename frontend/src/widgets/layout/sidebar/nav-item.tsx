"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import { useTestGuard } from "@/shared/lib";

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
  notes: { href: APP_PATHS.notes, icon: NotesIcon, label: "Notes" },
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
      className={`relative flex min-h-[62px] min-w-[72px] flex-col items-center justify-center gap-0.5 rounded-[13px] px-2.5 py-2 transition-colors ${
        isActive ? "bg-[#eef1f5] text-[#0b0f1a]" : "text-white hover:bg-white/8"
      }`}
    >
      {isActive && (
        <span className="absolute left-1.5 top-3 h-9 w-1 rounded-full bg-[var(--ege-accent)]" />
      )}
      <div className="flex h-7 w-7 max-h-7 max-w-7 items-center justify-center rounded-full">
        <Icon />
      </div>
      <span className="nova-text-label-tiny">{label}</span>
    </Link>
  );
}
