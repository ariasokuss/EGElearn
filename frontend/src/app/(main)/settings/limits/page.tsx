import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Usage Limits",
  description: "Private usage limits and quota details in NovaLearn.",
  path: "/settings/limits",
  indexable: false,
});

export default function SettingsLimitsPage() {
  redirect("/settings/profile");
}
