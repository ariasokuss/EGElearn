import { useCallback, useReducer } from "react";

import type {
  FeynmanSessionRead,
  SessionDetailRead,
  SessionFeedbackRead,
  ThemeFeedbackItem,
} from "@/shared/api/generated/model";

import { startFeynmanSession, streamFeynmanAnswer } from "./feynman-api";

type ChatMessage = { role: string; content: string };

type IdleState = { status: "idle" };
type LoadingState = { status: "loading" };
type ActiveState = {
  status: "active";
  sessionId: string;
  messages: ChatMessage[];
  streamingContent: string;
  submitting: boolean;
};
type CompleteState = {
  status: "complete";
  messages: ChatMessage[];
  summary: string;
  coveredPoints: boolean[];
  points: string[];
  allCovered: boolean;
};
type ErrorState = { status: "error"; message: string };
type MachineSummaryPayload = {
  covered?: boolean[];
  follow_up?: string;
  summary?: string;
  text?: string;
  points?: string[];
  all_covered?: boolean;
  allCovered?: boolean;
};

export type FeynmanSessionState =
  | IdleState
  | LoadingState
  | ActiveState
  | CompleteState
  | ErrorState;

function coerceBooleanArray(value: FeynmanSessionRead["covered_points"]): boolean[] {
  if (!value?.length) return [];
  return value.map((v) => (typeof v === "number" ? v > 0 : v === true));
}

function summarizeFromFeedbackList(feedback: ThemeFeedbackItem[] | null | undefined): string {
  if (!feedback?.length) return "";
  return feedback
    .map((item) => item.feedback)
    .filter(Boolean)
    .join("\n\n");
}

function isMachineSummaryPayload(value: unknown): value is MachineSummaryPayload {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const payload = value as Record<string, unknown>;
  return (
    Array.isArray(payload.covered) ||
    typeof payload.summary === "string" ||
    typeof payload.text === "string" ||
    typeof payload.follow_up === "string"
  );
}

function parseMachineSummaryPayload(raw: unknown): MachineSummaryPayload | null {
  if (isMachineSummaryPayload(raw)) return raw;
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return null;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    return isMachineSummaryPayload(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

type Action =
  | { type: "start_loading" }
  | { type: "session_started"; sessionId: string; firstMessage: ChatMessage }
  | { type: "restore_active"; sessionId: string; messages: ChatMessage[] }
  | { type: "add_user_message"; content: string }
  | { type: "stream_token"; content: string }
  | { type: "assistant_message_complete"; message: ChatMessage }
  | {
      type: "session_complete";
      summary: string;
      coveredPoints: boolean[];
      points: string[];
      allCovered: boolean;
    }
  | { type: "restore_complete"; state: CompleteState }
  | { type: "replace_messages"; messages: ChatMessage[] }
  | { type: "error"; message: string };

function reducer(state: FeynmanSessionState, action: Action): FeynmanSessionState {
  switch (action.type) {
    case "start_loading":
      return { status: "loading" };

    case "session_started":
      return {
        status: "active",
        sessionId: action.sessionId,
        messages: [action.firstMessage],
        streamingContent: "",
        submitting: false,
      };

    case "restore_active":
      return {
        status: "active",
        sessionId: action.sessionId,
        messages: action.messages,
        streamingContent: "",
        submitting: false,
      };

    case "add_user_message":
      if (state.status !== "active") return state;
      return {
        ...state,
        messages: [...state.messages, { role: "user", content: action.content }],
        submitting: true,
      };

    case "stream_token":
      if (state.status !== "active") return state;
      return { ...state, streamingContent: state.streamingContent + action.content };

    case "assistant_message_complete":
      if (state.status !== "active") return state;
      return {
        ...state,
        messages: [...state.messages, action.message],
        streamingContent: "",
        submitting: false,
      };

    case "session_complete":
      if (state.status !== "active") return state;
      return {
        status: "complete",
        messages: state.messages,
        summary: action.summary,
        coveredPoints: action.coveredPoints,
        points: action.points,
        allCovered: action.allCovered,
      };

    case "restore_complete":
      return action.state;

    case "replace_messages":
      if (state.status !== "active") return state;
      return { ...state, messages: action.messages, streamingContent: "", submitting: false };

    case "error":
      return { status: "error", message: action.message };

    default:
      return state;
  }
}

type UseFeynmanSessionParams = {
  feynmanBlockId: string;
  lessonId: string;
};

export function useFeynmanSession({ lessonId }: UseFeynmanSessionParams) {
  const [state, dispatch] = useReducer(reducer, { status: "idle" });

  const restoreFromHistory = useCallback(
    (detail: SessionDetailRead) => {
      if (detail.session.status === "completed" || detail.session.status === "aborted") {
        const coveredPoints = coerceBooleanArray(detail.session.covered_points);
        const points = detail.feynman_block.points;
        const allCovered =
          points.length > 0 &&
          coveredPoints.length >= points.length &&
          points.every((_, i) => coveredPoints[i] === true);
        dispatch({
          type: "restore_complete",
          state: {
            status: "complete",
            messages: detail.messages.map((m) => ({ role: m.role, content: m.content })),
            summary: summarizeFromFeedbackList(detail.session.feedback ?? null),
            coveredPoints,
            points,
            allCovered,
          },
        });
      } else if (detail.session.status === "active" && detail.messages.length > 0) {
        dispatch({
          type: "restore_active",
          sessionId: detail.session.id,
          messages: detail.messages.map((m) => ({ role: m.role, content: m.content })),
        });
      }
    },
    [],
  );

  const restoreFromFeedback = useCallback((feedback: SessionFeedbackRead) => {
    const coveredPoints = coerceBooleanArray(feedback.covered_points);
    const points = feedback.points ?? feedback.feynman_block.points;
    const allCovered =
      feedback.all_covered ??
      (points.length > 0 &&
        coveredPoints.length >= points.length &&
        points.every((_, i) => coveredPoints[i] === true));
    dispatch({
      type: "restore_complete",
      state: {
        status: "complete",
        messages: [],
        summary: feedback.summary ?? summarizeFromFeedbackList(feedback.session.feedback ?? null),
        coveredPoints,
        points,
        allCovered,
      },
    });
  }, []);

  const start = useCallback(async () => {
    if (!lessonId) {
      dispatch({ type: "error", message: "Missing lesson id." });
      return;
    }
    dispatch({ type: "start_loading" });
    const result = await startFeynmanSession(lessonId);
    if (!result) {
      dispatch({ type: "error", message: "Failed to start session." });
      return;
    }
    dispatch({
      type: "session_started",
      sessionId: result.session.id,
      firstMessage: {
        role: result.first_message.role,
        content: result.first_message.content,
      },
    });
  }, [lessonId]);

  const submitAnswer = useCallback(async (sessionId: string, answer: string) => {
    dispatch({ type: "add_user_message", content: answer });
    let guardedTokenBuffer = "";
    let tokenGuardActive = true;

    try {
      for await (const event of streamFeynmanAnswer(sessionId, answer)) {
        if (event.event === "token") {
          const data = event.data as { content?: string };
          if (!data.content) continue;
          if (!tokenGuardActive) {
            dispatch({ type: "stream_token", content: data.content });
            continue;
          }

          guardedTokenBuffer += data.content;
          const probe = guardedTokenBuffer.trimStart();
          if (
            probe.startsWith("{") ||
            probe.startsWith("```") ||
            probe.includes('"covered"') ||
            probe.includes('"follow_up"') ||
            probe.includes('"summary"')
          ) {
            continue;
          }
          if (probe.length < 24) continue;

          tokenGuardActive = false;
          dispatch({ type: "stream_token", content: guardedTokenBuffer });
          guardedTokenBuffer = "";
        } else if (event.event === "message_complete") {
          const data = event.data as { role?: string; content?: string };
          const machinePayload = parseMachineSummaryPayload(data.content);
          if (machinePayload) {
            dispatch({
              type: "session_complete",
              summary: machinePayload.summary ?? machinePayload.text ?? "",
              coveredPoints: machinePayload.covered ?? [],
              points: machinePayload.points ?? [],
              allCovered:
                machinePayload.all_covered ??
                machinePayload.allCovered ??
                false,
            });
            continue;
          }
          dispatch({
            type: "assistant_message_complete",
            message: { role: data.role ?? "assistant", content: data.content ?? "" },
          });
        } else if (event.event === "summary") {
          const data = event.data as {
            text?: string;
            summary?: string;
            covered?: boolean[];
            points?: string[];
            all_covered?: boolean;
            allCovered?: boolean;
          };
          dispatch({
            type: "session_complete",
            summary: data.summary ?? data.text ?? "",
            coveredPoints: data.covered ?? [],
            points: data.points ?? [],
            allCovered: data.all_covered ?? data.allCovered ?? false,
          });
        }
      }
    } catch {
      dispatch({ type: "error", message: "Connection error. Please try again." });
    }
  }, []);

  return { state, dispatch, start, submitAnswer, restoreFromHistory, restoreFromFeedback };
}
