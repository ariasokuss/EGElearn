import type { SessionResultsOut } from "@/shared/api/generated/model";
import { getTestStatus } from "../../../api/lesson-test-api";
import {
  getSessionResultsApiV1TestsSessionsSessionIdResultsGet,
} from "@/shared/api";

const INITIAL_INTERVAL = 1_000;
const MAX_INTERVAL = 8_000;
const MAX_DURATION = 600_000; // 10 minutes max

/**
 * Poll the backend until grading completes, then return SessionResultsOut.
 * Uses exponential backoff: 1s → 2s → 4s → 8s (capped).
 * Resolves once status === "graded".
 * Rejects if polling times out or the session can't be found.
 */
export async function pollForGradingResults(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionResultsOut> {
  const startTime = Date.now();
  let interval = INITIAL_INTERVAL;

  while (Date.now() - startTime < MAX_DURATION) {
    if (signal?.aborted) throw new Error("Polling aborted");

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, interval);
      signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new Error("Polling aborted"));
      }, { once: true });
    });

    const status = await getTestStatus(sessionId);
    if (!status) throw new Error("Session not found");

    if (status.status === "graded" || status.status === "completed") {
      return fetchSessionResults(sessionId);
    }

    // Exponential backoff: double interval, cap at MAX_INTERVAL
    interval = Math.min(interval * 2, MAX_INTERVAL);
  }

  throw new Error("Grading timed out");
}

async function fetchSessionResults(sessionId: string): Promise<SessionResultsOut> {
  const resp = await getSessionResultsApiV1TestsSessionsSessionIdResultsGet(sessionId);
  if (resp.status !== 200) throw new Error("Failed to fetch session results");
  return resp.data;
}
