"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getAuthCallbackRedirectMode } from "@/shared/lib/auth-callback-redirect";
import { getDesktopLoginTokenFromSearch } from "@/shared/lib/desktop-login-token";
import {
  clearDesktopLoginPending,
  markDesktopLoginPending,
} from "@/shared/lib/desktop-login-pending";
import { parseOAuthCallbackHash } from "@/shared/lib/oauth-callback-hash";
import { setTokens } from "@/shared/lib";
import { PageLoader } from "@/shared/ui";

export function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const doneRef = useRef(false);

  useEffect(() => {
    if (doneRef.current) return;
    doneRef.current = true;

    const hash = window.location.hash;
    const desktopLoginToken = getDesktopLoginTokenFromSearch(window.location.search);
    const parsed = parseOAuthCallbackHash(hash);

    if (desktopLoginToken) {
      markDesktopLoginPending();
    }

    const stripAuthParams = () => {
      const clean = desktopLoginToken
        ? window.location.pathname
        : `${window.location.pathname}${window.location.search}`;
      window.history.replaceState(null, "", clean);
    };

    const completeSignIn = (
      accessToken: string,
      refreshToken: string,
      expiresIn: number,
    ) => {
      setTokens(accessToken, refreshToken, expiresIn);
      clearDesktopLoginPending();
      window.dispatchEvent(new CustomEvent("auth:tokens-updated"));
      stripAuthParams();
      if (getAuthCallbackRedirectMode({ desktopLoginToken }) === "reload") {
        window.location.replace("/");
        return;
      }
      router.prefetch("/");
      router.replace("/");
    };

    if (desktopLoginToken) {
      void fetch("/api/v1/auth/desktop-login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: desktopLoginToken }),
      })
        .then(async (res) => {
          if (!res.ok) {
            throw new Error("Invalid or expired desktop login link.");
          }
          return res.json() as Promise<{
            access_token: string;
            refresh_token: string;
            expires_in?: number;
          }>;
        })
        .then(({ access_token, refresh_token, expires_in }) => {
          completeSignIn(access_token, refresh_token, expires_in ?? 3600);
        })
        .catch((err: unknown) => {
          clearDesktopLoginPending();
          stripAuthParams();
          queueMicrotask(() =>
            setError(err instanceof Error ? err.message : "Invalid or expired desktop login link.")
          );
        });
      return;
    }

    if (!parsed) {
      stripAuthParams();
      queueMicrotask(() =>
        setError("Invalid or missing sign-in data. Please try again.")
      );
      return;
    }

    if (!parsed.ok) {
      stripAuthParams();
      queueMicrotask(() =>
        setError(parsed.error_description ?? parsed.error)
      );
      return;
    }

    const { access_token, refresh_token, expires_in } = parsed;
    completeSignIn(access_token, refresh_token, expires_in);
  }, [router]);

  if (error) {
    return (
      <section className="flex w-full max-w-[402px] flex-col items-center gap-6 text-center">
        <p className="nova-text-label-small text-red-600">
          {error}
        </p>
        <Link
          href="/auth"
          className="nova-text-label-small text-[#3B82F6] hover:opacity-80"
        >
          Back to sign in
        </Link>
      </section>
    );
  }

  return (
    <div className="flex min-h-[120px] w-full max-w-[402px] items-center justify-center">
      <PageLoader showText={false} />
    </div>
  );
}
