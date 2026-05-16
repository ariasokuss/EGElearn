import type {
  CheckAnswerOut,
  DiagramUploadUrlOut,
  SessionDetailOut,
  SubmitAnswerItem,
  TestSessionOut,
  TestStatusOut,
} from "@/shared/api/generated/model";
import {
  getDiagramUploadUrlApiV1TestsSessionsSessionIdAnswersQuestionIdDiagramUploadUrlGet,
} from "@/shared/api/generated/api";

// ── Inline quiz types ─────────────────────────────────────────────────

export type InlineQuestionMapEntry = {
  question_id: string;
  type: "mcq" | "short";
};

export type InlineAnswerEntry = {
  answer: string;
  is_correct: boolean | null;
  earned_marks: number | null;
  total_marks: number;
  feedback: string | null;
  recommendations: string | null;
  graded_at: string | null;
};

export type InlineSessionResponse = {
  session_id: string;
  question_map: Record<string, InlineQuestionMapEntry>;
  answers: Record<string, InlineAnswerEntry>;
};

/** Alias for generated `CheckAnswerOut` (POST check mirrors persisted session answer). */
export type CheckAnswerResponse = CheckAnswerOut;

export type LessonTemplateAvailability = {
  available: boolean;
  templateId: string | null;
};

/** GET /api/v1/tests/templates/lesson/{lesson_id} */
export async function getLessonTestTemplateId(lessonId: string): Promise<string | null> {
  const res = await fetch(
    `/api/v1/tests/templates/lesson/${encodeURIComponent(lessonId)}`,
  );
  if (!res.ok) return null;
  const data = (await res.json()) as { template_id?: unknown; id?: unknown };
  if (typeof data.template_id === "string") return data.template_id;
  if (typeof data.id === "string") return data.id;
  return null;
}

/** GET /api/v1/tests/templates/lesson/{lesson_id}/available — single call returns both availability and template ID */
export async function getLessonTemplateAvailability(
  lessonId: string,
): Promise<LessonTemplateAvailability> {
  const res = await fetch(
    `/api/v1/tests/templates/lesson/${encodeURIComponent(lessonId)}/available`,
  );
  if (!res.ok) return { available: false, templateId: null };
  const data = (await res.json()) as { available?: boolean; template_id?: string | null };
  return {
    available: data.available === true,
    templateId: data.template_id ?? null,
  };
}

/** POST /api/v1/tests/sessions/start */
export async function startTestSession(
  templateId: string,
  mode: string = "practice",
): Promise<TestSessionOut | null> {
  const res = await fetch("/api/v1/tests/sessions/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: templateId, mode }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  // Backend returns SessionDetailOut {session, template, questions, answers}
  return data.session ?? data;
}

export async function listLessonTests(
  lessonId: string,
  folderId: string,
): Promise<TestSessionOut[]> {
  const params = new URLSearchParams({
    folder_id: folderId,
    lesson_id: lessonId,
  });
  const res = await fetch(`/api/v1/tests/sessions?${params}`);
  if (!res.ok) return [];
  return res.json();
}

/** GET /api/v1/tests/sessions/{session_id} */
export async function getTestDetail(sessionId: string): Promise<SessionDetailOut | null> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

/** PUT /api/v1/tests/sessions/{session_id}/answers/{question_id} */
export async function saveSessionAnswer(
  sessionId: string,
  questionId: string,
  answer: string,
  imageKeys?: string[],
): Promise<boolean> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/answers/${encodeURIComponent(questionId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, image_keys: imageKeys }),
    },
  );
  return res.ok;
}

/** POST /api/v1/tests/sessions/{session_id}/submit */
export async function submitTest(
  sessionId: string,
  answers: SubmitAnswerItem[],
): Promise<TestSessionOut | null> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/submit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    },
  );
  if (!res.ok) {
    let body = "";
    try { body = await res.text() } catch { /* ignore */ }
    console.error("[submitTest] failed", res.status, body);
    return null;
  }
  return res.json();
}

/** GET /api/v1/tests/sessions/{session_id}/status */
export async function getTestStatus(sessionId: string): Promise<TestStatusOut | null> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/status`,
  );
  if (!res.ok) return null;
  return res.json();
}

// ── Inline quiz (lesson mini-questions) ───────────────────────────────

/** GET /api/v1/tests/inline-session/{lesson_id} — bootstrap or resume */
export async function getInlineSession(lessonId: string): Promise<InlineSessionResponse | null> {
  const res = await fetch(
    `/api/v1/tests/inline-session/${encodeURIComponent(lessonId)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

/** POST /api/v1/learning/lessons/{lesson_id}/reset — full lesson reset */
export async function resetLesson(lessonId: string): Promise<boolean> {
  const res = await fetch(
    `/api/v1/learning/lessons/${encodeURIComponent(lessonId)}/reset`,
    { method: "POST" },
  );
  return res.ok;
}

/** POST /api/v1/tests/inline-session/{lesson_id}/reset — reset all answers */
export async function resetInlineSession(lessonId: string): Promise<InlineSessionResponse | null> {
  const res = await fetch(
    `/api/v1/tests/inline-session/${encodeURIComponent(lessonId)}/reset`,
    {
      method: "POST",
      
    },
  );
  if (!res.ok) return null;
  return res.json();
}

/** POST /api/v1/tests/sessions/{session_id}/check/{question_id} — check + grade */
export async function checkAnswer(
  sessionId: string,
  questionId: string,
  answer: string,
  imageKeys?: string[],
): Promise<CheckAnswerOut | null> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/check/${encodeURIComponent(questionId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, image_keys: imageKeys }),
    },
  );
  if (!res.ok) return null;
  return res.json();
}

/**
 * PUT /api/v1/tests/sessions/{session_id}/answers/{question_id}/skip
 * Mark or unmark a question as skipped. Skipped questions are excluded from
 * total/earned marks at submission time.
 */
export async function setQuestionSkipped(
  sessionId: string,
  questionId: string,
  skipped: boolean,
): Promise<boolean> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/answers/${encodeURIComponent(questionId)}/skip`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skipped }),
    },
  );
  return res.ok;
}

/**
 * GET presigned URL → PUT bytes to S3. The returned key is submitted later
 * together with the typed answer via save/check/submit.
 */
export async function uploadSessionAnswerDiagramImage(
  sessionId: string,
  questionId: string,
  file: File,
): Promise<string | null> {
  const contentType = file.type || "application/octet-stream";
  const urlRes =
    await getDiagramUploadUrlApiV1TestsSessionsSessionIdAnswersQuestionIdDiagramUploadUrlGet(
      sessionId,
      questionId,
      { content_type: contentType },
    );
  if (urlRes.status !== 200) return null;
  const payload = urlRes.data as DiagramUploadUrlOut;
  if (!payload.upload_url || !payload.image_key) return null;

  const putRes = await fetch(payload.upload_url, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": contentType },
  });
  if (!putRes.ok) return null;
  return payload.image_key;
}

/**
 * POST /api/v1/tests/sessions/{session_id}/answers/{question_id}/regrade
 * Reset graded_at and re-trigger vision grading for an image answer.
 * Call this before polling when the user explicitly clicks "Check" for an
 * image question that may have already been graded (e.g. from eager upload).
 */
export async function regradeSessionAnswer(
  sessionId: string,
  questionId: string,
): Promise<boolean> {
  const res = await fetch(
    `/api/v1/tests/sessions/${encodeURIComponent(sessionId)}/answers/${encodeURIComponent(questionId)}/regrade`,
    { method: "POST" },
  );
  return res.ok;
}
