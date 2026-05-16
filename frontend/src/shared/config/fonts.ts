import localFont from "next/font/local";

export const roboto = localFont({
  src: [
    {
      path: "../assets/fonts/roboto-400.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "../assets/fonts/roboto-500.woff2",
      weight: "500",
      style: "normal",
    },
  ],
  variable: "--font-roboto",
  display: "swap",
  preload: false,
  fallback: ["Segoe UI", "Arial", "sans-serif"],
});

export const inter = localFont({
  src: [
    {
      path: "../assets/fonts/inter-400.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "../assets/fonts/inter-500.woff2",
      weight: "500",
      style: "normal",
    },
    {
      path: "../assets/fonts/inter-600.woff2",
      weight: "600",
      style: "normal",
    },
  ],
  variable: "--font-inter",
  display: "swap",
  fallback: ["Segoe UI", "Arial", "sans-serif"],
});

export const dmSans = localFont({
  src: [
    {
      path: "../assets/fonts/dm-sans-400.woff2",
      weight: "400",
      style: "normal",
    },
  ],
  variable: "--font-dm-sans",
  display: "swap",
  preload: false,
  fallback: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
});

export const ibmPlexMono = localFont({
  src: [
    {
      path: "../assets/fonts/ibm-plex-mono-400.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "../assets/fonts/ibm-plex-mono-400-italic.woff2",
      weight: "400",
      style: "italic",
    },
    {
      path: "../assets/fonts/ibm-plex-mono-500.woff2",
      weight: "500",
      style: "normal",
    },
    {
      path: "../assets/fonts/ibm-plex-mono-500-italic.woff2",
      weight: "500",
      style: "italic",
    },
  ],
  variable: "--font-ibm-plex-mono",
  display: "swap",
  preload: false,
  fallback: ["Consolas", "Courier New", "monospace"],
});
