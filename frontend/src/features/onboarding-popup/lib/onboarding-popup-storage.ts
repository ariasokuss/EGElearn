const ONBOARDING_POPUP_SEEN_PREFIX = "onboarding-vid-seen:";

function storageKey(userId: string): string {
  return `${ONBOARDING_POPUP_SEEN_PREFIX}${userId}`;
}

export function isOnboardingPopupSeen(userId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(storageKey(userId)) === "1";
  } catch {
    return false;
  }
}

export function markOnboardingPopupSeen(userId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(storageKey(userId), "1");
  } catch {
    /* ignore quota / disabled storage */
  }
}
