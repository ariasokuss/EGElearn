"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useAuth, useLogout } from "@/features/auth";
import { MenuRibbonIcon, MenuUserIcon, SettingsIcon } from "@/shared/assets/icons";
import { cn } from "@/shared/lib";
import { Button } from "@/shared";


export function SidebarUserMenu() {
  const pathname = usePathname();
  const settingsActive = pathname.startsWith("/settings");
  const { user } = useAuth();
  const logoutAction = useLogout();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnId = useId();
  const menuId = `${btnId}-menu`;

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const el = wrapRef.current;
      if (el && !el.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  const logout = useCallback(() => {
    close();
    logoutAction();
  }, [close, logoutAction]);

  return (
    <div ref={wrapRef} className="relative flex min-w-16 flex-col items-center py-1.5">
      <button
        id={btnId}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-[36px] w-[36px] shrink-0 items-center justify-center overflow-hidden rounded-full p-0 transition-colors",
          open || settingsActive
            ? "bg-[#F1ECE9]"
            : "bg-[#E8E5E1]/50 hover:bg-[#F1ECE999]",
        )}
      >
        {user?.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- remote user avatar URL
          <img
            src={user.avatar_url}
            alt=""
            className="h-[36px] w-[36px] rounded-full object-cover"
          />
        ) : (
          <MenuUserIcon className="h-[24px] w-[24px] text-[#242529]" />
        )}
        <span className="sr-only">Account menu</span>
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          aria-labelledby={btnId}
          className="absolute bottom-full z-50 w-[min(260px,calc(100vw-24px))] translate-x-[116px] rounded-2xl border border-[#E8E5E1]/80 bg-white p-2 shadow-[0px_8px_24px_-4px_rgba(28,40,64,0.12),0px_4px_8px_-2px_rgba(28,40,64,0.06)]"
        >
          <ul className="flex flex-col gap-0.5 p-1">
            <li role="none">
              <Link
                role="menuitem"
                href="/settings/profile"
                onClick={close}
                className="flex items-center gap-3 rounded-xl px-[8px] py-[4px] nova-text-label-small text-[#242529] transition-colors hover:bg-[#FAF9F7]"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center text-[#71717A]">
                  <SettingsIcon />
                </span>
                <span className="flex-1">Settings</span>
                <kbd className="hidden font-sans nova-text-label-tiny text-[#A1A1AA] sm:inline">
                  ⌘ ,
                </kbd>
              </Link>
            </li>
            <li role="none">
              <span
                role="menuitem"
                aria-disabled="true"
                className="flex cursor-default items-center gap-3 rounded-xl px-[8px] py-[4px] nova-text-label-small text-[#A1A1AA]"
              >
                <MenuRibbonIcon className="h-5 w-5 shrink-0 text-[#D4D4D8]" />
                <span className="flex-1">Upgrade plan</span>
                <span className="nova-text-label-tiny text-[#D4D4D8]">Soon</span>
              </span>
            </li>
          </ul>

          <div className="my-2 h-px bg-[#E8E5E180]" role="separator" />

          <div className="px-1 pb-1">
            <Button
              variant="outline"
              rounded={false}
              size="l"
              type="button"
              role="menuitem"
              onClick={logout}
              className="w-full"
            >
              Log out
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
