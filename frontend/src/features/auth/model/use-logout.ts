"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { getRefreshToken } from "@/shared/lib/auth-storage";
import { logoutApiV1AuthLogoutPost } from "@/shared/api/generated/api";

export function useLogout() {
  const router = useRouter();
  return useCallback(async () => {
    // Revoke refresh token on the server (best-effort)
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await logoutApiV1AuthLogoutPost({ refresh_token: refreshToken });
      } catch {
        /* best-effort — clear local state regardless */
      }
    }
    window.dispatchEvent(new CustomEvent("auth:session-lost"));
    router.replace("/auth");
  }, [router]);
}
