import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Upgrade Plan",
  description: "Private subscription and plan upgrade settings in NovaLearn.",
  path: "/settings/upgrade-plan",
  indexable: false,
});

export default function SettingsUpgradePlanPage() {
  redirect("/settings/profile");
}
