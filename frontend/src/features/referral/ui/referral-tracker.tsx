"use client";

import { useEffect } from "react";
import {
  getRefCode,
  setRefCode,
  ensureVisitorId,
} from "@/shared/lib/referral-storage";

/**
 * Invisible component that captures `?ref=CODE` from the URL,
 * persists it in cookies, and fires a visit-tracking request to the backend.
 * Mount once at the app root (e.g. in Providers).
 */
export function ReferralTracker() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = params.get("ref");

    if (ref) {
      if (!getRefCode()) {
        setRefCode(ref);
      }

      const visitorId = ensureVisitorId();

      fetch("/api/v1/referral/track/visit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: ref,
          visitor_id: visitorId,
          landing_page: window.location.pathname,
        }),
      }).catch(() => {});

      params.delete("ref");
      const clean =
        params.toString()
          ? `${window.location.pathname}?${params.toString()}`
          : window.location.pathname;
      window.history.replaceState({}, "", clean);
    }
  }, []);

  return null;
}
