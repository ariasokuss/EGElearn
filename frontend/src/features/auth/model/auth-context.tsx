"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  getAccessToken,
  getRefreshToken,
  getExpiresAt,
  setTokens,
  clearTokens,
} from "@/shared/lib/auth-storage";
import { installAuthFetch } from "@/shared/api/api-client";
import {
  isDesktopLoginCallbackUrl,
  isDesktopLoginPending,
} from "@/shared/lib/desktop-login-pending";
import { meApiV1AuthMeGet, refreshApiV1AuthRefreshPost } from "@/shared/api/generated/api";
import type { UserOut } from "@/shared/api/generated/model";
import { PageLoader } from "@/shared/ui/page-loader";

const REFRESH_BEFORE_MS = 60_000;

async function runProactiveRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const res = await refreshApiV1AuthRefreshPost({ refresh_token: refreshToken });
    if (res.status === 200 && res.data) {
      const { access_token, refresh_token, expires_in } = res.data;
      setTokens(access_token, refresh_token, expires_in ?? 3600);
      return true;
    }
  } catch {
    /* ignore */
  }
  clearTokens();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("auth:session-lost"));
  }
  return false;
}

type AuthState = {
  user: UserOut | null;
  isAuthenticated: boolean;
  isLoading: boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
  });
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleProactiveRefreshRef = useRef<() => void>(() => {});

  const scheduleProactiveRefresh = useCallback(() => {
    const expiresAt = getExpiresAt();
    if (!expiresAt) return;

    const now = Date.now();
    const delay = expiresAt - now - REFRESH_BEFORE_MS;
    if (delay <= 0) return;

    refreshTimerRef.current = setTimeout(() => {
      refreshTimerRef.current = null;
      runProactiveRefresh().then((ok) => {
        if (ok) scheduleProactiveRefreshRef.current?.();
      });
    }, delay);
  }, []);

  useEffect(() => {
    scheduleProactiveRefreshRef.current = scheduleProactiveRefresh;
  }, [scheduleProactiveRefresh]);

  useEffect(() => {
    installAuthFetch();
  }, []);

  const checkSession = useCallback(() => {
    if (isDesktopLoginCallbackUrl() || isDesktopLoginPending()) {
      setState((s) => ({ ...s, isLoading: true }));
      return;
    }

    const token = getAccessToken();
    if (!token) {
      setState({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }

    // Trust the token immediately — set authenticated and stop blocking.
    // Fetch user data in the background without holding up navigation.
    setState((s) => ({
      ...s,
      isAuthenticated: true,
      isLoading: false,
    }));
    scheduleProactiveRefresh();

    let cancelled = false;
    meApiV1AuthMeGet()
      .then((res) => {
        if (cancelled) return;
        if (res.status === 200 && res.data) {
          setState((s) => ({ ...s, user: res.data }));
        } else {
          // Token was invalid — clear auth
          setState({ user: null, isAuthenticated: false, isLoading: false });
        }
      })
      .catch(() => {
        if (cancelled) return;
        setState({ user: null, isAuthenticated: false, isLoading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [scheduleProactiveRefresh]);

  const checkSessionCancelledRef = useRef(false);

  useEffect(() => {
    checkSessionCancelledRef.current = false;
    let sessionCleanup: (() => void) | void;
    queueMicrotask(() => {
      if (checkSessionCancelledRef.current) return;
      sessionCleanup = checkSession();
    });
    return () => {
      checkSessionCancelledRef.current = true;
      sessionCleanup?.();
    };
  }, [checkSession]);

  useEffect(() => {
    const onTokensUpdated = () => checkSession();
    window.addEventListener("auth:tokens-updated", onTokensUpdated);
    return () => window.removeEventListener("auth:tokens-updated", onTokensUpdated);
  }, [checkSession]);

  useEffect(() => {
    const onSessionLost = () => {
      clearTokens();
      setState({ user: null, isAuthenticated: false, isLoading: false });
    };

    const handler = () => onSessionLost();
    window.addEventListener("auth:session-lost", handler);
    return () => window.removeEventListener("auth:session-lost", handler);
  }, []);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, []);

  return (
    <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/auth");
  }, [isLoading, isAuthenticated, router]);

  if (!isLoading && !isAuthenticated) return null;

  return <>{children}</>;
}

export function AuthRedirectIfAuthenticated({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.prefetch("/");
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || isAuthenticated) return <PageLoader showText={false} />;

  return <>{children}</>;
}
