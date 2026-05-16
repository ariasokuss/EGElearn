import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";
import { RestorePage } from "@/views/restore";

export const metadata: Metadata = buildPageMetadata({
  title: "Restore Access",
  description: "Restore access to your NovaLearn account.",
  path: "/restore",
  indexable: false,
});

export default function Restore() {
  return <RestorePage />;
}
