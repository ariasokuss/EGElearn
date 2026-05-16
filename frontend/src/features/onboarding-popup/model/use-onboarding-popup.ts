"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/features/auth";
import { isOnboardingPopupSeen, markOnboardingPopupSeen } from "../lib/onboarding-popup-storage";
import { isCurrentDesktopOnboardingEnvironment } from "./onboarding-popup-eligibility";

type UseOnboardingPopupResult = {
  isOpen: boolean;
  close: () => void;
};

function isSafeOnboardingPath(pathname: string | null): boolean {
  return pathname === "/" || pathname === "/learning";
}

function isPaywallOpen(): boolean {
  if (typeof document === "undefined") return false;
  return document.querySelector("[data-paywall-open='true']") != null;
}

export function useOnboardingPopup(): UseOnboardingPopupResult {
  const { user, isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [isEligible, setIsEligible] = useState(false);
  const evaluatedRef = useRef(false);
  const evaluatedUserIdRef = useRef<string | null>(null);
  const openTimerRef = useRef<number | null>(null);

  const clearOpenTimer = useCallback(() => {
    if (openTimerRef.current == null) return;
    window.clearTimeout(openTimerRef.current);
    openTimerRef.current = null;
  }, []);

  const resetPopupState = useCallback(() => {
    queueMicrotask(() => {
      setIsOpen(false);
      setIsEligible(false);
    });
  }, []);

  useEffect(() => {
    if (!isCurrentDesktopOnboardingEnvironment()) {
      evaluatedRef.current = false;
      evaluatedUserIdRef.current = null;
      clearOpenTimer();
      resetPopupState();
      return;
    }

    if (isLoading) return;
    if (!isAuthenticated) {
      evaluatedRef.current = false;
      evaluatedUserIdRef.current = null;
      clearOpenTimer();
      resetPopupState();
      return;
    }

    const userId = user?.id ?? null;
    if (evaluatedUserIdRef.current !== userId) {
      evaluatedRef.current = false;
      evaluatedUserIdRef.current = userId;
      clearOpenTimer();
      resetPopupState();
    }

    if (evaluatedRef.current) return;
    if (!userId) return;

    evaluatedRef.current = true;
    const eligible = !isOnboardingPopupSeen(userId);
    queueMicrotask(() => {
      setIsEligible(eligible);
    });
  }, [user?.id, isAuthenticated, isLoading, clearOpenTimer, resetPopupState]);

  useEffect(() => {
    clearOpenTimer();
    if (!isCurrentDesktopOnboardingEnvironment()) {
      resetPopupState();
      return;
    }
    if (!isEligible || isOpen || !isSafeOnboardingPath(pathname)) return;

    let cancelled = false;

    const tryOpen = () => {
      if (cancelled) return;
      if (!isSafeOnboardingPath(pathname)) return;
      if (isPaywallOpen()) {
        openTimerRef.current = window.setTimeout(tryOpen, 350);
        return;
      }
      setIsOpen(true);
      openTimerRef.current = null;
    };

    openTimerRef.current = window.setTimeout(tryOpen, 1000);

    return () => {
      cancelled = true;
      clearOpenTimer();
    };
  }, [isEligible, isOpen, pathname, clearOpenTimer, resetPopupState]);

  useEffect(() => {
    if (!isOpen) return;
    if (isSafeOnboardingPath(pathname)) return;
    queueMicrotask(() => {
      setIsOpen(false);
    });
  }, [isOpen, pathname]);

  useEffect(() => {
    return () => {
      clearOpenTimer();
    };
  }, [clearOpenTimer]);

  const close = useCallback(() => {
    clearOpenTimer();
    setIsOpen(false);
    setIsEligible(false);
    if (user?.id) {
      markOnboardingPopupSeen(user.id);
    }
  }, [user, clearOpenTimer]);

  return { isOpen, close };
}
