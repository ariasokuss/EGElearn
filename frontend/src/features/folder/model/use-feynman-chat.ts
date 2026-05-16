"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { nanoid } from "nanoid";

import type {
  ChatMessage,
  ChatStatus,
  TaggedPart,
} from "@/entities/chat";
import { streamFeynman } from "@/shared/api/chat-stream";
import { abortSessionApiV1FeynmanSessionSessionIdAbortPost, getSessionApiV1FeynmanSessionSessionIdGet } from "@/shared/api";
import { FeynmanMessageRead } from "@/shared/api/generated/model";

function backendToLocal(msg: FeynmanMessageRead): ChatMessage {
  return {
    id: msg.id,
    role: msg.role as "user" | "assistant",
    content: msg.content,
    citations: msg.citations?.length ? msg.citations : undefined,
    createdAt: msg.created_at,
    siblingCount: 1,
    versionIndex: 1,
  };
}

type UseFeynmanChatOptions = {
  lessonId: string;
  sessionId?: string
};

type StreamResponseArgs = {
  type: "start"
  lessonId: string
} | {
  type: "answer",
  sessionId: string,
  message: string,
  citations?: string[]
}

type UseFeynmanChatReturn = {
  sessionId: string | undefined;
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  taggedPart: TaggedPart | null;
  setTaggedPart: (part: TaggedPart | null) => void;
  status: ChatStatus;
  isCompleted: boolean;
  error: string | null;
  handleSubmit: VoidFunction;
  reload: (messagesOverride?: ChatMessage[]) => void;
  setMessages: (msgs: ChatMessage[]) => void;
};

export function useFeynmanChat({ lessonId, sessionId: initialSessionId }: UseFeynmanChatOptions): UseFeynmanChatReturn {
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)
  const sessionStarted = useRef(false)
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [taggedPart, setTaggedPart] = useState<TaggedPart | null>(null);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [isCompleted, setIsCompleted] = useState(false)
  const [error, setError] = useState<string | null>(null);
  const endSession = useRef(false);
  const messagesRef = useRef(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    endSession.current = false
    return () => { endSession.current = true }
  }, [])

  const streamResponse = useCallback(
    async (args: StreamResponseArgs) => {
      setStatus("submitted");
      setError(null);

      const assistantMessage: ChatMessage = {
        id: nanoid(),
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        siblingCount: 1,
        versionIndex: 1,
      };

      try {
        let firstToken = true;
        let pendingUpdate = false;

        const generator = streamFeynman(
          args.type === "answer"
            ? {
              type: "answer",
              sessionId: args.sessionId,
              request: { answer: args.message, citations: args.citations }
            } : {
              type: "start",
              request: { lesson_id: args.lessonId }
            },
        );

        for await (const event of generator) {
          if (event.type === "error") {
            setError(event.message);
            setStatus("error");
            return;
          }

          if (event.type === "done") {
            setIsCompleted(true)
            break
          }

          if (event.type === "session_started") {
            if (endSession.current) {
              abortSessionApiV1FeynmanSessionSessionIdAbortPost(event.sessionId, {})
              return
            }

            setSessionId(event.sessionId)
            break
          }

          if (event.type === "token") {
            if (firstToken) {
              setStatus("streaming");
              firstToken = false;
            }

            assistantMessage.content += event.text;
            if (!pendingUpdate) {
              pendingUpdate = true;
              requestAnimationFrame(() => {
                pendingUpdate = false;
                const snapshot = { ...assistantMessage };
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.id === snapshot.id) {
                    const next = prev.slice();
                    next[next.length - 1] = snapshot;
                    return next;
                  }
                  return [...prev, snapshot];
                });
              });
            }
          }
        }

        const finalSnapshot = { ...assistantMessage };
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          let final: ChatMessage[];
          if (last?.id === finalSnapshot.id) {
            final = prev.slice();
            final[final.length - 1] = finalSnapshot;
          } else {
            final = [...prev, finalSnapshot];
          }

          return final;
        });

      } catch (err) {
        if (err instanceof Error && err.message === "AUTH_EXPIRED") {
          setError("Session expired. Please log in again.");
          setStatus("error");
          return;
        } else {
          setError(err instanceof Error ? err.message : "Error occurred");
          setStatus("error");
          return;
        }
      }

      setStatus("ready");
    },
    [],
  );

  const handleSubmit = useCallback(
    async () => {
      if (!sessionId) return
      const trimmed = input.trim();
      if (!trimmed || status === "streaming" || status === "submitted") return;

      const userMessage: ChatMessage = {
        id: nanoid(),
        role: "user",
        content: trimmed,
        citations: taggedPart?.text ? [taggedPart.text] : undefined,
        createdAt: new Date().toISOString(),
        siblingCount: 1,
        versionIndex: 1,
        ...(taggedPart ? { metadata: { tagged_part: taggedPart } } : {}),
      };

      const updatedMessages = [...messagesRef.current, userMessage];
      setMessages(updatedMessages);
      setInput("");
      setTaggedPart(null);

      streamResponse({
        type: "answer",
        message: trimmed,
        sessionId,
        citations: taggedPart?.text ? [taggedPart.text] : undefined,
      });
    },
    [input, status, sessionId, streamResponse, taggedPart]
  );

  const reload = useCallback(
    (messagesOverride?: ChatMessage[]) => {
      if (!sessionId) return
      const currentMessages = messagesOverride ?? messagesRef.current;
      if (currentMessages.length === 0) return;

      const lastMsg = currentMessages[currentMessages.length - 1];
      const withoutLastAssistant =
        lastMsg.role === "assistant"
          ? currentMessages.slice(0, -1)
          : currentMessages;

      setMessages(withoutLastAssistant);

      const lastUserMsg = withoutLastAssistant.findLast(
        (m) => m.role === "user",
      );
      if (!lastUserMsg) return;

      streamResponse({ type: "answer", message: lastUserMsg.content, sessionId });
    },
    [sessionId, streamResponse],
  );

  const loadMessages = useCallback(
    async (sessionId: string) => {
      const resp = await getSessionApiV1FeynmanSessionSessionIdGet(sessionId)
      if (resp.status !== 200) {
        setError("Failed to load chat");
        setStatus("error");
        return;
      }

      setMessages(resp.data.messages.map(backendToLocal))
    },
    []
  )

  useEffect(() => {
    if (sessionStarted.current) return
    sessionStarted.current = true
    if (initialSessionId)
      loadMessages(initialSessionId)
    else
      streamResponse({
        type: "start",
        lessonId: lessonId,
      })
  }, [lessonId, initialSessionId, loadMessages, streamResponse])

  return {
    sessionId,
    messages,
    input,
    setInput,
    taggedPart,
    setTaggedPart,
    status,
    isCompleted,
    error,
    handleSubmit,
    reload,
    setMessages,
  };
}
