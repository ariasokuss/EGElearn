import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { ProfilePanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Профиль",
  description: "Настройки профиля NovaLearn.",
  path: "/settings/profile",
  indexable: false,
});

export default function SettingsProfilePage() {
  return (
    <ProfilePanel />
  );
}
