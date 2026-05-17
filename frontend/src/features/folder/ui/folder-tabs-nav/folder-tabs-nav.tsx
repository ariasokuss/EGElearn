"use client";

import Link from "next/link";
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { FolderMiniIcon, RightIcon } from "@/shared/assets/icons";
import { APP_PATHS } from "@/shared/config";
import { TabsNav, type TabItem } from "@/shared/ui/tabs-nav/tabs-nav";

import {
  FOLDER_NAV_HOME_ARIA_LABEL,
  FOLDER_TABS,
  getFolderTabIndex,
  readSavedTab,
  resolveInitialFolderTab,
  type FolderTabParam,
  writeSavedTab,
} from "../../lib/folder-ui-copy";

const PRACTICE_TAB_INDEX = FOLDER_TABS.findIndex((t) => t.param === "practice");

function resolveInitialIndex(folderId: string | null): number {
  if (typeof window === "undefined") return 0;
  const initialTab = resolveInitialFolderTab(
    new URLSearchParams(window.location.search).get("tab"),
    readSavedTab(folderId),
  );
  return getFolderTabIndex(initialTab);
}

const TAB_ITEMS: TabItem[] = FOLDER_TABS.map((tab) => ({
  key: tab.param ?? "roadmap",
  label: tab.label,
}));

function getActiveIndexFromUrl(): number {
  if (typeof window === "undefined") return 0;
  return getFolderTabIndex(new URLSearchParams(window.location.search).get("tab"));
}

function FolderNavHomeLink() {
  return (
    <div>
      <div className="border-b border-[#E8E5E180]">
        <div className="w-13 h-7 flex gap-2 mt-0.5 mr-2 mb-2">
          <div className="flex items-center">
            <div className="w-9 h-7 flex items-center justify-center">
              <Link
                href={APP_PATHS.home}
                className="hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring/50"
                aria-label={FOLDER_NAV_HOME_ARIA_LABEL}
                prefetch
              >
                <FolderMiniIcon aria-hidden />
              </Link>
            </div>
            <RightIcon aria-hidden />
          </div>
        </div>
      </div>
    </div>
  );
}

export type FolderTabsNavProps = {
  /** Fired when user clicks "Practice questions" while already on that tab (e.g. leave results → landing). */
  onPracticeTabReselect?: VoidFunction;
  onFolderTabChange?: (tab: FolderTabParam) => void;
};

function FolderTabsNavInner({ onPracticeTabReselect, onFolderTabChange }: FolderTabsNavProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const rawUrlTab = searchParams.get("tab");
  const pathnameRef = useRef(pathname);
  useLayoutEffect(() => {
    pathnameRef.current = pathname;
  });

  // Extract folder ID from /folders/{id}
  const folderId = pathname.split("/folders/")[1]?.split("/")[0] ?? null;

  // Start at 0 to match SSR output, then snap to the real index before first paint.
  const [activeIndex, setActiveIndex] = useState(0);

  // useLayoutEffect fires after commit but before paint — no hydration mismatch,
  // no visible animation when restoring a saved tab.
  useLayoutEffect(() => {
    const correct = resolveInitialIndex(folderId);
    if (correct !== 0) setActiveIndex(correct);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Silently sync URL with localStorage on mount (replaceState = no navigation/animation)
    const currentParams = new URLSearchParams(window.location.search);
    const urlHasTab = currentParams.has("tab");
    const urlIndex = getFolderTabIndex(currentParams.get("tab"));
    if (urlIndex > 0) {
      writeSavedTab(folderId, FOLDER_TABS[urlIndex].param);
    } else if (!urlHasTab) {
      const saved = readSavedTab(folderId);
      const savedIndex = saved ? FOLDER_TABS.findIndex((t) => t.param === saved) : -1;
      if (savedIndex > 0) {
        const qs = new URLSearchParams({ tab: saved! });
        window.history.replaceState(null, "", `${pathnameRef.current}?${qs.toString()}`);
      }
    }

    const onPopState = () => setActiveIndex(getActiveIndexFromUrl());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [folderId]);

  useEffect(() => {
    if (rawUrlTab === null) return;
    setActiveIndex(getFolderTabIndex(rawUrlTab));
  }, [rawUrlTab]);

  const handleTabChange = useCallback(
    (index: number) => {
      const param = FOLDER_TABS[index].param;
      const current = new URLSearchParams(window.location.search);
      const currentTab = current.get("tab");

      if (
        onPracticeTabReselect &&
        index === PRACTICE_TAB_INDEX &&
        param === "practice" &&
        currentTab === "practice"
      ) {
        onPracticeTabReselect();
      }

      setActiveIndex(index);
      onFolderTabChange?.(param);
      writeSavedTab(folderId, param);
      if (param === null) {
        current.delete("tab");
      } else {
        current.set("tab", param);
      }
      const qs = current.toString();
      window.history.pushState(null, "", qs ? `${pathnameRef.current}?${qs}` : pathnameRef.current);
    },
    [onFolderTabChange, onPracticeTabReselect, folderId],
  );

  return (
    <div className="flex">
      <FolderNavHomeLink />

      <TabsNav
        tabs={TAB_ITEMS}
        activeIndex={activeIndex}
        onTabChange={handleTabChange}
        scrollable
        ariaLabel="Folder sections"
      />
    </div>
  );
}

export const FolderTabsNav = memo(FolderTabsNavInner);
