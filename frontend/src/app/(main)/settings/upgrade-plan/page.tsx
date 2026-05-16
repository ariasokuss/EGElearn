import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { UpgradePanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Тариф",
  description: "Настройки тарифа NovaLearn.",
  path: "/settings/upgrade-plan",
  indexable: false,
});

export default function SettingsUpgradePlanPage() {
  return (
    <UpgradePanel />
  );
}
