"use client";

import type { ReactNode } from "react";
import { useState } from "react";

import { useAuth } from "@/features/auth";
import { detectIsPhoneUserAgent } from "@/shared/lib";
import { PageLoader } from "@/shared/ui";
import { shouldRenderMainAppChildren } from "./main-app-mobile-gate-visibility";

type MainAppMobileGateProps = {
  isPhoneFromUa: boolean;
  stub: ReactNode;
  children: ReactNode;
};

export function MainAppMobileGate({ isPhoneFromUa, stub, children }: MainAppMobileGateProps) {
  const { isLoading } = useAuth();
  const [isPhone] = useState(() => {
    if (typeof navigator === "undefined") return isPhoneFromUa;
    return (
      detectIsPhoneUserAgent(
        navigator.userAgent,
        navigator.maxTouchPoints,
        navigator.platform,
      )
    );
  });

  if (shouldRenderMainAppChildren({ isPhone, isLoading })) {
    return <div className="h-dvh min-h-0 overflow-hidden">{children}</div>;
  }

  if (isLoading) {
    return (
      <div className="flex h-dvh min-h-0 items-center justify-center overflow-hidden bg-[var(--ege-canvas)] text-[var(--ege-text)] p-1">
        <PageLoader showText={false} />
      </div>
    );
  }

  return <div className="md:hidden">{stub}</div>;
}
