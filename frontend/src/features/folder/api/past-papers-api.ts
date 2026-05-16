import { streamSSE } from "@/features/practice-questions/api";
import { getUploadPastPaperStreamApiV1PastPapersUploadPostUrl } from "@/shared/api";
import { BodyUploadPastPaperStreamApiV1PastPapersUploadPost } from "@/shared/api/generated/model";
import { throwHttpError } from "@/shared/api/http-error";

type SSEEvent = {
    event: "started",
    paper_id: string,
} | {
    event: "processing",
    phase: "ocr" | "mark_scheme_parsing" | "parsing" | "matching" | "mark_scheme_matching"
    message: string
} | {
    event: "complete",
    paper_id: string,
    total_questions: number,
    total_marks: number,
    name: string
} | {
    event: "mark_scheme_unassigned"
    matched_questions: number
    total_short_questions: number
    total_questions: number
    message: string
} | {
    event: "mark_scheme_failed"
    matched_questions: number
    total_short_questions: number
    message: string
}

export type PastPaperStatus = {
    id: string
    status: "processing" | "ready" | "failed"
    processing_phase: "ocr" | "parsing" | "matching" | null
}

export async function getPastPaperStatus(paperId: string): Promise<PastPaperStatus> {
    const res = await fetch(`/api/v1/past-papers/${encodeURIComponent(paperId)}/status`)
    if (!res.ok) await throwHttpError(res)
    return res.json()
}

export function streamPastPaperUpload(body: BodyUploadPastPaperStreamApiV1PastPapersUploadPost) {
    const formData = new FormData();
    formData.append(`file`, body.file);
    formData.append(`name`, body.name);
    formData.append(`folder_id`, body.folder_id);
    if (body.mark_scheme_file !== undefined && body.mark_scheme_file !== null) {
        formData.append(`mark_scheme_file`, body.mark_scheme_file);
    }

    return streamSSE<SSEEvent>(
        getUploadPastPaperStreamApiV1PastPapersUploadPostUrl(),
        "POST",
        formData
    )
}