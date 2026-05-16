import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Learning",
  description: "Private learning workspace inside your NovaLearn account.",
  path: "/learning",
  indexable: false,
});

export default function LearningPage() {
  return <div />;
}
