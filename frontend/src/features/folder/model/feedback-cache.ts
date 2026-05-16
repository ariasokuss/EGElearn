import type { FeedbackNote, FeedbackSummary } from "@/features/folder/api/feedback-api";

export type CachedFeedback = {
  summary: FeedbackSummary;
  seeNotes: FeedbackNote[];
  reviewNotes: FeedbackNote[];
  coveredNotes: FeedbackNote[];
};

const feedbackCacheByFolder = new Map<string, CachedFeedback>();

export type FeedbackCacheInvalidateListener = (folderId: string) => void;

const feedbackInvalidateListeners = new Set<FeedbackCacheInvalidateListener>();

export function readCachedFeedback(folderId: string): CachedFeedback | null {
  if (!folderId) return null;
  return feedbackCacheByFolder.get(folderId) ?? null;
}

export function writeCachedFeedback(folderId: string, payload: CachedFeedback): void {
  if (!folderId) return;
  feedbackCacheByFolder.set(folderId, payload);
}

/** Removes cached snapshot for the folder and notifies subscribers (e.g. mounted Feedback hub). */
export function invalidateFeedbackCache(folderId: string): void {
  if (!folderId) return;
  feedbackCacheByFolder.delete(folderId);
  for (const listener of [...feedbackInvalidateListeners]) {
    listener(folderId);
  }
}

export function subscribeFeedbackCacheInvalidation(
  listener: FeedbackCacheInvalidateListener,
): () => void {
  feedbackInvalidateListeners.add(listener);
  return () => {
    feedbackInvalidateListeners.delete(listener);
  };
}
