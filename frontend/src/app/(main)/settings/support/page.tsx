import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Support Settings",
  description: "Private support and help settings in NovaLearn.",
  path: "/settings/support",
  indexable: false,
});

export default function SettingsSupportPage() {
  redirect("/settings/profile");
}
