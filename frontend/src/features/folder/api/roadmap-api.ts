import type { RoadmapOut } from "@/shared/api/generated/model";

export async function getRoadmapApi(folderId: string): Promise<RoadmapOut | null> {
  const res = await fetch(`/api/v1/roadmap/folders/${folderId}`);
  if (!res.ok) return null;
  return res.json();
}
