import type { Metadata, Viewport } from "next";
import "@/shared/styles/globals.css";
import { dmSans, ibmPlexMono, inter, roboto } from "@/shared/config/fonts";
import { buildOrganizationSchema, buildWebsiteSchema, getPublicBaseUrl, THEME_STORAGE_KEY } from "@/shared/lib";
import { Providers } from "./providers";

const russianDescription =
  "NovaLearn помогает готовиться к ЕГЭ: предметы, уроки, практика, разбор ошибок и YandexGPT-помощник.";

const themeInitScript = `
try {
  var theme = localStorage.getItem("${THEME_STORAGE_KEY}");
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
  }
} catch (_) {}
`;

export const metadata: Metadata = {
  metadataBase: new URL(getPublicBaseUrl()),
  title: {
    default: "NovaLearn",
    template: "%s | NovaLearn",
  },
  description: russianDescription,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "NovaLearn",
    description: russianDescription,
    type: "website",
    locale: "ru_RU",
    siteName: "NovaLearn",
    url: "/",
  },
  twitter: {
    card: "summary_large_image",
    title: "NovaLearn",
    description: russianDescription,
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const organizationSchema = buildOrganizationSchema();
  const websiteSchema = buildWebsiteSchema();

  return (
    <html lang="ru" suppressHydrationWarning>
      <body
        className={`${roboto.variable} ${inter.variable} ${dmSans.variable} ${ibmPlexMono.variable} bg-[var(--ege-canvas)] antialiased`}
      >
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
        />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
