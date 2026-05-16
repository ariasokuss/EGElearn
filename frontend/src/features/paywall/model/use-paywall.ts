"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth";
import { isPaywallSeen, markPaywallSeen } from "../lib/paywall-storage";

const PAYWALL_AUTO_PROMPT_ENABLED = process.env.NEXT_PUBLIC_PAYWALL_AUTO_PROMPT === "true";

type UsePaywallResult = {
  isOpen: boolean;
  close: () => void;
};

export function usePaywall(): UsePaywallResult {
  const { user, isAuthenticated, isLoading } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const evaluatedRef = useRef(false);

  useEffect(() => {
    if (!PAYWALL_AUTO_PROMPT_ENABLED) return;
    if (evaluatedRef.current) return;
    if (isLoading) return;
    if (!isAuthenticated) return;
    const userId = user?.id;
    if (!userId) return;

    evaluatedRef.current = true;

    if (!isPaywallSeen(userId)) {
      markPaywallSeen(userId);
      queueMicrotask(() => {
        setIsOpen(true);
      });
    }
  }, [user?.id, isAuthenticated, isLoading]);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  return { isOpen, close };
}
