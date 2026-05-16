import type { Metadata } from "next";
import { headers } from "next/headers";
import { AuthGuard } from "@/features/auth";
import { buildPageMetadata, detectIsPhoneUserAgent } from "@/shared/lib";
import { MainAppChrome } from "@/widgets";

export const metadata: Metadata = buildPageMetadata({
  title: "App",
  description: "Private NovaLearn application area.",
  path: "/",
  indexable: false,
});

export default async function MainLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const ua = (await headers()).get("user-agent") ?? "";
  const isPhoneFromUa = detectIsPhoneUserAgent(ua);

  return (
    <AuthGuard>
      <MainAppChrome isPhoneFromUa={isPhoneFromUa}>{children}</MainAppChrome>
    </AuthGuard>
  );
}
