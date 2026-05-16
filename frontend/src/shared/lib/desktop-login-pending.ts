const DESKTOP_LOGIN_PENDING_KEY = "auth_desktop_login_pending";

export function hasDesktopLoginTokenInSearch(search: string): boolean {
  if (!search) return false;
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return Boolean(params.get("desktop_login_token"));
}

export function isDesktopLoginCallbackUrl(): boolean {
  if (typeof window === "undefined") return false;
  return hasDesktopLoginTokenInSearch(window.location.search);
}

export function markDesktopLoginPending(): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(DESKTOP_LOGIN_PENDING_KEY, "1");
}

export function clearDesktopLoginPending(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(DESKTOP_LOGIN_PENDING_KEY);
}

export function isDesktopLoginPending(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(DESKTOP_LOGIN_PENDING_KEY) === "1";
}
