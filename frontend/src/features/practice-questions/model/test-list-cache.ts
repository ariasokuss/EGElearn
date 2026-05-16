import type { TemplateWithProgress } from "../api";
import type { TestSessionTypes } from "./types";
import type { TestSessionOut } from "@/shared/api/generated/model";

export type CachedTestLists = {
  sessions?: TestSessionOut[];
  templates?: TemplateWithProgress[];
};

const testListsCache = new Map<string, CachedTestLists>();

function cacheKey(folderId: string, type: TestSessionTypes): string {
  return `${folderId}:${type}`;
}

export function readCachedTestLists(folderId: string, type: TestSessionTypes): CachedTestLists | null {
  if (!folderId) return null;
  return testListsCache.get(cacheKey(folderId, type)) ?? null;
}

export function writeCachedTestSessions(
  folderId: string,
  type: TestSessionTypes,
  sessions: TestSessionOut[],
): void {
  if (!folderId) return;
  const key = cacheKey(folderId, type);
  const current = testListsCache.get(key) ?? {};
  testListsCache.set(key, { ...current, sessions });
}

export function writeCachedTestTemplates(
  folderId: string,
  type: TestSessionTypes,
  templates: TemplateWithProgress[],
): void {
  if (!folderId) return;
  const key = cacheKey(folderId, type);
  const current = testListsCache.get(key) ?? {};
  testListsCache.set(key, { ...current, templates });
}
