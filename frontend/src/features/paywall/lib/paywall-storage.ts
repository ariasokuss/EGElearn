const PAYWALL_SEEN_PREFIX = "novalearn_paywall_seen:";

function storageKey(userId: string): string {
  return `${PAYWALL_SEEN_PREFIX}${userId}`;
}

export function isPaywallSeen(userId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(storageKey(userId)) === "1";
  } catch {
    return false;
  }
}

export function markPaywallSeen(userId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(storageKey(userId), "1");
  } catch {
    /* ignore quota / disabled storage */
  }
}
