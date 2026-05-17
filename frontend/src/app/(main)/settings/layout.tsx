import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { SettingsShell } from "@/features/settings";
import { PageCard } from "@/shared/ui";

export const metadata: Metadata = buildPageMetadata({
  title: "Settings",
  description: "Private account settings in NovaLearn.",
  path: "/settings",
  indexable: false,
});

export default function SettingsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
  <PageCard className="flex-1">
    <SettingsShell>{children}</SettingsShell>
  </PageCard>
  );
}
