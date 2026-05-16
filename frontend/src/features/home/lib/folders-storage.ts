import type { FolderOut } from "@/shared/api/generated/model";

const STORAGE_KEY_PREFIX = "novalearn_folders_cache_";
const FIXED_EGE_PREFIX = "novalearn_folders_fixed_ege_";
const LEGACY_FIXED_PREFIXES = [
  "novalearn_folders_fixed_a_level_",
  "novalearn_folders_fixed_gcse_",
] as const;
const FOLDERS_CACHE_PREFIXES = [
  STORAGE_KEY_PREFIX,
  FIXED_EGE_PREFIX,
  ...LEGACY_FIXED_PREFIXES,
] as const;

function readJsonFolders(raw: string | null): FolderOut[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as FolderOut[]) : [];
  } catch {
    return [];
  }
}

export function getFoldersFromStorage(userId: string): FolderOut[] {
  if (typeof window === "undefined") return [];
  return readJsonFolders(localStorage.getItem(STORAGE_KEY_PREFIX + userId));
}

export function setFoldersToStorage(userId: string, folders: FolderOut[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      STORAGE_KEY_PREFIX + userId,
      JSON.stringify(folders)
    );
  } catch {
    /* ignore */
  }
}

export function getFixedFoldersEgeFromStorage(userId: string): FolderOut[] {
  if (typeof window === "undefined") return [];
  return readJsonFolders(localStorage.getItem(FIXED_EGE_PREFIX + userId));
}

export function setFixedFoldersEgeToStorage(
  userId: string,
  folders: FolderOut[]
): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(FIXED_EGE_PREFIX + userId, JSON.stringify(folders));
  } catch {
    /* ignore */
  }
}

export function clearFoldersCache(userId: string): void {
  if (typeof window === "undefined") return;
  FOLDERS_CACHE_PREFIXES.forEach((prefix) => {
    localStorage.removeItem(prefix + userId);
  });
}

export function clearAllFoldersCaches(): void {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && FOLDERS_CACHE_PREFIXES.some((prefix) => k.startsWith(prefix))) {
      keys.push(k);
    }
  }
  keys.forEach((k) => localStorage.removeItem(k));
}
