import type { FolderOut } from "@/shared/api/generated/model";

function parseFolderList(body: unknown): FolderOut[] {
  if (Array.isArray(body)) return body as FolderOut[];
  if (
    body &&
    typeof body === "object" &&
    "folders" in body &&
    Array.isArray((body as { folders: unknown }).folders)
  ) {
    return (body as { folders: FolderOut[] }).folders;
  }
  return [];
}

export async function listEgeFoldersApi(): Promise<FolderOut[]> {
  const res = await fetch("/api/v1/files/folders/ege", { method: "GET" });
  if (!res.ok) return [];
  const raw: unknown = await res.json();
  return parseFolderList(raw);
}

export async function reorderEgeFoldersApi(folderIds: string[]): Promise<boolean> {
  const res = await fetch("/api/v1/files/folders/ege/reorder", {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_ids: folderIds }),
  });
  return res.status >= 200 && res.status < 300;
}
