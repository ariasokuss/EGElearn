import { createExamApiV1ExamsPost, deleteExamApiV1ExamsExamIdDelete, getExamsApiV1ExamsFoldersFolderIdGet } from "@/shared/api/generated/api";
import type { ExamCreate, ExamOut } from "@/shared/api/generated/model";

export const createExamApi = (data: ExamCreate) => createExamApiV1ExamsPost(data);

export const getExamsApi = async (folderId: string) => {
  try {
    return await getExamsApiV1ExamsFoldersFolderIdGet(folderId);
  } catch {
    return { data: [], status: 500 as const, headers: new Headers() };
  }
};

export const deleteExamApi = (examId: string) => deleteExamApiV1ExamsExamIdDelete(examId);

export const updateExamApi = async (examId: string, data: ExamCreate) => {
  const res = await fetch(`/api/v1/exams/${examId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const body = await res.text();
  const parsed: ExamOut = body ? JSON.parse(body) : {};
  return { data: parsed, status: res.status as 200 | 422 };
};

export type OptionalThemesOut = {
  title: string;
  exam_date: string;
  blocks: { id: string; name: string }[][];
};

export const getOptionalThemesApi = async (
  folderId: string
): Promise<OptionalThemesOut | null> => {
  try {
    const res = await fetch(`/api/v1/roadmap/folders/${folderId}/optional-themes`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
};

export const saveOptionalThemesSelectionApi = async (
  folderId: string,
  optionIds: string[]
): Promise<{ exam_id: string } | null> => {
  try {
    const res = await fetch(
      `/api/v1/roadmap/folders/${folderId}/optional-themes/selection`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ option_ids: optionIds }),
      }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
};
