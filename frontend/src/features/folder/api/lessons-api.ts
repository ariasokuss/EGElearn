import type {
  CompleteStepResponse,
  LessonDetailRead,
  LessonListSchema,
  LessonProgressRead,
  LessonResultRead,
  LessonSchema,
} from "@/shared/api/generated/model";
import { listLastAccessedLessonsApiV1LearningLessonsLastAccessedGet } from "@/shared/api/generated/api";

export async function getLessonsApi(): Promise<LessonSchema[]> {
  const res = await fetch("/api/v1/learning/lessons?shared=true");
  if (!res.ok) return [];
  return res.json();
}

/** Last-accessed list for one folder only; requires the same folder context as {@link getLessonDetailApi}. */
export async function getLastAccessedLessonsApi(folderId: string): Promise<LessonListSchema[]> {
  const response = await listLastAccessedLessonsApiV1LearningLessonsLastAccessedGet({
    folder_id: folderId,
  });
  if (response.status !== 200) return [];
  const data = response.data;
  return Array.isArray(data) ? data : [];
}

/**
 * Loads lesson detail. The backend records “last access” for this folder when `folderId` is set
 * (must match the folder you are viewing). No separate “touch” endpoint.
 */
export async function getLessonDetailApi(
  lessonId: string,
  folderId?: string | null,
): Promise<LessonDetailRead | null> {
  const q = new URLSearchParams();
  if (folderId) q.set("folder_id", folderId);
  const qs = q.toString();
  const res = await fetch(
    `/api/v1/learning/lessons/${lessonId}${qs ? `?${qs}` : ""}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function completeStepApi(lessonId: string, step: number): Promise<CompleteStepResponse | null> {
  const res = await fetch(`/api/v1/learning/lessons/${lessonId}/complete-step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step }),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function getLessonResultsApi(lessonId: string): Promise<LessonResultRead | null> {
  const res = await fetch(`/api/v1/learning/lessons/${lessonId}/results`);
  if (!res.ok) return null;
  return res.json();
}

export async function getLessonProgressApi(lessonId: string): Promise<LessonProgressRead | null> {
  const res = await fetch(`/api/v1/learning/lessons/${lessonId}/progress`);
  if (!res.ok) return null;
  return res.json();
}
