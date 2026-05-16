import Dexie, { type EntityTable } from "dexie";

import type {
  LessonDetailRead,
  SessionHistoryItem,
} from "@/shared/api/generated/model";

type CachedLessonDetail = {
  lessonId: string;
  data: LessonDetailRead;
  updatedAt: number;
};

type CachedFeynmanHistory = {
  lessonId: string;
  history: SessionHistoryItem[];
  updatedAt: number;
};

const db = new Dexie("novalearn-lessons") as Dexie & {
  lessonDetails: EntityTable<CachedLessonDetail, "lessonId">;
  feynmanHistories: EntityTable<CachedFeynmanHistory, "lessonId">;
};

db.version(1).stores({
  lessonDetails: "lessonId, updatedAt",
  feynmanHistories: "lessonId, updatedAt",
});

const memLessons = new Map<string, LessonDetailRead>();
const memHistories = new Map<string, SessionHistoryItem[]>();

export function getMemoryLesson(lessonId: string): LessonDetailRead | null {
  return memLessons.get(lessonId) ?? null;
}

export function getMemoryFeynmanHistory(lessonId: string): SessionHistoryItem[] | null {
  return memHistories.get(lessonId) ?? null;
}

export async function getCachedLesson(lessonId: string): Promise<LessonDetailRead | null> {
  const mem = memLessons.get(lessonId);
  if (mem) return mem;
  try {
    const row = await db.lessonDetails.get(lessonId);
    if (row?.data) memLessons.set(lessonId, row.data);
    return row?.data ?? null;
  } catch {
    return null;
  }
}

export async function cacheLesson(lessonId: string, data: LessonDetailRead): Promise<void> {
  memLessons.set(lessonId, data);
  try {
    await db.lessonDetails.put({ lessonId, data, updatedAt: Date.now() });
  } catch {
    // silent
  }
}

export async function getCachedFeynmanHistory(lessonId: string): Promise<SessionHistoryItem[] | null> {
  const mem = memHistories.get(lessonId);
  if (mem) return mem;
  try {
    const row = await db.feynmanHistories.get(lessonId);
    if (row?.history) memHistories.set(lessonId, row.history);
    return row?.history ?? null;
  } catch {
    return null;
  }
}

export async function cacheFeynmanHistory(
  lessonId: string,
  history: SessionHistoryItem[],
): Promise<void> {
  memHistories.set(lessonId, history);
  try {
    await db.feynmanHistories.put({ lessonId, history, updatedAt: Date.now() });
  } catch {
    // silent
  }
}

/** Drop in-memory + IndexedDB caches so the next load refetches from the API. */
export async function clearLessonCaches(lessonId: string): Promise<void> {
  memLessons.delete(lessonId);
  memHistories.delete(lessonId);
  try {
    await db.lessonDetails.delete(lessonId);
    await db.feynmanHistories.delete(lessonId);
  } catch {
    // silent
  }
}
