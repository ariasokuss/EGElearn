"use client";

import { useAuth } from "@/features/auth";
import { MainAppChrome } from "@/widgets";
import { PageLoader, PageCard } from "@/shared/ui";
import { HomePage } from "@/views";
import { LandingPage } from "./landing-page";

type HomeRouteProps = {
  isPhoneFromUa: boolean;
};

export function HomeRoute({ isPhoneFromUa }: HomeRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isAuthenticated) {
    return <LandingPage />;
  }

  return (
    <MainAppChrome isPhoneFromUa={isPhoneFromUa}>
      <PageCard className="flex-1">
        <HomePage />
      </PageCard>
    </MainAppChrome>
  );
}
