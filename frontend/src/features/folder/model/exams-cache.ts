import type { ExamOut } from "@/shared/api/generated/model";

const memoryByFolder = new Map<string, ExamOut[]>();

function storageKey(folderId: string): string {
  return `nl.folderExams.v1:${folderId}`;
}

export function readCachedExams(folderId: string): ExamOut[] | null {
  if (!folderId) return null;

  const fromMem = memoryByFolder.get(folderId);
  if (fromMem) return fromMem;

  if (typeof window === "undefined") return null;

  try {
    const raw = sessionStorage.getItem(storageKey(folderId));
    if (raw == null) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return null;
    memoryByFolder.set(folderId, parsed as ExamOut[]);
    return parsed as ExamOut[];
  } catch {
    return null;
  }
}

export function writeCachedExams(folderId: string, exams: ExamOut[]): void {
  if (!folderId) return;

  memoryByFolder.set(folderId, exams);

  if (typeof window === "undefined") return;

  try {
    sessionStorage.setItem(storageKey(folderId), JSON.stringify(exams));
  } catch {
  }
}
