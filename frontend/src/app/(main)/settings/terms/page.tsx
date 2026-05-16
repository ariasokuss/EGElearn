import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { TermsPanel } from "@/features/settings";

export const metadata: Metadata = buildPageMetadata({
  title: "Условия и приватность",
  description: "Правовые условия и приватность NovaLearn.",
  path: "/settings/terms",
  indexable: false,
});

export default function SettingsTermsPage() {
  return (
    <TermsPanel />
  );
}
