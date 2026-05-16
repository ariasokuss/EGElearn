"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AuthDecor } from "../auth-decor/auth-decor";
import { AuthIllustrationPreload } from "../auth-decor/auth-illustration-preload";
import { PageLoader } from "@/shared/ui/page-loader";
import { useAuth } from "../../model/auth-context";

type AuthLayoutContentProps = {
  children: React.ReactNode;
};

export function AuthLayoutContent({ children }: AuthLayoutContentProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.prefetch("/");
      router.replace("/");
    }
  }, [isLoading, isAuthenticated, router]);

  return (
    <>
      <AuthIllustrationPreload />
      {isAuthenticated ? (
        <PageLoader showText={false} />
      ) : (
        <>
          <div className="flex min-h-0 flex-1 items-center justify-center px-12">
            {children}
          </div>
          <AuthDecor />
        </>
      )}
    </>
  );
}
