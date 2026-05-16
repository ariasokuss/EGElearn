import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { AuthCallbackPage } from "@/views/auth";

export const metadata: Metadata = buildPageMetadata({
  title: "Signing In",
  description: "Completing authentication for your NovaLearn account.",
  path: "/auth/callback",
  indexable: false,
});

export default function AuthCallbackRoute() {
  return <AuthCallbackPage />;
}
