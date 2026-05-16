import type { Metadata } from "next";
import { AuthLayoutContent } from "@/features/auth";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Authentication",
  description: "NovaLearn authentication area.",
  path: "/auth",
  indexable: false,
});

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex h-screen overflow-hidden bg-[#FFFFFF] py-4 pr-4">
      <AuthLayoutContent>{children}</AuthLayoutContent>
    </div>
  );
}
