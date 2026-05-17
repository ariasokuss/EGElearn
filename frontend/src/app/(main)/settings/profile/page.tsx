import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { ProfilePanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Profile Settings",
  description: "Private profile settings in NovaLearn.",
  path: "/settings/profile",
  indexable: false,
});

export default function SettingsProfilePage() {
  return (
    <ProfilePanel />
  );
}
