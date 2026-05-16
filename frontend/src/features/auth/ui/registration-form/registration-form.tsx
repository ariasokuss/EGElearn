"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GoogleSignInButton } from "../google-sign-in";
import { Button } from "@/shared/ui/button";
import { EmailInput } from "@/shared/ui/email-input";
import { VerifyCodeForm } from "../verify-code-form";
import { useResendCooldown } from "../../model/use-resend-cooldown";
import {
  cn,
  formatApiValidationError,
  validateEmail,
  validatePassword,
  validatePasswordMatch,
} from "@/shared/lib";
import {
  registerApiV1AuthRegisterPost,
  sendVerificationApiV1MailSendVerificationPost,
} from "@/shared/api/generated/api";
import { getRefCode, getVisitorId } from "@/shared/lib/referral-storage";

const inputClassName =
  "h-[36px] w-full rounded-full bg-white pl-[14px] pr-3 nova-text-label-small text-[#242529] placeholder:text-[#a1a1aa] nova-shadow-sm outline-none ring-transparent focus-visible:ring focus-visible:ring-offset-2 focus-visible:ring-offset-nova-500";
const inputErrorClassName = "ring-offset-2 ring-offset-red-500/30 border-red-200";

const buttonBase =
  "flex w-full items-center justify-center gap-2 rounded-full transition-all";

type Step = "form" | "verify";

export function RegistrationForm() {
  const [step, setStep] = useState<Step>("form");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{
    email?: string;
    password?: string;
    passwordConfirm?: string;
    submit?: string;
  }>({});
  const [signupLoading, setSignupLoading] = useState(false);
  const [verifyBanner, setVerifyBanner] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);
  const { secondsLeft, start } = useResendCooldown(60);
  const [googleError, setGoogleError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("google_error");
    if (!q) return;

    const timeoutId = window.setTimeout(() => setGoogleError(q), 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  async function handleResend() {
    const emailTrim = email.trim();
    setResendLoading(true);
    setVerifyBanner(null);
    try {
      const sendRes = await sendVerificationApiV1MailSendVerificationPost({
        email: emailTrim,
      });
      if (sendRes.status === 200) {
        start(60);
      } else {
        setVerifyBanner(
          formatApiValidationError(sendRes.data, "Could not resend the code.")
        );
      }
    } catch {
      setVerifyBanner("Network error. Try again.");
    } finally {
      setResendLoading(false);
    }
  }

  async function handleSignupSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const passwordValue = (formData.get("password") as string) ?? "";
    const passwordConfirm = (formData.get("passwordConfirm") as string) ?? "";

    const emailError = validateEmail(email);
    const passwordError = validatePassword(passwordValue, "Password");
    const passwordConfirmError = validatePasswordMatch(
      passwordValue,
      passwordConfirm
    );

    if (emailError || passwordError || passwordConfirmError) {
      setErrors({
        email: emailError,
        password: passwordError,
        passwordConfirm: passwordConfirmError,
      });
      return;
    }

    setErrors({});
    setSignupLoading(true);

    const emailTrim = email.trim();

    try {
      const regRes = await registerApiV1AuthRegisterPost({
        email: emailTrim,
        password: passwordValue,
        ref_code: getRefCode() ?? undefined,
        visitor_id: getVisitorId() ?? undefined,
      } as Parameters<typeof registerApiV1AuthRegisterPost>[0]);

      if (regRes.status !== 201) {
        const fallback = "Registration failed. Please try again.";
        const msg = formatApiValidationError(regRes.data, fallback);
        const showOnEmail =
          regRes.status === 422 ||
          (msg !== fallback && /email/i.test(msg));
        setErrors(showOnEmail ? { email: msg } : { submit: msg });
        return;
      }

      // Transition to verify step immediately — don't wait for email send
      setPassword(passwordValue);
      setStep("verify");
      start(60);

      // Fire send-verification in background (non-blocking)
      sendVerificationApiV1MailSendVerificationPost({
        email: emailTrim,
      }).then((sendRes) => {
        if (sendRes.status !== 200) {
          setVerifyBanner(
            formatApiValidationError(
              sendRes.data,
              "Could not send the code. Use Resend to try again."
            )
          );
        }
      }).catch(() => {
        setVerifyBanner("Could not send the code. Use Resend to try again.");
      });
    } catch {
      setErrors({ submit: "Network error. Please try again." });
    } finally {
      setSignupLoading(false);
    }
  }

  if (step === "verify") {
    return (
      <div className="flex w-full max-w-[402px] flex-col gap-6">
        <div className="flex flex-col gap-4 text-center">
          <h1 className="nova-text-h-small-sb text-[#242529]">
            Enter the code sent to your email
          </h1>
          <p className="nova-text-label-small text-[#A1A1AA]">
            We have sent the confirmation code to the email
            <br />
            <span className="text-[#A1A1AA]">{email}</span>
          </p>
        </div>
        {verifyBanner && (
          <p className="rounded-2xl bg-amber-50 px-4 py-3 text-center nova-text-label-small text-amber-900">
            {verifyBanner}
          </p>
        )}
        <VerifyCodeForm
          email={email}
          password={password}
          resendSecondsLeft={secondsLeft}
          onResend={handleResend}
          resendLoading={resendLoading}
        />
      </div>
    );
  }

  return (
    <div className="flex w-full max-w-[402px] flex-col gap-6">
      <h1 className="text-center nova-text-h-small-sb text-[#242529]">
        Registration
      </h1>
      <form
        onSubmit={(e) => {
          void handleSignupSubmit(e);
        }}
        className="flex w-full flex-col gap-6"
      >
        {googleError && (
          <p className="nova-text-label-tiny text-red-500">
            {googleError}
          </p>
        )}
        <GoogleSignInButton label="Continue with Google" />
        <div className="relative flex items-center">
          <div className="h-px flex-1 bg-[#f4f4f5]" />
          <div className="flex h-5 w-9 shrink-0 items-center justify-center rounded-[24px] bg-[#FAF9F7]">
            <span className="nova-text-label-small text-[#A1A1AA]">
              <p className="mb-1">or</p>
            </span>
          </div>
          <div className="h-px flex-1 bg-[#f4f4f5]" />
        </div>
        <div className="flex flex-col gap-4">
          <p className="nova-text-label-small text-[#242529]">
            Enter your details
          </p>
          <div className="flex flex-col gap-1">
            <EmailInput
              id="email"
              name="email"
              placeholder="Email"
              className={cn(inputClassName, errors.email && inputErrorClassName)}
              onChange={(e) => setEmail(e.target.value)}
            />
            {errors.email && (
              <p className="nova-text-label-tiny text-red-500">
                {errors.email}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <input
              id="password"
              name="password"
              type="password"
              placeholder="Create a password"
              className={cn(
                inputClassName,
                errors.password && inputErrorClassName
              )}
              autoComplete="new-password"
            />
            {errors.password && (
              <p className="nova-text-label-tiny text-red-500">
                {errors.password}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <input
              id="passwordConfirm"
              name="passwordConfirm"
              type="password"
              placeholder="Repeat the password"
              className={cn(
                inputClassName,
                errors.passwordConfirm && inputErrorClassName
              )}
              autoComplete="new-password"
            />
            {errors.passwordConfirm && (
              <p className="nova-text-label-tiny text-red-500">
                {errors.passwordConfirm}
              </p>
            )}
          </div>
        </div>
        {errors.submit && (
          <p className="nova-text-label-tiny text-red-500">
            {errors.submit}
          </p>
        )}
        <Button
          type="submit"
          size="l"
          disabled={signupLoading}
          isLoading={signupLoading}
          className={`${buttonBase} disabled:cursor-not-allowed disabled:opacity-60`}
        >
          Create account
        </Button>
        <p className="text-center nova-text-label-small text-[#A1A1AA]">
          Already have an account?{" "}
          <Link
            href="/auth"
            className="text-[#3B82F6] tracking-[-0.014em] hover:opacity-80"
          >
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
