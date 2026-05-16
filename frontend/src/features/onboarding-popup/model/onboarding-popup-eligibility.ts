import { detectIsPhoneUserAgent } from "@/shared/lib/device/detect-is-phone";

const MIN_DESKTOP_ONBOARDING_WIDTH = 768;

type OnboardingEnvironment = {
  userAgent: string;
  maxTouchPoints?: number;
  platform?: string;
  viewportWidth: number;
};

export function isDesktopOnboardingEnvironment({
  userAgent,
  maxTouchPoints,
  platform,
  viewportWidth,
}: OnboardingEnvironment): boolean {
  if (viewportWidth < MIN_DESKTOP_ONBOARDING_WIDTH) return false;
  return !detectIsPhoneUserAgent(userAgent, maxTouchPoints, platform);
}

export function isCurrentDesktopOnboardingEnvironment(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return false;
  }

  return isDesktopOnboardingEnvironment({
    userAgent: navigator.userAgent,
    maxTouchPoints: navigator.maxTouchPoints,
    platform: navigator.platform,
    viewportWidth: window.innerWidth,
  });
}
