"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { FeynmanBlockRead, SessionHistoryItem } from "@/shared/api/generated/model";
import type { ChatMessage, ChatStatus, TaggedPart } from "@/entities/chat";
import { LessonCard } from "@/shared/ui/lesson-card";
import { ChatThread, type ChatThreadHandle } from "@/features/chat/ui/chat-thread";
import { useVoiceInput } from "@/features/chat/model/use-voice-input";
import { cn } from "@/shared/lib";
import {
  FaceSmileIcon,
  FaceFrownIcon,
  CheckIcon,
  CancelCircleIcon,
  AttachmentIcon,
  MicIcon,
  PaperAirplaneIcon,
} from "@/shared/assets/icons";

import { getSession, getSessionFeedback } from "./feynman-api";
import type { FeynmanData } from "./parse-content";
import { useFeynmanSession } from "./use-feynman-session";
import { Button } from "@/shared";

type FeynmanBlockProps = {
  data: FeynmanData;
  feynmanBlock: FeynmanBlockRead | undefined;
  lessonId: string;
  miniFeynmanHistory: SessionHistoryItem[];
  /**
   * Called when the user selects text inside a Feynman chat message and
   * clicks the in-chat "Ask Nova" toolbar. The parent routes the text into
   * the main Nova chat (opens the chat panel + tags the selection).
   */
  onAskNova?: (text: string) => void;
};

const STABLE_DATE = new Date(0).toISOString();

/** Map feynman session messages to ChatMessage format for ChatMessages component */
function toChatMessages(
  messages: { role: string; content: string }[],
  streamingContent: string,
): ChatMessage[] {
  const mapped: ChatMessage[] = messages.map((msg, i) => ({
    id: `feynman-msg-${i}`,
    role: msg.role === "user" ? "user" : "assistant",
    content: msg.content,
    createdAt: STABLE_DATE,
    siblingCount: 1,
    versionIndex: 1,
  }));

  if (streamingContent) {
    mapped.push({
      id: "feynman-streaming",
      role: "assistant",
      content: streamingContent,
      createdAt: STABLE_DATE,
      siblingCount: 1,
      versionIndex: 1,
    });
  }

  return mapped;
}

type ResultLevel = "success" | "partial" | "fail";

const RESULT_CONFIG: Record<
  ResultLevel,
  { color: string; Icon: React.ComponentType<React.SVGProps<SVGSVGElement>> }
> = {
  success: { color: "#97CEAB", Icon: FaceSmileIcon },
  partial: { color: "#CEC397", Icon: CheckIcon },
  fail: { color: "#CE9C97", Icon: FaceFrownIcon },
};

function getResultLevel(
  coveredPoints: boolean[],
  allCovered: boolean,
): ResultLevel {
  if (allCovered) return "success";
  const coveredCount = coveredPoints.filter(Boolean).length;
  if (coveredCount === 0) return "fail";
  return "partial";
}

function FeynmanResultOverlay({
  points,
  coveredPoints,
  allCovered,
  onTryAgain,
}: {
  points: string[];
  coveredPoints: boolean[];
  allCovered: boolean;
  onTryAgain: VoidFunction;
}) {
  const level = getResultLevel(coveredPoints, allCovered);
  const { color, Icon } = RESULT_CONFIG[level];

  const missed = points.filter((_, i) => !coveredPoints[i]);
  const covered = points.filter((_, i) => coveredPoints[i]);

  return (
    <div className="flex flex-col items-center bg-white px-6 py-6">
      <div className="flex flex-col items-center gap-3">
        <div
          className="flex h-18 w-18 shrink-0 items-center justify-center rounded-full"
          style={{ border: `5px solid ${color}` }}
        >
          <div
            className="flex h-14 w-14 items-center justify-center rounded-full"
            style={{ background: color }}
          >
            <Icon style={{ color: "white" }} />
          </div>
        </div>

        <Button
          variant="outline"
          type="button"
          onClick={onTryAgain}
        >
          Try again
        </Button>

        {points.length > 0 && (
          <div className="flex w-full flex-col gap-5">
            {missed.length > 0 && (
              <div>
                <p className="mb-1 nova-text-label-small text-[#242529]">
                  You missed in your explanation
                </p>
                <ul className="space-y-1.5">
                  {missed.map((point, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-3 nova-text-p-base text-[#8A8F98]"
                    >
                      <CancelCircleIcon className="mt-1 shrink-0 text-[#CE9C97]" />
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {covered.length > 0 && (
              <div>
                <p className="mb-1 nova-text-label-small text-[#242529]">
                  Covered well
                </p>
                <ul className="space-y-1.5">
                  {covered.map((point, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-3 nova-text-p-base text-[#8A8F98]"
                    >
                      <CheckIcon className="mt-1 shrink-0 text-[#77B18C]" />
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FeynmanChatInput({
  input,
  onInputChange,
  onSubmit,
  isLoading,
}: {
  input: string;
  onInputChange: (v: string) => void;
  onSubmit: VoidFunction;
  isLoading: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef(input);
  useEffect(() => { inputRef.current = input; }, [input]);

  const handleVoiceTranscript = useCallback(
    (text: string) => {
      const cur = inputRef.current;
      const sep = cur && !cur.endsWith(" ") && !cur.endsWith("\n") ? " " : "";
      onInputChange(cur + sep + text);
    },
    [onInputChange],
  );

  const { state: voiceState, interimText, toggle: toggleVoice, stop: stopVoice } =
    useVoiceInput(handleVoiceTranscript);

  const voiceSupported = voiceState !== "unsupported";
  const isListening = voiceState === "listening";

  const displayValue =
    isListening && interimText
      ? input + (input && !input.endsWith(" ") && !input.endsWith("\n") ? " " : "") + interimText
      : input;

  const canSend = input.trim().length > 0 && !isLoading;

  const handleSend = useCallback(() => {
    if (isListening) stopVoice();
    onSubmit();
  }, [isListening, stopVoice, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) handleSend();
      }
    },
    [canSend, handleSend],
  );

  return (
    <div className="border-t border-[#0000000D] bg-white px-1 backdrop-blur-xs">
      <div className="flex items-center gap-1.5 rounded-full px-2 py-1.5">
        <Button
          iconOnly
          variant="plain"
          rounded={false}
          type="button"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Attach file"
          className="flex shrink-0 items-center justify-center text-[#B0ADA9] hover:text-[#6B6B6B]"
        >
          <AttachmentIcon />
        </Button>
        <input ref={fileInputRef} type="file" multiple accept="image/*,.pdf,.txt,.csv,.json" hidden />

        <input
          type="text"
          value={displayValue}
          onChange={(e) => { if (!isListening) onInputChange(e.target.value); }}
          onKeyDown={handleKeyDown}
          readOnly={isListening}
          placeholder={isListening ? "Listening…" : "Ask Nova anything"}
          className={cn(
            "min-w-0 flex-1 bg-transparent nova-text-label-medium outline-none",
            isListening
              ? "text-[#B0ADA9] placeholder:text-[#B0ADA9]"
              : "text-[#242529] placeholder:text-[#A1A1AA]",
          )}
        />

        {voiceSupported && (
          <Button
            type="button"
            onClick={toggleVoice}
            className={cn(
              "relative flex shrink-0 items-center justify-center transition-all duration-200",
              !isListening && "text-[#B0ADA9] hover:text-[#6B6B6B]",
            )}
            aria-label={isListening ? "Stop recording" : "Voice input"}
          >
            {isListening && <span className="voice-pulse absolute inset-0 rounded-full bg-[#F1ECE9]" />}
            <MicIcon className="relative z-10 h-4.5 w-4.5" />
          </Button>
        )}

        {isLoading ? (
          <Button //No button variant
            size="sm"
            iconOnly
            type="button"
            aria-label="Stop generation"
            className="flex shrink-0 items-center justify-center bg-[#242529] hover:bg-[#3a3a3e]"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="white">
              <rect width="10" height="10" rx="2" />
            </svg>
          </Button>
        ) : (
          <Button
            iconOnly
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send message"
            className="flex shrink-0 items-center justify-center"
          >
            <PaperAirplaneIcon />
          </Button>
        )}
      </div>
    </div>
  );
}

export function FeynmanBlock({ feynmanBlock, lessonId, miniFeynmanHistory, onAskNova }: FeynmanBlockProps) {
  const {
    state,
    dispatch,
    start,
    submitAnswer,
    restoreFromHistory,
    restoreFromFeedback,
  } = useFeynmanSession({
    feynmanBlockId: feynmanBlock?.id ?? "",
    lessonId,
  });
  const [input, setInput] = useState("");
  const chatThreadRef = useRef<ChatThreadHandle>(null);

  useEffect(() => {
    if (!feynmanBlock?.id) return;
    let cancelled = false;

    const matching = miniFeynmanHistory
      .filter((s) => s.feynman_block.id === feynmanBlock.id)
      .sort(
        (a, b) =>
          new Date(b.session.updated_at).getTime() -
          new Date(a.session.updated_at).getTime(),
      );

    const latest = matching[0];

    if (latest) {
      if (latest.session.status === "completed" || latest.session.status === "aborted") {
        getSession(latest.session.id).then((detail) => {
          if (cancelled || !detail) return;
          if (
            detail.session.status === "aborted" &&
            !detail.messages.some((m) => m.role === "user")
          ) {
            start();
            return;
          }
          getSessionFeedback(latest.session.id).then((feedback) => {
            if (cancelled) return;
            if (feedback) {
              restoreFromFeedback(feedback);
            } else {
              restoreFromHistory(detail);
            }
          });
        });
      } else if (latest.session.status === "active") {
        getSession(latest.session.id).then((detail) => {
          if (!cancelled && detail) restoreFromHistory(detail);
        });
      }
    } else {
      start();
    }

    return () => { cancelled = true; };
  }, [feynmanBlock?.id, miniFeynmanHistory, restoreFromHistory, restoreFromFeedback, start]);

  function handleSubmit() {
    if (state.status !== "active" || !input.trim() || state.submitting) return;
    const answer = input.trim();
    setInput("");
    submitAnswer(state.sessionId, answer);
    chatThreadRef.current?.scrollOnSend();
  }

  function handleRetry() {
    start();
  }

  const handleEdit = useCallback(
    (index: number, newContent: string) => {
      if (state.status !== "active" || state.submitting) return;
      const trimmed = state.messages.slice(0, index);
      dispatch({ type: "replace_messages", messages: trimmed });
      submitAnswer(state.sessionId, newContent);
    },
    [state, dispatch, submitAnswer],
  );

  const handleRegenerate = useCallback(
    (index: number) => {
      if (state.status !== "active" || state.submitting) return;
      const msg = state.messages[index];
      if (!msg) return;

      if (msg.role === "assistant") {
        const prevUserMsg = state.messages
          .slice(0, index)
          .reverse()
          .find((m) => m.role === "user");
        if (!prevUserMsg) return;
        const trimmed = state.messages.slice(0, index);
        dispatch({ type: "replace_messages", messages: trimmed });
        submitAnswer(state.sessionId, prevUserMsg.content);
      } else {
        const trimmed = state.messages.slice(0, index);
        dispatch({ type: "replace_messages", messages: trimmed });
        submitAnswer(state.sessionId, msg.content);
      }
    },
    [state, dispatch, submitAnswer],
  );

  const chatStatus: ChatStatus = useMemo(() => {
    if (state.status === "active" && state.submitting) {
      return state.streamingContent ? "streaming" : "submitted";
    }
    return "ready";
  }, [state]);

  const chatMessages = useMemo(() => {
    if (state.status === "active") {
      return toChatMessages(state.messages, state.streamingContent);
    }
    return [];
  }, [state]);

  return (
    <LessonCard>
      <div className="border-b border-[#F4F4F5] px-3.5 pt-4.5 pb-4">
        <span className="nova-text-label-tiny-sb text-[#242529]">
          Feynman
        </span>
      </div>

      <div className="flex flex-col" style={{ height: state.status === "complete" ? "auto" : 400 }}>
        {(state.status === "idle" || state.status === "loading") && (
          <div className="flex flex-1 items-center justify-center">
            <div className="flex gap-1.5">
              <span className="h-2 w-2 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "0ms" }} />
              <span className="h-2 w-2 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "150ms" }} />
              <span className="h-2 w-2 animate-bounce rounded-full bg-[#B0ADA9]" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}

        {state.status === "error" && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-4">
            <p className="nova-text-p-base text-red-500">{state.message}</p>
            <Button //No button variant
              rounded={false}
              size="l"
              type="button"
              onClick={handleRetry}
              className="rounded-lg bg-[#242529] text-white hover:bg-[#3a3a3e]"
            >
              Retry
            </Button>
          </div>
        )}

        {state.status === "active" && (
          <div className="flex min-h-0 flex-1 flex-col">
            <ChatThread
              ref={chatThreadRef}
              messages={chatMessages}
              status={chatStatus}
              onEdit={handleEdit}
              onRegenerate={handleRegenerate}
              onSetTaggedPart={
                onAskNova
                  ? (part: TaggedPart) => onAskNova(part.text)
                  : undefined
              }
              inputWrapperClassName="relative"
            >
              <FeynmanChatInput
                input={input}
                onInputChange={setInput}
                onSubmit={handleSubmit}
                isLoading={chatStatus !== "ready"}
              />
            </ChatThread>
          </div>
        )}

        {state.status === "complete" && (
          <FeynmanResultOverlay
            points={state.points}
            coveredPoints={state.coveredPoints}
            allCovered={state.allCovered}
            onTryAgain={() => start()}
          />
        )}
      </div>
    </LessonCard>
  );
}
