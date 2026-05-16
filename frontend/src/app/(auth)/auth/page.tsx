import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { AuthPage } from "@/views/auth";

export const metadata: Metadata = buildPageMetadata({
  title: "Login",
  description: "Sign in to your NovaLearn account.",
  path: "/auth",
  indexable: false,
});

export default function Auth() {
  return (
    <AuthPage />
  );
}
