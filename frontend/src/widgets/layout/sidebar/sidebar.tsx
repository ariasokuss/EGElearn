"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { SidebarUserMenu } from "@/features/settings";

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
    <aside className="flex flex-col rounded-[18px] bg-[#111722] text-white shadow-[0px_18px_40px_-28px_rgba(11,15,26,0.7)]">
      <nav className="flex flex-1 flex-col justify-between p-2">
        <div className="flex flex-col gap-1">
          <SidebarNavItem link="home" />
          {showLearning && <SidebarNavItem link="learning" hrefOverride={learningHref} />}
          <SidebarNavItem link="chat" />
          {/* Notes page not implemented yet — restore when /notes is ready */}
          {/* <SidebarNavItem link="notes" /> */}
        </div>

        <SidebarUserMenu />
      </nav>
    </aside>
  );
}
