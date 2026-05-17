import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Terms and Privacy",
  description: "Private legal and privacy settings in NovaLearn.",
  path: "/settings/terms",
  indexable: false,
});

export default function SettingsTermsPage() {
  redirect("/settings/profile");
}
