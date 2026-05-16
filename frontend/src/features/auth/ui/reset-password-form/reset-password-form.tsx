"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  cn,
  formatApiValidationError,
  validatePassword,
  validatePasswordMatch,
} from "@/shared/lib";
import { resetPasswordApiV1MailResetPasswordPost } from "@/shared/api/generated/api";
import { Button } from "@/shared/ui/button";

const inputClassName =
  "h-[36px] w-full rounded-full bg-white pl-[14px] pr-3 nova-text-label-small text-[#242529] placeholder:text-[#a1a1aa] nova-shadow-sm outline-none ring-transparent focus-visible:ring focus-visible:ring-offset-2 focus-visible:ring-offset-nova-500";
const inputErrorClassName = "ring-offset-2 ring-offset-red-500/30 border-red-200";

const buttonBase =
  "flex w-full items-center justify-center gap-2 rounded-full transition-all";

const RESET_TOKEN_LEN = 64;

interface ResetPasswordFormProps {
  token: string;
}

export function ResetPasswordForm({ token }: ResetPasswordFormProps) {
  const router = useRouter();
  const [errors, setErrors] = useState<{
    password?: string;
    passwordConfirm?: string;
    submit?: string;
  }>({});
  const [loading, setLoading] = useState(false);

  const tokenInvalid = token.length > 0 && token.length !== RESET_TOKEN_LEN;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const password = (formData.get("password") as string) ?? "";
    const passwordConfirm = (formData.get("passwordConfirm") as string) ?? "";

    const passwordError = validatePassword(password, "Password");
    const passwordConfirmError = validatePasswordMatch(password, passwordConfirm);

    if (passwordError || passwordConfirmError) {
      setErrors({
        password: passwordError,
        passwordConfirm: passwordConfirmError,
      });
      return;
    }

    if (token.length !== RESET_TOKEN_LEN) {
      setErrors({
        submit: "Invalid reset link. Request a new one from Restore access.",
      });
      return;
    }

    setErrors({});
    setLoading(true);

    try {
      const res = await resetPasswordApiV1MailResetPasswordPost({
        token,
        new_password: password,
      });

      if (res.status === 200) {
        router.push("/auth");
        return;
      }

      if (res.status === 422) {
        setErrors({
          submit: formatApiValidationError(
            res.data,
            "Could not reset password. Link may have expired."
          ),
        });
        return;
      }

      setErrors({ submit: "Could not reset password. Try again." });
    } catch {
      setErrors({ submit: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex w-full max-w-[402px] flex-col gap-6">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="nova-text-h-small-sb text-[#242529]">
          Set a new password
        </h1>
        <p className="nova-text-label-small text-[#A1A1AA]">
          Enter your new password below.
        </p>
      </div>
      {tokenInvalid && (
        <p className="rounded-2xl bg-amber-50 px-4 py-3 text-center nova-text-label-small text-amber-900">
          This reset link looks invalid or incomplete. Open the link from the
          latest email or request a new one.
        </p>
      )}
      <form
        onSubmit={(e) => {
          void handleSubmit(e);
        }}
        className="flex w-full flex-col gap-4"
      >
        <div className="flex flex-col gap-1">
          <input
            id="password"
            name="password"
            type="password"
            placeholder="New password"
            className={cn(inputClassName, errors.password && inputErrorClassName)}
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
        {errors.submit && (
          <p className="nova-text-label-tiny text-red-500">
            {errors.submit}
          </p>
        )}
        <Button
          type="submit"
          size="l"
          disabled={loading || tokenInvalid}
          isLoading={loading}
          className={`${buttonBase} mt-[8px] disabled:cursor-not-allowed disabled:opacity-60`}
        >
          Reset password
        </Button>
        <p className="text-center nova-text-label-small text-[#A1A1AA] tracking-[-0.014em]">
          <Link
            href="/auth"
            className="text-[#3B82F6] tracking-[-0.014em] hover:opacity-80"
          >
            Back to Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
