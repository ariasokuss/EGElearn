"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { SidebarUserMenu } from "@/features/settings";
import { ThemeToggleButton } from "@/shared/ui";

import { SidebarNavItem } from "./nav-item";

const LAST_FOLDER_KEY = "lastFolderId";

function getLastFolderId() {
  return sessionStorage.getItem(LAST_FOLDER_KEY);
}

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  return () => window.removeEventListener("storage", cb);
}

export function Sidebar() {
  const pathname = usePathname();
  const lastFolderId = useSyncExternalStore(subscribe, getLastFolderId, () => null);

  const match = pathname.match(/^\/folders\/([^/?]+)/);
  if (match && typeof sessionStorage !== "undefined") {
    const id = match[1];
    if (id !== lastFolderId) {
      sessionStorage.setItem(LAST_FOLDER_KEY, id);
    }
  }

  const currentFolderId = match?.[1] ?? lastFolderId;
  const showLearning = pathname.startsWith("/folders") || !!currentFolderId;
  const learningHref = currentFolderId ? `/folders/${currentFolderId}` : "/learning";

  return (
    <aside className="flex flex-col bg-[var(--ege-canvas)] text-[var(--ege-text)]">
      <nav className="flex flex-1 flex-col justify-between gap-1 pt-0.5 p-2.5">
        <SidebarNavItem link="home" />

        <div className="flex flex-col gap-4">
          {showLearning && <SidebarNavItem link="learning" hrefOverride={learningHref} />}
          <SidebarNavItem link="chat" />
          {/* Notes page not implemented yet — restore when /notes is ready */}
          {/* <SidebarNavItem link="notes" /> */}
        </div>

        <div className="flex flex-col items-center gap-2">
          <ThemeToggleButton />
          <SidebarUserMenu />
        </div>
      </nav>
    </aside>
  );
}
