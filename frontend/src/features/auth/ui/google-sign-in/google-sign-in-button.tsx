"use client";

import { useState } from "react";
import { GoogleIcon } from "@/shared/assets/icons";
import { getGoogleOAuthRedirectUrl } from "@/shared/lib/google-oauth-url";
import {
  getChromeIntentUrl,
  isInAppBrowserUserAgent,
} from "@/shared/lib/in-app-browser";
import { Button } from "@/shared/ui/button";

const buttonBase =
  "flex w-full items-center justify-center gap-2 transition-all";

type GoogleSignInButtonProps = {
  label: string;
};

export function GoogleSignInButton({ label }: GoogleSignInButtonProps) {
  const [loading, setLoading] = useState(false);
  const [showBrowserPrompt, setShowBrowserPrompt] = useState(false);
  const [copied, setCopied] = useState(false);

  const pageUrl = typeof window === "undefined" ? "" : window.location.href;
  const openInBrowserUrl =
    pageUrl && /Android/i.test(navigator.userAgent)
      ? getChromeIntentUrl(pageUrl)
      : pageUrl;

  async function copyPageLink() {
    if (!pageUrl) return;
    try {
      await navigator.clipboard.writeText(pageUrl);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function startGoogleSignIn() {
    if (isInAppBrowserUserAgent(navigator.userAgent)) {
      setLoading(false);
      setShowBrowserPrompt(true);
      return;
    }

    setLoading(true);
    window.location.assign(getGoogleOAuthRedirectUrl());
  }

  return (
    <div className="flex w-full flex-col gap-2">
      <Button
        size="l"
        variant="outline"
        type="button"
        disabled={loading}
        isLoading={loading}
        className={`${buttonBase} disabled:cursor-not-allowed disabled:opacity-60`}
        onClick={startGoogleSignIn}
      >
        <GoogleIcon className="size-4.5" />
        {label}
      </Button>
      {showBrowserPrompt && (
        <div
          aria-live="polite"
          className="flex flex-col gap-2 rounded-[8px] border border-amber-200 bg-amber-50 px-3 py-2 text-amber-950"
        >
          <p className="nova-text-label-small">
            Google sign-in needs Chrome or Safari. Open this page in your browser, then try again.
          </p>
          <div className="flex flex-wrap gap-2">
            {openInBrowserUrl && (
              <Button
                asChild
                size="sm"
                variant="outline"
                className="rounded-full bg-white px-3 text-amber-950 hover:bg-amber-100"
              >
                <a href={openInBrowserUrl} target="_blank" rel="noreferrer">
                  Open in browser
                </a>
              </Button>
            )}
            <Button
              size="sm"
              variant="plain"
              type="button"
              className="rounded-full px-3 text-amber-950 hover:bg-amber-100"
              onClick={() => {
                void copyPageLink();
              }}
            >
              {copied ? "Link copied" : "Copy link"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
