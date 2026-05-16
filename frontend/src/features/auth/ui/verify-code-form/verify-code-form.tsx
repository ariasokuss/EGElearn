"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  cn,
  formatApiValidationError,
  setTokens,
  validateCode,
} from "@/shared/lib";
import {
  loginApiV1AuthLoginPost,
  verifyEmailApiV1MailVerifyEmailPost,
} from "@/shared/api/generated/api";
import { Button } from "@/shared/ui/button";

const inputClassName =
  "h-[36px] w-full rounded-full bg-white pl-[14px] pr-3 nova-text-label-small text-[#242529] placeholder:text-[#a1a1aa] nova-shadow-sm outline-none ring-transparent focus-visible:ring focus-visible:ring-offset-2 focus-visible:ring-offset-nova-500";
const inputErrorClassName = "ring-offset-2 ring-offset-red-500/30 border-red-200";

const buttonBase =
  "flex w-full items-center justify-center gap-2 rounded-full transition-all";

export interface VerifyCodeFormProps {
  email: string;
  password: string;
  resendSecondsLeft: number;
  onResend: () => Promise<void>;
  resendLoading: boolean;
}

export function VerifyCodeForm({
  email,
  password,
  resendSecondsLeft,
  onResend,
  resendLoading,
}: VerifyCodeFormProps) {
  const router = useRouter();
  const [errors, setErrors] = useState<{ code?: string; submit?: string }>({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const code = (formData.get("code") as string) ?? "";

    const codeError = validateCode(code);

    if (codeError) {
      setErrors({ code: codeError });
      return;
    }

    setErrors({});
    setLoading(true);

    try {
      const trimmedEmail = email.trim();
      const trimmedCode = code.trim();

      const verifyRes = await verifyEmailApiV1MailVerifyEmailPost({
        email: trimmedEmail,
        code: trimmedCode,
      });

      if (verifyRes.status !== 200) {
        setErrors({
          submit: formatApiValidationError(verifyRes.data, "Invalid or expired code"),
        });
        return;
      }

      const loginRes = await loginApiV1AuthLoginPost({
        email: trimmedEmail,
        password,
      });

      if (loginRes.status === 200) {
        const { access_token, refresh_token, expires_in } = loginRes.data;
        setTokens(access_token, refresh_token, expires_in ?? 3600);
        window.dispatchEvent(new CustomEvent("auth:tokens-updated"));
        router.prefetch("/");
        router.push("/");
        return;
      }

      if (loginRes.status === 422) {
        setErrors({
          submit: formatApiValidationError(
            loginRes.data,
            "Email verified. Sign in with your password."
          ),
        });
        return;
      }

      setErrors({
        submit: "Email verified. Please sign in.",
      });
      router.push("/auth");
    } catch {
      setErrors({ submit: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  const resendDisabled = resendSecondsLeft > 0 || resendLoading;
  const resendLabel = resendSecondsLeft > 0
      ? `Resend in ${resendSecondsLeft}s`
      : "Resend code";

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full max-w-[402px] flex-col gap-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <input
            id="code"
            name="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="Enter the code"
            className={cn(inputClassName, errors.code && inputErrorClassName)}
            maxLength={6}
          />
          {errors.code && (
            <p className="nova-text-label-tiny text-red-500">
              {errors.code}
            </p>
          )}
        </div>
        {errors.submit && (
          <p className="nova-text-label-tiny text-red-500">
            {errors.submit}
          </p>
        )}
        <p className="nova-text-label-small text-[#A1A1AA]">
          Code sent to {email}. Not receiving it?{" "}
          <Button
            type="button"
            size="l"
            disabled={resendDisabled}
            isLoading={resendLoading}
            onClick={() => {
              void onResend();
            }}
            className="text-[#3B82F6] tracking-[-0.014em] hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:opacity-50"
          >
            {resendLabel}
          </Button>
        </p>
      </div>
      <Button
        type="submit"
        size="l"
        disabled={loading}
        isLoading={loading}
        className={`${buttonBase} disabled:cursor-not-allowed disabled:opacity-60`}
      >
        Check the code
      </Button>
      <p className="text-center nova-text-label-small text-[#A1A1AA]">
        <Link
          href="/auth"
          className="text-[#3B82F6] tracking-[-0.014em] hover:opacity-80"
        >
          Back to Sign in
        </Link>
      </p>
    </form>
  );
}
