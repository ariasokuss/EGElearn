import type { Metadata } from "next";

type BuildMetadataParams = {
  title: string;
  description: string;
  path: string;
  indexable?: boolean;
  type?: "website" | "article";
};

const PROD_BASE_URL = "https://novalearn.ai";
const DEV_BASE_URL = "https://dev.novalearn.ai";
const LOCAL_FALLBACK_URL = "http://localhost:3000";

function normalizeBaseUrl(rawUrl: string): string {
  const trimmed = rawUrl.trim();
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  const url = new URL(withProtocol);

  if (url.pathname !== "/") {
    url.pathname = "/";
  }

  return url.toString().replace(/\/$/, "");
}

export function getPublicBaseUrl() {
  const explicitAppUrl = process.env.NEXT_PUBLIC_APP_URL;
  if (explicitAppUrl) {
    return normalizeBaseUrl(explicitAppUrl);
  }

  if (process.env.NODE_ENV === "production") {
    return PROD_BASE_URL;
  }

  if (process.env.CI) {
    return DEV_BASE_URL;
  }

  return LOCAL_FALLBACK_URL;
}

export function toAbsoluteUrl(path: string) {
  return `${getPublicBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export function buildRobotsPolicy(indexable: boolean): Metadata["robots"] {
  if (indexable) {
    return {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
      },
    };
  }

  return {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  };
}

export function buildPageMetadata({
  title,
  description,
  path,
  indexable = true,
  type = "website",
}: BuildMetadataParams): Metadata {
  const canonical = toAbsoluteUrl(path);
  const robots = buildRobotsPolicy(indexable);

  return {
    title,
    description,
    alternates: {
      canonical,
    },
    robots,
    openGraph: {
      title,
      description,
      url: canonical,
      siteName: "NovaLearn",
      type,
      locale: "ru_RU",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export function buildOrganizationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "NovaLearn",
    url: getPublicBaseUrl(),
    logo: toAbsoluteUrl("/favicon.svg"),
  };
}

export function buildWebsiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "NovaLearn",
    url: getPublicBaseUrl(),
  };
}

export function buildBreadcrumbSchema(items: Array<{ name: string; path: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: toAbsoluteUrl(item.path),
    })),
  };
}

export function buildFaqSchema(items: Array<{ question: string; answer: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: item.answer,
      },
    })),
  };
}
