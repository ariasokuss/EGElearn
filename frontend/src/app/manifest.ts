import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "NovaLearn",
    short_name: "NovaLearn",
    description:
      "NovaLearn помогает готовиться к ЕГЭ: предметы, уроки, практика, разбор ошибок и YandexGPT-помощник.",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    icons: [
      {
        src: "/favicon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
