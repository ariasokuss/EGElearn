export type NoteStatus = "see" | "review" | "complete";

export type ReviewQuestion = {
  question: string;
  total_marks: number;
  model_answer: string;
};

export type FeedbackNote = {
  id: string;
  source_type: string;
  source_session_id: string;
  source_answer_id: string | null;
  question_id: string | null;
  severity: string;
  topic: string;
  mistake: string;
  correction: string;
  status: NoteStatus;
  review_question: ReviewQuestion | null;
  created_at: string;
};

export type FeedbackSummary = {
  see: number;
  review: number;
  complete: number;
  total: number;
};

export type NoteAnswerResult = {
  is_correct: boolean;
  earned_marks: number;
  total_marks: number;
  feedback: string;
  recommendations: string;
};

/** GET /api/v1/feedback/summary */
export async function getFeedbackSummary(folder_id: string): Promise<FeedbackSummary | null> {
  const url = `/api/v1/feedback/summary?folder_id=${folder_id}`
  const res = await fetch(url);
  if (!res.ok) return null;
  return res.json();
}

/** GET /api/v1/feedback/notes */
export async function listFeedbackNotes(params: {
  folder_id: string;
  source_type?: string;
  status?: NoteStatus;
  limit?: number;
  offset?: number;
}): Promise<FeedbackNote[]> {
  const sp = new URLSearchParams();
  sp.set("folder_id", params.folder_id);
  if (params.source_type) sp.set("source_type", params.source_type);
  if (params.status) sp.set("status", params.status);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const url = `/api/v1/feedback/notes?${qs}`;
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

/** PATCH /api/v1/feedback/notes/:noteId/status */
export async function updateNoteStatus(
  noteId: string,
  status: NoteStatus,
): Promise<FeedbackNote | null> {
  const res = await fetch(
    `/api/v1/feedback/notes/${encodeURIComponent(noteId)}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  if (!res.ok) return null;
  return res.json();
}

/** POST /api/v1/feedback/notes/:noteId/answer */
export async function answerNote(
  noteId: string,
  answer: string,
): Promise<NoteAnswerResult | null> {
  const res = await fetch(
    `/api/v1/feedback/notes/${encodeURIComponent(noteId)}/answer`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer }),
    },
  );
  if (!res.ok) return null;
  return res.json();
}
