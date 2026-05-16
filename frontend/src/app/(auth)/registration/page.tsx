import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { RegistrationPage } from "@/views/registration";

export const metadata: Metadata = buildPageMetadata({
  title: "Registration",
  description: "Create your NovaLearn account.",
  path: "/registration",
  indexable: false,
});

export default function Registration() {
  return (
    <RegistrationPage />
  );
}
