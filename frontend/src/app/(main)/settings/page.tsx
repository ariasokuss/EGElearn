import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Settings",
  description: "Private account settings in NovaLearn.",
  path: "/settings",
  indexable: false,
});

export default function SettingsIndexPage() {
  redirect("/settings/profile");
}
