export type HighlightRead = {
  id: string;
  user_id: string;
  lesson_id: string;
  text: string;
  comment: string | null;
  type: "highlight" | "note";
  created_at: string;
  updated_at: string;
};

export async function createHighlightApi(
  lessonId: string,
  text: string,
  comment?: string,
): Promise<HighlightRead | null> {
  const res = await fetch(`/api/v1/learning/lessons/${lessonId}/highlights`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, comment: comment ?? null }),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function listLessonHighlightsApi(
  lessonId: string,
): Promise<HighlightRead[]> {
  const res = await fetch(`/api/v1/learning/lessons/${lessonId}/highlights`);
  if (!res.ok) return [];
  return res.json();
}

export async function listAllHighlightsApi(
  type?: "highlight" | "note",
): Promise<HighlightRead[]> {
  const url = type
    ? `/api/v1/learning/highlights?type=${type}`
    : "/api/v1/learning/highlights";
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function patchHighlightApi(
  highlightId: string,
  comment: string | null,
): Promise<HighlightRead | null> {
  const res = await fetch(`/api/v1/learning/highlights/${highlightId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function deleteHighlightApi(highlightId: string): Promise<boolean> {
  const res = await fetch(`/api/v1/learning/highlights/${highlightId}`, {
    method: "DELETE",
  });
  return res.ok;
}
