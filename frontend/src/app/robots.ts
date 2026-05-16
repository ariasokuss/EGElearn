import type { MetadataRoute } from "next";
import { getPublicBaseUrl } from "@/shared/lib";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = getPublicBaseUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/ege", "/ege/"],
        disallow: [
          "/auth",
          "/registration",
          "/restore",
          "/chat",
          "/folders",
          "/settings",
          "/notes",
          "/learning",
          "/api",
          "/*?*",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
