"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/shared/ui/button";
import { EmailInput } from "@/shared/ui/email-input";
import {
  cn,
  formatApiValidationError,
  getPasswordResetRedirectUrl,
  validateEmail,
} from "@/shared/lib";
import { forgotPasswordApiV1MailForgotPasswordPost } from "@/shared/api/generated/api";

const inputClassName =
  "h-[36px] w-full rounded-full bg-white pl-[14px] pr-3 nova-text-label-small text-[#242529] placeholder:text-[#a1a1aa] nova-shadow-sm outline-none ring-transparent focus-visible:ring focus-visible:ring-offset-2 focus-visible:ring-offset-nova-500";
const inputErrorClassName = "ring-offset-2 ring-offset-red-500/30 border-red-200";

const buttonBase =
  "flex h-9 w-full items-center justify-center gap-2 rounded-full transition-all";

type Step = "email" | "sent";

export function RestoreForm() {
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<{ email?: string; submit?: string }>({});
  const [loading, setLoading] = useState(false);

  async function handleEmailSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const emailError = validateEmail(email);

    if (emailError) {
      setErrors({ email: emailError });
      return;
    }

    setErrors({});
    setLoading(true);

    try {
      const res = await forgotPasswordApiV1MailForgotPasswordPost({
        email: email.trim(),
        redirect_url: getPasswordResetRedirectUrl(),
      });

      if (res.status === 200) {
        setStep("sent");
        return;
      }

      if (res.status === 422) {
        setErrors({
          submit: formatApiValidationError(res.data, "Could not send reset link."),
        });
        return;
      }

      setErrors({ submit: "Could not send reset link. Try again." });
    } catch {
      setErrors({ submit: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  if (step === "sent") {
    return (
      <div className="flex w-full max-w-[402px] flex-col gap-4">
        <div className="mb-2 flex flex-col gap-4 text-center">
          <h1 className="nova-text-h-small-sb text-[#242529]">
            Check your email
          </h1>
          <p className="nova-text-label-small text-[#A1A1AA]">
            We have sent a password reset link to
            <br />
            <span className="text-[#A1A1AA]">{email}</span>
            <br />
          </p>
        </div>
        <Link
          href="/auth"
          className={`${buttonBase}`}
        >
          <Button
            size="l"
            type="button"
            className={buttonBase}
          >
            Back to Sign in
          </Button>
        </Link>
        <Button
          size="l"
          type="button"
          onClick={() => setStep("email")}
          className="text-[#3B82F6] hover:opacity-80"
        >
          Wrong email? Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="flex w-full max-w-[402px] flex-col gap-6">
      <div className="flex flex-col gap-4 text-center">
        <h1 className="nova-text-h-small-sb text-[#242529]">
          Restore access to your account
        </h1>
        <p className="nova-text-label-small text-[#A1A1AA]">
          Enter the email associated with your account. We will send you a link
          to reset your password.
        </p>
      </div>
      <form
        onSubmit={(e) => {
          void handleEmailSubmit(e);
        }}
        className="flex w-full flex-col gap-4"
      >
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
        {errors.submit && (
          <p className="nova-text-label-tiny text-red-500">
            {errors.submit}
          </p>
        )}
        <Button
          size="l"
          type="submit"
          disabled={loading}
          isLoading={loading}
          className={`${buttonBase} bg-[#f1ece9] text-[#242529] hover:bg-[#e8e3df] disabled:cursor-not-allowed disabled:opacity-60`}
        >
          Send reset link
        </Button>
        <p className="text-center nova-text-label-small text-[#A1A1AA] tracking-[-0.014em]">
          Remember your password?{" "}
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
