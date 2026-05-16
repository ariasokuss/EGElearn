import type { Metadata } from "next";
import { buildPageMetadata } from "@/shared/lib";

import { FolderPage } from "@/views";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;

  return buildPageMetadata({
    title: "Folder",
    description: "Private NovaLearn folder workspace.",
    path: `/folders/${id}`,
    indexable: false,
  });
}

export default async function FolderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <FolderPage folderId={id} />;
}
