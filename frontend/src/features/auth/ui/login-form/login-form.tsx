"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GoogleSignInButton } from "../google-sign-in";
import { Button } from "@/shared/ui/button";
import { EmailInput } from "@/shared/ui/email-input";
import { cn, setTokens, validateEmailForLogin } from "@/shared/lib";
import { loginApiV1AuthLoginPost } from "@/shared/api/generated/api";

const inputClassName =
  "h-[36px] w-full rounded-full bg-white pl-[14px] pr-3 nova-text-label-small text-[#242529] placeholder:text-[#a1a1aa] nova-shadow-sm outline-none ring-transparent focus-visible:ring focus-visible:ring-offset-2 focus-visible:ring-offset-nova-500";
const inputErrorClassName = "ring-offset-2 ring-offset-red-500/30 border-red-200";

const buttonBase =
  "flex w-full items-center justify-center gap-2 rounded-full transition-all";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<{ email?: string; submit?: string }>({});
  const [loading, setLoading] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("google_error");
    if (!q) return;

    const timeoutId = window.setTimeout(() => setGoogleError(q), 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const emailError = validateEmailForLogin(email);

    if (emailError) {
      setErrors({ email: emailError });
      return;
    }

    const formData = new FormData(e.currentTarget);
    const password = (formData.get("password") as string) ?? "";

    setErrors({});
    setLoading(true);

    try {
      const res = await loginApiV1AuthLoginPost({ email: email.trim(), password });

      if (res.status === 200) {
        const { access_token, refresh_token, expires_in } = res.data;
        setTokens(access_token, refresh_token, expires_in ?? 3600);
        window.dispatchEvent(new CustomEvent("auth:tokens-updated"));
        router.prefetch("/");
        router.push("/");
        return;
      }
      if (res.status === 422) {
        const detail = (res.data as { detail?: Array<{ msg?: string }> })?.detail;
        const msg = detail?.[0]?.msg ?? "Invalid email or password";
        setErrors({ submit: msg });
      } else {
        setErrors({ submit: "Invalid email or password" });
      }
    } catch {
      setErrors({ submit: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-[402px] flex-col gap-4">
      {googleError && (
        <p className="nova-text-label-tiny text-red-500">
          {googleError}
        </p>
      )}
      <GoogleSignInButton label="Sign in with Google" />
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
        <input
          id="password"
          name="password"
          type="password"
          placeholder="Password"
          className={inputClassName}
          autoComplete="current-password"
        />
        {errors.submit && (
          <p className="nova-text-label-tiny text-red-500">
            {errors.submit}
          </p>
        )}
      </div>
      <Button
        type="submit"
        size="l"
        disabled={loading}
        isLoading={loading}
        className={`${buttonBase} mt-2 disabled:opacity-60 disabled:cursor-not-allowed`}
      >
        Log in
      </Button>
      <div className="flex flex-col items-center gap-1 text-center">
        <p className="nova-text-label-small text-[#A1A1AA]">
          Having trouble logging in?{" "}
          <Link
            href="/registration"
            className="text-[#3B82F6] tracking-[-0.014em] hover:opacity-80"
          >
            Register
          </Link>{" "}
          or
        </p>
        <Link
          href="/restore"
          className="nova-text-label-small tracking-[-0.014em] text-[#3B82F6] hover:opacity-80"
        >
          restore access to the account
        </Link>
      </div>
    </form>
  );
}
