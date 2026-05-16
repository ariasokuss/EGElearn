/**
 * Auth-aware fetch wrapper.
 * Injects Bearer token and handles 401 with refresh + retry.
 */

import {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
} from "@/shared/lib/auth-storage";
import { isDesktopLoginPending } from "@/shared/lib/desktop-login-pending";
import { refreshApiV1AuthRefreshPost } from "@/shared/api/generated/api";

const AUTH_PATHS = [
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
  "/api/v1/auth/google",
  "/api/v1/auth/desktop-login",
];

function isAuthPath(url: string): boolean {
  try {
    const path = new URL(url, window.location.origin).pathname;
    return AUTH_PATHS.some((p) => path === p || path.startsWith(p + "?"));
  } catch {
    return false;
  }
}

/**
 * Origins we treat as "ours" for auth purposes. Includes the page origin (for
 * Next.js-proxied /api/... calls) and the direct backend origin used by SSE /
 * streaming endpoints that bypass Next rewrites.
 */
function isOurApiOrigin(origin: string): boolean {
  if (origin === window.location.origin) return true;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    try {
      if (new URL(apiUrl).origin === origin) return true;
    } catch {
      /* ignore */
    }
  }
  return false;
}

/**
 * True when the URL points to a host that is not one of our backend origins.
 * We must NOT inject Authorization headers into third-party requests
 * (S3 presigned URLs, public CDNs, etc.) — extra headers can break
 * presigned signatures and trigger CORS preflight rejections.
 */
function isExternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    return !isOurApiOrigin(parsed.origin);
  } catch {
    return false;
  }
}

let refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  if (isDesktopLoginPending()) return false;

  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const res = await refreshApiV1AuthRefreshPost(
      { refresh_token: refreshToken },
      { credentials: "include" }
    );

    if (res.status === 200 && res.data) {
      const { access_token, refresh_token, expires_in } = res.data;
      setTokens(access_token, refresh_token, expires_in ?? 3600);
      return true;
    }
  } catch {
    /* ignore */
  }
  if (!isDesktopLoginPending()) {
    clearTokens();
  }
  if (typeof window !== "undefined" && !isDesktopLoginPending()) {
    window.dispatchEvent(new CustomEvent("auth:session-lost"));
  }
  return false;
}

function mergeHeaders(init?: RequestInit, addAuth?: boolean): HeadersInit {
  const token = addAuth ? getAccessToken() : null;
  const base = new Headers(init?.headers);
  if (token) base.set("Authorization", `Bearer ${token}`);
  return base;
}

let isInstalled = false;

/**
 * Replaces window.fetch with auth-aware version.
 * Call once on app init (client-side). Idempotent — safe to call multiple times.
 */
export function installAuthFetch(): void {
  if (typeof window === "undefined") return;
  if (isInstalled) return;
  isInstalled = true;
  const origFetch = window.fetch;
  window.fetch = async function authFetch(
    input: RequestInfo | URL,
    init?: RequestInit
  ): Promise<Response> {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const isAuth = isAuthPath(url);
    const isExternal = isExternalUrl(url);

    // Pass third-party requests (S3 presigned URLs, etc.) through untouched.
    // Adding Authorization headers breaks presigned signatures and triggers
    // CORS preflight failures.
    if (isExternal) {
      return origFetch(input, init);
    }

    const res = await origFetch(input, {
      ...init,
      headers: mergeHeaders(init, !isAuth),
    });

    if (res.status === 401 && !isAuth && !isDesktopLoginPending()) {
      if (!refreshPromise) refreshPromise = doRefresh();
      const ok = await refreshPromise;
      refreshPromise = null;
      if (ok) {
        return origFetch(input, {
          ...init,
          headers: mergeHeaders(init, true),
        });
      }
    }

    return res;
  };
}

// Eagerly install at module load so the patched fetch is in place before any
// descendant component's useEffect fires its first request. Without this, child
// data-fetching effects run before AuthProvider's useEffect (children mount
// first), so the very first request after a hard reload goes out without the
// Bearer token — the backend's dev-bypass falls through to a different user
// and resources scoped strictly by user_id come back empty.
if (typeof window !== "undefined") {
  installAuthFetch();
}
