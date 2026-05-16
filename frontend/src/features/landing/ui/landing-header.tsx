"use client";

import Link from "next/link";
import { useCallback, useEffect, type MouseEvent } from "react";

import { LandingLogo } from "./landing-logo";

const navItems = [
  { label: "Как это работает", href: "#how-it-works" },
  { label: "Прогресс", href: "#roadmap" },
  { label: "Уроки", href: "#lesson" },
  { label: "Предметы", href: "#subjects" },
  { label: "Практика", href: "#testing" },
] as const;

/** Breathing room between fixed header bottom and section headline (pure CSS anchors often undershoot). */
const NAV_ANCHOR_GAP_PX = 24;
/** Scroll a little further past the aligned point so section titles clear the viewport edge. */
const NAV_ANCHOR_SCROLL_NUDGE_PX = 46;

export function LandingHeader() {
  const scrollLandingNavToHash = useCallback((hash: string) => {
    if (!hash.startsWith("#") || hash === "#") return;
    const id = decodeURIComponent(hash.slice(1));
    const target = document.getElementById(id);
    const root = document.getElementById("nl-landing-root");
    if (!target || !root) return;

    const headerEl = document.querySelector<HTMLElement>(".site-header");
    const headerH = headerEl?.getBoundingClientRect().height ?? 0;

    const y =
      target.getBoundingClientRect().top +
      window.scrollY -
      headerH -
      NAV_ANCHOR_GAP_PX +
      NAV_ANCHOR_SCROLL_NUDGE_PX;
    window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
  }, []);

  const onLandingNavClick = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      const href = e.currentTarget.getAttribute("href");
      if (!href?.startsWith("#")) return;
      e.preventDefault();
      scrollLandingNavToHash(href);
    },
    [scrollLandingNavToHash],
  );

  /** Native #scroll + scroll-padding is unreliable across browsers; align after layout. */
  useEffect(() => {
    const { hash } = window.location;
    if (!hash || hash === "#") return;
    const id = decodeURIComponent(hash.slice(1));
    if (!document.getElementById(id)) return;

    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        scrollLandingNavToHash(hash);
      }),
    );
  }, [scrollLandingNavToHash]);

  useEffect(() => {
    const mobileCheckbox = document.getElementById("menu-toggle") as HTMLInputElement | null;
    const mobileLinks = document.querySelectorAll<HTMLAnchorElement>("#mobile-nav a");
    if (!mobileCheckbox) return;

    const onClickNav = () => {
      mobileCheckbox.click();
    };
    mobileLinks.forEach((link) => link.addEventListener("click", onClickNav));
    return () => mobileLinks.forEach((link) => link.removeEventListener("click", onClickNav));
  }, []);

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="inline-flex items-center">
          <LandingLogo />
        </Link>

        <nav className="hidden md:block">
          <ul className="nav-pill">
            {navItems.map((item) => (
              <li key={item.href}>
                <a href={item.href} className="nav-link" onClick={onLandingNavClick}>
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="invisible justify-self-end md:visible">
          <div className="header-cta">
            <Link href="/auth" className="btn-login">
              Войти
            </Link>
            <Link href="/registration" className="btn-signup">
              Начать
            </Link>
          </div>
        </div>

        <div className="block md:hidden">
          <input type="checkbox" id="menu-toggle" className="hidden" />

          <label
            htmlFor="menu-toggle"
            id="menu-toggle-icon"
            className="flex size-6 flex-col items-center justify-center gap-1"
          >
            <div id="menu-toggle-line-1" className="h-0.5 w-4 rounded-full bg-[#27272A] transition-all" />
            <div id="menu-toggle-line-2" className="h-0.5 w-4 rounded-full bg-[#27272A] transition-all" />
          </label>

          <div className="invisible fixed inset-0 -z-10 left-full flex items-center justify-center bg-white transition-all">
            <div className="absolute inset-x-0 top-[90px] h-px bg-[#F4F4F5]" />

            <nav id="mobile-nav" className="relative">
              <ul className="flex flex-col items-center gap-6">
                {navItems.map((item) => (
                  <li key={item.href}>
                    <a href={item.href} className="mobile-nav-item" onClick={onLandingNavClick}>
                      {item.label}
                    </a>
                  </li>
                ))}
                <div className="h-px w-8 rounded-full bg-[#E4E4E7]" />
                <label htmlFor="menu-toggle" className="relative size-9">
                  <div className="absolute top-1/2 left-1/2 h-0.75 w-7 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-full bg-[#27272A]" />
                  <div className="absolute top-1/2 left-1/2 h-0.75 w-7 -translate-x-1/2 -translate-y-1/2 -rotate-45 rounded-full bg-[#27272A]" />
                </label>
              </ul>
            </nav>
          </div>
        </div>
      </div>
    </header>
  );
}
