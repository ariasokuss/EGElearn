import type { Metadata } from "next";
import { getSeoPage, PublicContentPage } from "@/features/seo-content";
import { buildPageMetadata } from "@/shared/lib";

const page = getSeoPage("ege");

export const metadata: Metadata = buildPageMetadata({
  title: page.metadataTitle,
  description: page.metadataDescription,
  path: page.path,
});

export default function EgePage() {
  return (
    <PublicContentPage
      title={page.pageTitle}
      intro={page.intro}
      breadcrumbs={page.breadcrumbs}
      sections={page.sections}
      relatedLinks={page.relatedLinks}
      faq={page.faq}
    />
  );
}
