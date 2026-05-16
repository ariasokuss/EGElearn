import type { MetadataRoute } from "next";
import { seoPages } from "@/features/seo-content";
import { toAbsoluteUrl } from "@/shared/lib";

const weekly = "weekly" as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  const home: MetadataRoute.Sitemap[number] = {
    url: toAbsoluteUrl("/"),
    lastModified,
    changeFrequency: weekly,
    priority: 1,
  };

  return [
    home,
    ...seoPages.map((page) => ({
      url: toAbsoluteUrl(page.path),
      lastModified,
      changeFrequency: weekly,
      priority: page.priority ?? 0.7,
    })),
  ];
}
