"use client";

import { useEffect, useRef, useState } from "react";

import { sendDesktopLinkApiV1MailSendDesktopLinkPost } from "@/shared/api/generated/api";
import { Button, PageCard } from "@/shared/ui";

const RESEND_COOLDOWN_MS = 60_000;

type SendStatus = "idle" | "loading" | "sent" | "error";

export function MobileAppUnavailable() {
  const [status, setStatus] = useState<SendStatus>("idle");
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current) {
        clearTimeout(cooldownTimerRef.current);
        cooldownTimerRef.current = null;
      }
    };
  }, []);

  const handleSend = async () => {
    if (status === "loading" || status === "sent") return;
    setStatus("loading");
    try {
      const desktopUrl = window.location.origin;
      const res = await sendDesktopLinkApiV1MailSendDesktopLinkPost({
        desktop_url: desktopUrl,
      });
      if (res.status === 200) {
        setStatus("sent");
        cooldownTimerRef.current = setTimeout(() => {
          setStatus("idle");
          cooldownTimerRef.current = null;
        }, RESEND_COOLDOWN_MS);
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    }
  };

  const buttonLabel =
    status === "loading"
      ? "Sending…"
      : status === "sent"
        ? "Sent ✓ Check your inbox"
        : status === "error"
          ? "Couldn’t send — try again"
          : "Email me the link";

  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center bg-[var(--ege-canvas)] text-[var(--ege-text)] p-1 px-4 pt-[max(0.5rem,env(safe-area-inset-top))] pb-[max(0.5rem,env(safe-area-inset-bottom))]"
      role="status"
      aria-live="polite"
    >
      <PageCard className="w-full max-w-[22rem] p-6">
        <div className="flex flex-col items-center text-center">
          <div
            className="mb-5 flex h-14 w-14 items-center justify-center rounded-[12px] border border-[var(--ege-border)] bg-[var(--ege-surface)]"
            aria-hidden
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="h-8 w-8 text-[var(--ege-muted)]"
              xmlns="http://www.w3.org/2000/svg"
            >
              <rect
                x="7"
                y="3.5"
                width="10"
                height="17"
                rx="2.5"
                stroke="currentColor"
                strokeWidth="1.4"
              />
              <line
                x1="2"
                y1="2"
                x2="22"
                y2="22"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <h1 className="nova-text-p-large text-balance text-[var(--ege-text)]">
            NovaLearn is best on a computer.
          </h1>
          <p className="nova-text-label-small mt-3 text-balance text-[var(--ege-muted)]">
            We’ll email you a link so you can open NovaLearn on your laptop and
            keep going.
          </p>

          <Button
            type="button"
            size="xl"
            onClick={handleSend}
            disabled={status === "loading" || status === "sent"}
            isLoading={status === "loading"}
            aria-live="polite"
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-full bg-[var(--ege-accent)] text-white transition-all hover:bg-[var(--ege-accent-strong)] disabled:opacity-100"
          >
            {buttonLabel}
          </Button>

          {status === "sent" && (
            <p className="nova-text-label-tiny mt-3 text-[var(--ege-muted)]">
              Open the link from your inbox on a laptop or desktop browser.
            </p>
          )}
        </div>
      </PageCard>
    </div>
  );
}
