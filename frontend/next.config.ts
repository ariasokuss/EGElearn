import type { NextConfig } from "next";

import { AUTH_ILLUSTRATION_SRC } from "./src/features/auth/ui/auth-decor/auth-decor-shell";

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
    rules: {
      "*.svg": {
        loaders: ["@svgr/webpack"],
        as: "*.js",
      },
    },
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: true,
  logging: {
    browserToTerminal: true,
    fetches: {
      fullUrl: true,
    },
  },
  experimental: {
    viewTransition: true,
  },
  async headers() {
    return [
      {
        source: AUTH_ILLUSTRATION_SRC,
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=604800, stale-while-revalidate=86400",
          },
        ],
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/a-level/:path*",
        destination: "/ege",
        permanent: true,
      },
    ];
  },
  async rewrites() {
    const apiUrl =
      process.env.NEXT_PUBLIC_API_URL ?? "https://dev-api.novalearn.ai";
    return [
      { source: "/health", destination: `${apiUrl}/health` },
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
    ];
  },
};

export default nextConfig;
