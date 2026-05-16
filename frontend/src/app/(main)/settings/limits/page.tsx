import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { LimitsPanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Лимиты",
  description: "Лимиты использования NovaLearn.",
  path: "/settings/limits",
  indexable: false,
});

export default function SettingsLimitsPage() {
  return (
      <LimitsPanel />
  );
}
