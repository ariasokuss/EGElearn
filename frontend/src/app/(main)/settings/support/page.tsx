import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { SupportPanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Поддержка",
  description: "Поддержка NovaLearn.",
  path: "/settings/support",
  indexable: false,
});

export default function SettingsSupportPage() {
  return (
    <SupportPanel />
  );
}
