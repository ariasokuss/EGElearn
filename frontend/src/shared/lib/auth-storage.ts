const AUTH_ACCESS_TOKEN_KEY = "auth_access_token";
const AUTH_REFRESH_TOKEN_KEY = "auth_refresh_token";
const AUTH_EXPIRES_AT_KEY = "auth_expires_at";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_REFRESH_TOKEN_KEY);
}

export function getExpiresAt(): number | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_EXPIRES_AT_KEY);
  if (!raw) return null;
  const value = parseInt(raw, 10);
  return Number.isFinite(value) ? value : null;
}

export function setTokens(
  accessToken: string,
  refreshToken: string,
  expiresInSeconds: number
): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(AUTH_ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, refreshToken);
  const expiresAt = Date.now() + expiresInSeconds * 1000;
  localStorage.setItem(AUTH_EXPIRES_AT_KEY, String(expiresAt));
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(AUTH_ACCESS_TOKEN_KEY);
  localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
  localStorage.removeItem(AUTH_EXPIRES_AT_KEY);
}
