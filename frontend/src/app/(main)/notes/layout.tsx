import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

export const metadata: Metadata = buildPageMetadata({
  title: "Notes",
  description: "Private notes and highlights saved in your NovaLearn account.",
  path: "/notes",
  indexable: false,
});

export default function NotesLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}
