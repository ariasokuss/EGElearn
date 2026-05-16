"use client";

import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useMemo,
  type Dispatch,
  type SetStateAction,
} from "react";
import { nanoid } from "nanoid";

import type {
  ChatMessage,
  ChatStatus,
  FileAttachment,
  MessageSchema,
  ConversationSummary,
  TaggedPart,
} from "@/entities/chat";
import { streamChatMessage, streamRegenerateMessage } from "@/shared/api/chat-stream";
import { apiStreamOrigin } from "@/shared/api/api-fetch-origin";
import { getAccessToken } from "@/shared/lib/auth-storage";
import {
  listConversationsApiV1ChatConversationsGet,
  getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet,
  deleteConversationApiV1ChatConversationsConversationIdDelete as deleteConversationApi,
  renameConversationTitleApiV1ChatConversationsConversationIdTitlePatch as renameConversationApi,
} from "@/shared/api/generated/api";
import { imagesToBase64, filesToAttachments } from "@/features/chat/lib";
import type { FileAttachmentPayload } from "@/features/chat/lib/file-to-base64";
import { db } from "@/features/chat/lib";
import type { ListConversationsApiV1ChatConversationsGetParams } from "@/shared/api/generated/model";

export type PracticeChatScope = {
  testSessionId: string;
  questionId: string;
  scopeType?: "practice" | "review" | "feedback_review";
  feedbackNoteId?: string;
};

type ListConversationsQueryParams = ListConversationsApiV1ChatConversationsGetParams & {
  scope_type?: NonNullable<PracticeChatScope["scopeType"]>;
  feedback_note_id?: string;
};

type SiblingApiRow = {
  id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  parent_id?: string | null;
  version_index: number;
};

/** Serialized inline quiz answer for the chat API. */
type InlineQuizAnswerPayload = {
  block_id: string;
  question_index: number;
  question_type: string;
  total_marks: number;
  answer: string;
  earned_marks: number | null;
  is_correct: boolean | null;
  feedback: string | null;
  recommendations: string | null;
  grading: boolean;
};

type UseChatOptions = {
  folderId: string | null;
  /** When provided (from URL), this conversation is loaded directly. */
  initialConversationId?: string | null;
  /**
   * Practice Questions: scope list + messages to this test session and question (API params).
   * IndexedDB cache key is derived from folder + scope.
   */
  practiceChatScope?: PracticeChatScope | null;
  /** Lesson side panel: scope list + messages to this lesson (`lesson_id` on API). Ignored if `practiceChatScope` is set. */
  lessonId?: string | null;
  /** The currently visible lesson block UUID — injected into the lesson scope prompt. */
  currentBlockId?: string | null;
  /** Inline quiz answers from the lesson panel — sent with each message for context. */
  inlineQuizAnswers?: Map<string, { answer: string; questionType: string; isCorrect: boolean | null; earnedMarks: number; totalMarks: number; feedback: string | null; recommendations: string | null; grading: boolean }> | null;
};

function serializeInlineQuizAnswers(
  answers: Map<string, { answer: string; questionType: string; isCorrect: boolean | null; earnedMarks: number; totalMarks: number; feedback: string | null; recommendations: string | null; grading: boolean }> | null | undefined,
): InlineQuizAnswerPayload[] | undefined {
  if (!answers || answers.size === 0) return undefined;
  const result: InlineQuizAnswerPayload[] = [];
  for (const [key, record] of answers) {
    const sep = key.indexOf(":");
    if (sep === -1) continue;
    result.push({
      block_id: key.slice(0, sep),
      question_index: Number(key.slice(sep + 1)),
      question_type: record.questionType,
      total_marks: record.totalMarks,
      answer: record.answer,
      earned_marks: record.earnedMarks ?? null,
      is_correct: record.isCorrect ?? null,
      feedback: record.feedback ?? null,
      recommendations: record.recommendations ?? null,
      grading: record.grading,
    });
  }
  return result.length > 0 ? result : undefined;
}

function buildChatCacheFolderKey(
  folderId: string | null,
  scope: PracticeChatScope | null | undefined,
  lessonId: string | null | undefined,
): string | null {
  if (scope) {
    const scopeType = scope.scopeType ?? "practice";
    const noteKey = scope.feedbackNoteId ? `::fn::${scope.feedbackNoteId}` : "";
    return `${folderId ?? "generalChat"}::pq::${scope.testSessionId}::${scope.questionId}::${scopeType}${noteKey}`;
  }
  if (lessonId) {
    return `${folderId ?? "generalChat"}::lesson::${lessonId}`;
  }
  return folderId;
}

const MANUAL_TITLE_TTL_MS = 5 * 60 * 1000;

type ManualTitleEntry = { title: string; at: number };

function pruneStaleManualTitles(map: Map<string, ManualTitleEntry>) {
  const now = Date.now();
  for (const [id, v] of map) {
    if (now - v.at > MANUAL_TITLE_TTL_MS) map.delete(id);
  }
}

function mergeServerConversationsWithManualTitles(
  server: ConversationSummary[],
  manualMap: Map<string, ManualTitleEntry>,
): ConversationSummary[] {
  pruneStaleManualTitles(manualMap);
  if (manualMap.size === 0) return server;
  return server.map((c) => {
    const manual = manualMap.get(c.id);
    if (!manual) return c;
    if (c.title === manual.title) {
      manualMap.delete(c.id);
      return c;
    }
    return { ...c, title: manual.title };
  });
}

function migrateManualTitleId(
  manualMap: Map<string, ManualTitleEntry>,
  fromId: string,
  toId: string,
) {
  if (fromId === toId) return;
  const entry = manualMap.get(fromId);
  if (!entry) return;
  manualMap.delete(fromId);
  manualMap.set(toId, entry);
}

type UseChatReturn = {
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  status: ChatStatus;
  error: string | null;
  clearError: VoidFunction;
  isLoading: boolean;
  handleSubmit: (files?: File[]) => void;
  stop: VoidFunction;
  reload: (messagesOverride?: ChatMessage[], editedMessageId?: string) => void;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  conversationId: string | null;
  conversations: ConversationSummary[];
  conversationsLoading: boolean;
  conversationsError: string | null;
  switchConversation: (id: string) => void;
  startNewChat: VoidFunction;
  removeConversation: (id: string) => void;
  conversationTitle: string | null;
  selectedModel: string | null;
  setSelectedModel: (model: string | null) => void;
  selectedReasoning: string | null;
  setSelectedReasoning: (reasoning: string | null) => void;
  currentDocumentId: string | null;
  setCurrentDocumentId: (id: string | null) => void;
  loadMoreMessages: () => Promise<void>;
  hasMoreMessages: boolean;
  retryLoadConversations: VoidFunction;
  taggedPart: TaggedPart | null;
  setTaggedPart: (part: TaggedPart | null) => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  /** Practice hint SSE: reconcile real conversation id from hint_meta (no message reload). */
  reconcileHintConversationId: (realId: string) => void;
  /** Reload current conversation messages from server (e.g. after hint persisted to chat). */
  refreshConversationMessages: () => Promise<void>;
  /** List conversations only (no loadMessages). Use after practice hint to refresh sidebar without wiping the thread. */
  refreshConversationSummaries: () => Promise<void>;
  /** Bump to invalidate any in-flight loadMessages / loadConversations (e.g. hint stream owns messages). */
  bumpLoadGeneration: () => void;
  /** Navigate to a sibling branch for a given message. */
  switchBranch: (messageId: string, direction: "next" | "prev") => Promise<void>;
};

function backendToLocal(msg: MessageSchema): ChatMessage {
  const attachments: FileAttachment[] | undefined = msg.attachments?.length
    ? msg.attachments.map((a) => ({
        name: a.filename,
        type: a.mime_type,
        size: 0,
        url: a.url ?? "",
      }))
    : undefined;

  return {
    id: msg.id,
    role: msg.role as "user" | "assistant",
    content: msg.content,
    metadata: msg.metadata,
    images: msg.images?.length ? msg.images : undefined,
    citations: msg.citations?.length ? msg.citations : undefined,
    attachments,
    createdAt: msg.created_at,
    parentId: msg.parent_id ?? null,
    siblingCount: msg.sibling_count ?? 1,
    versionIndex: msg.version_index ?? 1,
  };
}

async function cacheConversations(
  folderId: string | null,
  conversations: ConversationSummary[],
) {
  try {
    await db.conversations
      .where("folder_id")
      .equals(folderId ?? "generalChat")
      .delete();
    await db.conversations.bulkPut(
      conversations.map((c) => ({
        ...c,
        folder_id: folderId ?? "generalChat",
      })),
    );
  } catch {
    // silent
  }
}

async function cacheMessages(convId: string, messages: ChatMessage[]) {
  try {
    await db.messages.where("conversationId").equals(convId).delete();
    await db.messages.bulkPut(
      messages.map((m) => ({ ...m, conversationId: convId })),
    );
  } catch {
    // silent
  }
}

async function getCachedConversations(
  folderId: string | null,
): Promise<ConversationSummary[]> {
  try {
    const cached = await db.conversations
      .where("folder_id")
      .equals(folderId ?? "generalChat")
      .reverse()
      .sortBy("updated_at");
    return cached.map(({ folder_id, ...rest }) => {
      void folder_id;
      return rest;
    });
  } catch {
    return [];
  }
}

async function getCachedMessages(convId: string): Promise<ChatMessage[]> {
  try {
    const cached = await db.messages
      .where("conversationId")
      .equals(convId)
      .sortBy("createdAt");
    return cached.map(({ conversationId, ...rest }) => {
      void conversationId;
      return rest;
    });
  } catch {
    return [];
  }
}

export function useChat({
  folderId,
  initialConversationId,
  practiceChatScope,
  lessonId,
  currentBlockId,
  inlineQuizAnswers,
}: UseChatOptions): UseChatReturn {
  const cacheFolderKey = useMemo(
    () =>
      buildChatCacheFolderKey(
        folderId,
        practiceChatScope ?? null,
        practiceChatScope ? null : lessonId ?? null,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- primitives avoid parent object identity churn
    [
      folderId,
      practiceChatScope?.testSessionId,
      practiceChatScope?.questionId,
      practiceChatScope?.scopeType,
      practiceChatScope?.feedbackNoteId,
      lessonId,
    ],
  );

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [taggedPart, setTaggedPart] = useState<TaggedPart | null>(null);
  const [status, setStatus] = useState<ChatStatus>("ready");
  const [error, setError] = useState<string | null>(null);
  const clearError = useCallback(() => {
    setError(null);
  }, []);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsError, setConversationsError] = useState<string | null>(
    null,
  );
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [selectedReasoning, setSelectedReasoning] = useState<string | null>(null);
  const [currentDocumentId, setCurrentDocumentId] = useState<string | null>(
    null,
  );
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const nextCursorRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const optimisticIdRef = useRef<string | null>(null);
  const messagesRef = useRef(messages);
  const conversationIdRef = useRef(conversationId);
  const currentDocumentIdRef = useRef(currentDocumentId);
  /** Current chat scope (folder / practice / lesson); used to ignore stale async after lesson/tab switch. */
  const chatScopeKeyRef = useRef(cacheFolderKey);
  chatScopeKeyRef.current = cacheFolderKey;
  /** Monotonic counter — bumped to invalidate in-flight loadMessages / loadConversations calls. */
  const loadGenRef = useRef(0);
  const currentBlockIdRef = useRef(currentBlockId);
  const inlineQuizAnswersRef = useRef(inlineQuizAnswers);
  /** Cache of sibling messages: messageId -> ChatMessage[] (all siblings in the group). */
  const siblingsCacheRef = useRef<Map<string, ChatMessage[]>>(new Map());
  const manualTitlesRef = useRef<Map<string, ManualTitleEntry>>(new Map());

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);
  useEffect(() => {
    currentDocumentIdRef.current = currentDocumentId;
  }, [currentDocumentId]);
  useEffect(() => {
    currentBlockIdRef.current = currentBlockId;
  }, [currentBlockId]);
  useEffect(() => {
    inlineQuizAnswersRef.current = inlineQuizAnswers;
  }, [inlineQuizAnswers]);

  const conversationTitle =
    conversations.find((c) => c.id === conversationId)?.title ?? null;

  const initialIdRef = useRef(initialConversationId ?? null);
  const activeCacheKeyRef = useRef<string | null>(cacheFolderKey);

  const fetchSiblings = useCallback(async (convId: string, messageId: string) => {
    const token = getAccessToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(
      `${apiStreamOrigin()}/api/v1/chat/conversations/${convId}/messages/${messageId}/siblings`,
      { headers },
    );
    if (!res.ok) return;
    const data = (await res.json()) as { siblings: SiblingApiRow[] };

    const siblings: ChatMessage[] = data.siblings.map((s) => ({
      id: s.id,
      role: s.role as "user" | "assistant",
      content: s.content,
      metadata: s.metadata,
      createdAt: s.created_at,
      parentId: s.parent_id ?? null,
      siblingCount: data.siblings.length,
      versionIndex: s.version_index,
    }));

    // Key by each sibling's message ID so any of them can look up the group
    for (const s of siblings) {
      siblingsCacheRef.current.set(s.id, siblings);
    }
  }, []);

  const loadMessages = useCallback(async (convId: string) => {
    const scopeAtStart = chatScopeKeyRef.current;
    const genAtStart = loadGenRef.current;
    try {
      const res =
        await getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet(
          convId,
          undefined,
        );
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (loadGenRef.current !== genAtStart) return;
      if (res.status !== 200) return;

      const data = res.data as {
        messages: MessageSchema[];
        has_more: boolean;
        next_cursor?: string | null;
      };
      const fresh = data.messages.map(backendToLocal);
      setMessages(fresh);
      setHasMoreMessages(data.has_more);
      nextCursorRef.current = data.next_cursor ?? null;

      cacheMessages(convId, fresh);

      // Pre-fetch siblings for messages that have branches (background, non-blocking)
      const branchedMessages = fresh.filter((m) => m.siblingCount > 1);
      for (const msg of branchedMessages) {
        fetchSiblings(convId, msg.id).catch(() => {});
      }
    } catch {
      // keep cached data if network fails
    }
  }, [fetchSiblings]);

  const loadConversationsRef = useRef<() => Promise<void>>(async () => {});

  const loadConversations = useCallback(async () => {
    const scopeAtStart = chatScopeKeyRef.current;
    const genAtStart = loadGenRef.current;
    setConversationsLoading(true);
    setConversationsError(null);

    let cachedConvs: ConversationSummary[] = [];

    // General chat (no folder/practice/lesson): always open fresh — never auto-resume the
    // last conversation. Only an explicit initialConversationId / current id wins.
    const isGeneralScope = !folderId && !practiceChatScope && !lessonId;

    try {
      const targetId = initialIdRef.current ?? conversationIdRef.current;

      cachedConvs = await getCachedConversations(cacheFolderKey);
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (loadGenRef.current !== genAtStart) return;

      if (cachedConvs.length > 0) {
        setConversations(
          mergeServerConversationsWithManualTitles(
            cachedConvs,
            manualTitlesRef.current,
          ),
        );
        const pickId =
          targetId ?? (isGeneralScope ? null : cachedConvs[0]?.id ?? null);
        if (pickId) {
          setConversationId(pickId);
          conversationIdRef.current = pickId;
          const cachedMsgs = await getCachedMessages(pickId);
          if (chatScopeKeyRef.current !== scopeAtStart) return;
          if (loadGenRef.current !== genAtStart) return;
          if (cachedMsgs.length > 0) {
            setMessages(cachedMsgs);
          } else {
            setIsLoading(true);
          }
        } else {
          setIsLoading(true);
        }
      } else {
        if (targetId) {
          setConversationId(targetId);
          conversationIdRef.current = targetId;
        }
        setIsLoading(true);
      }

      const listParams: ListConversationsQueryParams = {};
      if (folderId) listParams.folder_id = folderId;
      if (practiceChatScope) {
        listParams.test_session_id = practiceChatScope.testSessionId;
        listParams.question_id = practiceChatScope.questionId;
        listParams.scope_type = practiceChatScope.scopeType ?? "practice";
        if (practiceChatScope.feedbackNoteId) {
          listParams.feedback_note_id = practiceChatScope.feedbackNoteId;
        }
      } else if (lessonId) {
        listParams.lesson_id = lessonId;
      }
      const convRes = await listConversationsApiV1ChatConversationsGet(
        Object.keys(listParams).length > 0 ? listParams : undefined,
      );
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (loadGenRef.current !== genAtStart) return;

      if (convRes.status === 200) {
        const data = convRes.data as { conversations: ConversationSummary[] };
        const merged = mergeServerConversationsWithManualTitles(
          data.conversations,
          manualTitlesRef.current,
        );
        setConversations(merged);
        cacheConversations(cacheFolderKey, merged);

        const currentId = conversationIdRef.current;
        if (currentId) {
          await loadMessages(currentId);
          if (chatScopeKeyRef.current !== scopeAtStart) return;
        } else if (!isGeneralScope && data.conversations.length > 0) {
          const latest = data.conversations[0];
          setConversationId(latest.id);
          conversationIdRef.current = latest.id;
          await loadMessages(latest.id);
          if (chatScopeKeyRef.current !== scopeAtStart) return;
        } else {
          if (loadGenRef.current !== genAtStart) return;
          setMessages([]);
        }
      }
    } catch {
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (cachedConvs.length === 0) {
        setConversations([]);
      }
      setConversationsError("Failed to load conversations");
    } finally {
      if (chatScopeKeyRef.current === scopeAtStart) {
        setIsLoading(false);
        setConversationsLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scope fields listed explicitly
  }, [
    cacheFolderKey,
    folderId,
    practiceChatScope?.testSessionId,
    practiceChatScope?.questionId,
    lessonId,
    loadMessages,
  ]);
  loadConversationsRef.current = loadConversations;

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    optimisticIdRef.current = null;
    siblingsCacheRef.current = new Map();
    manualTitlesRef.current.clear();
    setMessages([]);
    setConversationId(null);
    conversationIdRef.current = null;
    initialIdRef.current = null;
    setConversations([]);
    setError(null);
    setConversationsError(null);
    setStatus("ready");
    loadConversationsRef.current();
  }, [cacheFolderKey]);

  const refreshConversationMessages = useCallback(async () => {
    const id = conversationIdRef.current;
    if (!id) return;
    await loadMessages(id);
  }, [loadMessages]);

  const refreshConversationSummaries = useCallback(async () => {
    const scopeAtStart = chatScopeKeyRef.current;
    try {
      const listParams: ListConversationsQueryParams = {};
      if (folderId) listParams.folder_id = folderId;
      if (practiceChatScope) {
        listParams.test_session_id = practiceChatScope.testSessionId;
        listParams.question_id = practiceChatScope.questionId;
        listParams.scope_type = practiceChatScope.scopeType ?? "practice";
        if (practiceChatScope.feedbackNoteId) {
          listParams.feedback_note_id = practiceChatScope.feedbackNoteId;
        }
      } else if (lessonId) {
        listParams.lesson_id = lessonId;
      }
      const convRes = await listConversationsApiV1ChatConversationsGet(
        Object.keys(listParams).length > 0 ? listParams : undefined,
      );
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (convRes.status === 200) {
        const data = convRes.data as { conversations: ConversationSummary[] };
        const merged = mergeServerConversationsWithManualTitles(
          data.conversations,
          manualTitlesRef.current,
        );
        setConversations(merged);
        cacheConversations(cacheFolderKey, merged);
      }
    } catch {
      // keep current list
    }
  }, [cacheFolderKey, folderId, practiceChatScope, lessonId]);

  const reconcileHintConversationId = useCallback(
    (realId: string) => {
      if (!realId) return;
      if (conversationIdRef.current === realId && !optimisticIdRef.current) return;

      const tempId = optimisticIdRef.current;

      conversationIdRef.current = realId;
      setConversationId(realId);

      if (tempId) {
        optimisticIdRef.current = null;
        migrateManualTitleId(manualTitlesRef.current, tempId, realId);
        setConversations((prev) => {
          const withoutDuplicate = prev.filter((c) => c.id !== realId);
          return withoutDuplicate.map((c) =>
            c.id === tempId
              ? { ...c, id: realId, updated_at: new Date().toISOString() }
              : c,
          );
        });
      } else {
        setConversations((prev) => {
          if (prev.some((c) => c.id === realId)) return prev;
          const newConv: ConversationSummary = {
            id: realId,
            title: "New Chat",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 0,
            last_message_preview: "",
            ...(practiceChatScope
              ? {
                  test_session_id: practiceChatScope.testSessionId,
                  question_id: practiceChatScope.questionId,
                }
              : lessonId && !practiceChatScope
                ? { lesson_id: lessonId }
                : {}),
          };
          return [newConv, ...prev];
        });
      }
    },
    [lessonId, practiceChatScope],
  );

  /** Bump to invalidate any in-flight loadMessages / loadConversations (e.g. hint stream owns messages). */
  const bumpLoadGeneration = useCallback(() => {
    loadGenRef.current++;
  }, []);

  const loadMoreMessages = useCallback(async () => {
    const convId = conversationIdRef.current;
    if (!convId || !hasMoreMessages || !nextCursorRef.current) return;

    const scopeAtStart = chatScopeKeyRef.current;
    try {
      const res =
        await getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet(
          convId,
          { cursor: nextCursorRef.current },
        );
      if (chatScopeKeyRef.current !== scopeAtStart) return;
      if (res.status !== 200) return;

      const data = res.data as {
        messages: MessageSchema[];
        has_more: boolean;
        next_cursor?: string | null;
      };

      const olderMessages = data.messages.map(backendToLocal);
      setMessages((prev) => {
        const merged = [...olderMessages, ...prev];
        cacheMessages(convId, merged);
        return merged;
      });
      setHasMoreMessages(data.has_more);
      nextCursorRef.current = data.next_cursor ?? null;
    } catch {
      // silent
    }
  }, [hasMoreMessages]);

  const switchConversation = useCallback(
    async (id: string) => {
      if (id === conversationIdRef.current) return;
      abortRef.current?.abort();
      abortRef.current = null;
      siblingsCacheRef.current = new Map();

      const myKey = activeCacheKeyRef.current;
      conversationIdRef.current = id;
      setConversationId(id);
      setStatus("ready");
      setError(null);
      setHasMoreMessages(false);
      nextCursorRef.current = null;

      const cached = await getCachedMessages(id);
      if (activeCacheKeyRef.current !== myKey) return;
      if (cached.length > 0) {
        setMessages(cached);
      } else {
        setMessages([]);
      }

      loadMessages(id);
    },
    [loadMessages],
  );

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    loadGenRef.current++;
    siblingsCacheRef.current = new Map();

    conversationIdRef.current = null;
    setConversationId(null);
    setMessages([]);
    setInput("");
    setStatus("ready");
    setError(null);
    setHasMoreMessages(false);
    nextCursorRef.current = null;
  }, []);

  const removeConversation = useCallback(
    async (id: string) => {
      manualTitlesRef.current.delete(id);
      // Snapshot for rollback
      let removed: ConversationSummary | undefined;
      let removedIndex = -1;

      // Optimistic: remove from UI immediately
      setConversations((prev) => {
        removedIndex = prev.findIndex((c) => c.id === id);
        if (removedIndex !== -1) removed = prev[removedIndex];
        return prev.filter((c) => c.id !== id);
      });

      if (conversationIdRef.current === id) {
        startNewChat();
      }

      try {
        await deleteConversationApi(id);

        // Clean up local DB in the background
        db.conversations.delete(id).catch(() => {});
        db.messages
          .where("conversationId")
          .equals(id)
          .delete()
          .catch(() => {});
      } catch {
        // Restore on failure
        if (removed) {
          const snapshot = removed;
          const idx = removedIndex;
          setConversations((prev) => {
            // Avoid duplicates if somehow re-added
            if (prev.some((c) => c.id === id)) return prev;
            const next = [...prev];
            next.splice(Math.min(idx, next.length), 0, snapshot);
            return next;
          });
        }
      }
    },
    [startNewChat],
  );

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      manualTitlesRef.current.set(id, { title, at: Date.now() });
      setConversations((prev) => {
        const updated = prev.map((c) => (c.id === id ? { ...c, title } : c));
        cacheConversations(cacheFolderKey, updated);
        return updated;
      });
      try {
        await renameConversationApi(id, { title });
      } catch {
        manualTitlesRef.current.delete(id);
        loadConversations();
      }
    },
    [loadConversations, cacheFolderKey],
  );

  const streamResponse = useCallback(
    async (
      userContent: string,
      convId: string | null,
      model: string | null,
      reasoning: string | null,
      documentId: string | null,
      options?: {
        images?: string[]
        citations?: string[]
        attachments?: FileAttachmentPayload[]
      },
    ) => {
      // Abort any in-flight stream before starting a new one (prevents
      // stale post-processing from corrupting the messages array).
      abortRef.current?.abort();
      abortRef.current = null;

      setStatus("submitted");
      setError(null);

      const assistantNanoId = nanoid();
      const assistantMessage: ChatMessage = {
        id: assistantNanoId,
        _renderKey: assistantNanoId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        siblingCount: 1,
        versionIndex: 1,
      };

      const abortController = new AbortController();
      abortRef.current = abortController;
      let realAssistantId: string | null = null;
      let realUserMessageId: string | null = null;

      try {
        let firstToken = true;
        let pendingUpdate = false;
        let receivedConversationId = convId;

        const effectiveConversationId =
          convId && !convId.startsWith("__optimistic_") ? convId : undefined;

        const generator = streamChatMessage(
          {
            conversation_id: effectiveConversationId,
            folder_id: folderId,
            ...(practiceChatScope
              ? {
                  test_session_id: practiceChatScope.testSessionId,
                  question_id: practiceChatScope.questionId,
                  scope_type: practiceChatScope.scopeType ?? "practice",
                  ...(practiceChatScope.feedbackNoteId
                    ? { feedback_note_id: practiceChatScope.feedbackNoteId }
                    : {}),
                }
              : lessonId
                ? {
                    lesson_id: lessonId,
                    current_block_id: currentBlockIdRef.current ?? undefined,
                    inline_quiz_answers: serializeInlineQuizAnswers(inlineQuizAnswersRef.current),
                  }
                : {}),
            message: userContent,
            model: model ?? undefined,
            reasoning: reasoning ?? undefined,
            current_document_id: documentId ?? undefined,
            images: options?.images?.length ? options.images : undefined,
            citations: options?.citations?.length ? options.citations : undefined,
            attachments: options?.attachments?.length ? options.attachments : undefined,
          },
          { signal: abortController.signal },
        );

        for await (const event of generator) {
          if (abortController.signal.aborted) break;

          if (event.type === "metadata") {
            if (event.conversation_id && !receivedConversationId) {
              // First metadata: reconcile optimistic ID with real backend ID
              receivedConversationId = event.conversation_id;
              const realId = event.conversation_id;
              const backendTitle = event.title ?? null;
              const tempId = optimisticIdRef.current;

              setConversationId(realId);

              if (tempId) {
                // Reconcile optimistic placeholder with real backend data
                optimisticIdRef.current = null;
                migrateManualTitleId(manualTitlesRef.current, tempId, realId);
                const manualTitle = manualTitlesRef.current.get(realId);
                setConversations((prev) => {
                  const withoutDuplicate = prev.filter(
                    (c) => c.id !== realId,
                  );
                  return withoutDuplicate.map((c) =>
                    c.id === tempId
                      ? {
                          ...c,
                          id: realId,
                          title:
                            manualTitle?.title ??
                            backendTitle ??
                            c.title ??
                            "New Chat",
                          updated_at: new Date().toISOString(),
                        }
                      : c,
                  );
                });
              } else {
                // No optimistic entry — add new conversation (fallback)
                const manualTitle = manualTitlesRef.current.get(realId);
                setConversations((prev) => {
                  const exists = prev.some((c) => c.id === realId);
                  if (exists) return prev;
                  const newConv: ConversationSummary = {
                    id: realId,
                    title: manualTitle?.title ?? backendTitle ?? "New Chat",
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                    message_count: 1,
                    last_message_preview: "",
                    ...(lessonId && !practiceChatScope
                      ? { lesson_id: lessonId }
                      : {}),
                  };
                  return [newConv, ...prev];
                });
              }
            } else if (event.title && receivedConversationId) {
              const titleUpdate = event.title;
              const targetId = receivedConversationId;
              const manual = manualTitlesRef.current.get(targetId);
              if (!manual || titleUpdate === manual.title) {
                setConversations((prev) => {
                  const target = prev.find((c) => c.id === targetId);
                  if (!target || target.title === titleUpdate) return prev;
                  const updated = prev.map((c) =>
                    c.id === targetId ? { ...c, title: titleUpdate } : c,
                  );
                  cacheConversations(cacheFolderKey, updated);
                  return updated;
                });
              }
            }
            // Capture real message IDs — but DON'T mutate during
            // streaming, or RAF callbacks will see a changed ID and append
            // a duplicate instead of updating.  We apply them in the final
            // setMessages after the loop.
            if (event.message_id) {
              realAssistantId = event.message_id;
            }
            if (event.user_message_id) {
              realUserMessageId = event.user_message_id;
            }
            continue;
          }

          // stream_end arrives right after the last token, before DB
          // writes / title generation. Flip the button immediately.
          // The loop continues to receive message_complete with real IDs.
          // If the user sends a new message or regenerates, the abort at
          // the start of streamResponse/streamRegenerate kills this loop.
          if (event.type === "stream_end") {
            setStatus("ready");
            continue;
          }

          if (event.type === "error") {
            // Clean up optimistic entry on stream error
            const tempId = optimisticIdRef.current;
            if (tempId) {
              optimisticIdRef.current = null;
              manualTitlesRef.current.delete(tempId);
              setConversations((prev) => prev.filter((c) => c.id !== tempId));
              setConversationId(convId);
            }
            setError(event.message);
            setStatus("error");
            return;
          }

          if (event.type === "done") break;

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
                // Skip if this stream was aborted (new message sent) —
                // otherwise the stale snapshot gets appended as a duplicate.
                if (abortController.signal.aborted) return;
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

        // Apply the real DB IDs now that streaming is done.
        // Only create new message objects when IDs actually changed —
        // unnecessary object replacement causes MarkdownContent to
        // re-parse and blink.
        if (realAssistantId) {
          assistantMessage.id = realAssistantId;
        }
        setMessages((prev) => {
          let changed = false;
          let final = prev;

          // Reconcile assistant message ID
          const lastIdx = final.length - 1;
          if (lastIdx >= 0 && final[lastIdx].role === "assistant") {
            if (final[lastIdx].id !== assistantMessage.id || final[lastIdx].content !== assistantMessage.content) {
              final = final.slice();
              final[lastIdx] = { ...final[lastIdx], id: assistantMessage.id, content: assistantMessage.content };
              changed = true;
            }
          } else {
            final = [...final, { ...assistantMessage }];
            changed = true;
          }

          // Reconcile the user message's optimistic nanoid → real UUID.
          if (realUserMessageId) {
            for (let i = final.length - 1; i >= 0; i--) {
              if (final[i].role === "user") {
                if (final[i].id !== realUserMessageId) {
                  if (!changed) final = final.slice();
                  final[i] = { ...final[i], id: realUserMessageId };
                  changed = true;
                }
                break;
              }
            }
          }

          if (changed && receivedConversationId) {
            cacheMessages(receivedConversationId, final);
          }
          return changed ? final : prev;
        });

        // Update conversation preview with the final assistant message
        if (receivedConversationId) {
          const preview = assistantMessage.content.slice(0, 100);
          setConversations((prev) => {
            const updated = prev.map((c) =>
              c.id === receivedConversationId
                ? { ...c, last_message_preview: preview, updated_at: new Date().toISOString() }
                : c,
            );
            cacheConversations(cacheFolderKey, updated);
            return updated;
          });
        }
      } catch (err) {
        const cleanupOptimistic = () => {
          const tempId = optimisticIdRef.current;
          if (tempId) {
            optimisticIdRef.current = null;
            manualTitlesRef.current.delete(tempId);
            setConversations((prev) => prev.filter((c) => c.id !== tempId));
            setConversationId(null);
          }
        };

        if (err instanceof DOMException && err.name === "AbortError") {
          // user stopped — keep the optimistic entry if backend already assigned a real ID
          if (optimisticIdRef.current) {
            cleanupOptimistic();
          }
        } else if (err instanceof Error && err.message === "AUTH_EXPIRED") {
          cleanupOptimistic();
          setError("Session expired. Please log in again.");
          setStatus("error");
          return;
        } else {
          cleanupOptimistic();
          setError(err instanceof Error ? err.message : "Error occurred");
          setStatus("error");
          return;
        }
      } finally {
        abortRef.current = null;
      }

      setStatus("ready");
    },
    [folderId, practiceChatScope, lessonId, cacheFolderKey],
  );

  const handleSubmit = useCallback(async (files?: File[]) => {
    const trimmed = input.trim();
    const hasFiles = files && files.length > 0;
    if ((!trimmed && !hasFiles) || status === "streaming" || status === "submitted") return;

    // Capture and clear tagged part before send
    const currentTaggedPart = taggedPart;
    setTaggedPart(null);

    // Convert image files to base64 and non-image files to attachments
    let base64Images: string[] | undefined;
    let attachmentPayloads: FileAttachmentPayload[] | undefined;
    try {
      if (hasFiles) {
        base64Images = await imagesToBase64(files);
        attachmentPayloads = await filesToAttachments(files);
      }
    } catch {
      setError("Failed to process attached files");
      setStatus("error");
      return;
    }

    // Build citations from tagged part
    const citations = currentTaggedPart ? [currentTaggedPart.text] : undefined;

    // Build local file attachments for message display
    const nonImageFiles = hasFiles
      ? files.filter((f) => !f.type.startsWith("image/") || f.name.toLowerCase().endsWith(".heic") || f.name.toLowerCase().endsWith(".heif"))
      : [];
    const localAttachments: FileAttachment[] = nonImageFiles.map((f) => ({
      name: f.name,
      type: f.type || "application/octet-stream",
      size: f.size,
      url: "",
    }));

    const userNanoId = nanoid();
    const userMessage: ChatMessage = {
      id: userNanoId,
      _renderKey: userNanoId,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
      images: base64Images?.length ? base64Images : undefined,
      citations,
      attachments: localAttachments.length ? localAttachments : undefined,
      siblingCount: 1,
      versionIndex: 1,
      ...(currentTaggedPart && {
        metadata: { tagged_part: currentTaggedPart },
      }),
    };

    // Use functional update to avoid reading stale messagesRef —
    // a RAF from a previous stream may have called setMessages but
    // the useEffect that syncs messagesRef hasn't run yet.
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    // Optimistic conversation creation for new chats
    if (!conversationIdRef.current) {
      const tempId = `__optimistic_${nanoid()}`;
      optimisticIdRef.current = tempId;

      const optimisticConv: ConversationSummary = {
        id: tempId,
        title: "New Chat",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 1,
        last_message_preview: "New Chat",
        ...(lessonId && !practiceChatScope ? { lesson_id: lessonId } : {}),
      };

      setConversationId(tempId);
      setConversations((prev) => [optimisticConv, ...prev]);
    } else if (conversationIdRef.current) {
      // Best-effort cache — uses ref which may lag slightly
      cacheMessages(conversationIdRef.current, [...messagesRef.current, userMessage]);
    }

    streamResponse(
      trimmed,
      conversationIdRef.current,
      selectedModel,
      selectedReasoning,
      currentDocumentIdRef.current,
      {
        images: base64Images?.length ? base64Images : undefined,
        citations,
        attachments: attachmentPayloads?.length ? attachmentPayloads : undefined,
      },
    );
  }, [
    input,
    status,
    streamResponse,
    selectedModel,
    selectedReasoning,
    taggedPart,
    lessonId,
    practiceChatScope,
  ]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus("ready");
  }, []);

  const streamRegenerate = useCallback(
    async (
      convId: string,
      messageId: string,
      newContent: string,
      model: string | null,
      reasoning: string | null,
    ) => {
      abortRef.current?.abort();
      abortRef.current = null;

      setStatus("submitted");
      setError(null);

      const regenNanoId = nanoid();
      const assistantMessage: ChatMessage = {
        id: regenNanoId,
        _renderKey: regenNanoId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        siblingCount: 1,
        versionIndex: 1,
      };

      const abortController = new AbortController();
      abortRef.current = abortController;
      let realRegenId: string | null = null;
      let realUserMessageId: string | null = null;

      try {
        let firstToken = true;
        let pendingUpdate = false;

        const generator = streamRegenerateMessage(
          convId,
          messageId,
          { message: newContent, model: model ?? undefined, reasoning: reasoning ?? undefined },
          { signal: abortController.signal },
        );

        for await (const event of generator) {
          if (abortController.signal.aborted) break;

          if (event.type === "error") {
            setError(event.message);
            setStatus("error");
            return;
          }

          if (event.type === "done") break;

          if (event.type === "stream_end") {
            setStatus("ready");
            continue;
          }

          if (event.type === "metadata") {
            if (event.message_id) {
              realRegenId = event.message_id;
            }
            if (event.user_message_id) {
              realUserMessageId = event.user_message_id;
            }
            continue;
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
                // Skip if this stream was aborted (new message sent) —
                // otherwise the stale snapshot gets appended as a duplicate.
                if (abortController.signal.aborted) return;
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

        if (realRegenId) {
          assistantMessage.id = realRegenId;
        }
        setMessages((prev) => {
          let changed = false;
          let final = prev;

          const lastIdx = final.length - 1;
          if (lastIdx >= 0 && final[lastIdx].role === "assistant") {
            if (final[lastIdx].id !== assistantMessage.id || final[lastIdx].content !== assistantMessage.content) {
              final = final.slice();
              final[lastIdx] = { ...final[lastIdx], id: assistantMessage.id, content: assistantMessage.content };
              changed = true;
            }
          } else {
            final = [...final, { ...assistantMessage }];
            changed = true;
          }

          // Reconcile the user message's optimistic nanoid → real UUID
          if (realUserMessageId) {
            for (let i = final.length - 1; i >= 0; i--) {
              if (final[i].role === "user") {
                if (final[i].id !== realUserMessageId) {
                  if (!changed) final = final.slice();
                  final[i] = { ...final[i], id: realUserMessageId };
                  changed = true;
                }
                break;
              }
            }
          }

          if (changed) cacheMessages(convId, final);
          return changed ? final : prev;
        });

        // Update sibling counts in-place (real IDs are reconciled above)
        try {
          const res =
            await getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet(
              convId, undefined,
            );
          if (res.status === 200) {
            const data = res.data as { messages: MessageSchema[] };
            const countMap = new Map(
              data.messages.map((m) => [
                m.id,
                { siblingCount: m.sibling_count ?? 1, versionIndex: m.version_index ?? 1 },
              ]),
            );
            setMessages((prev) => {
              let changed = false;
              const next = prev.map((msg) => {
                const fresh = countMap.get(msg.id);
                if (fresh && (msg.siblingCount !== fresh.siblingCount || msg.versionIndex !== fresh.versionIndex)) {
                  changed = true;
                  return { ...msg, siblingCount: fresh.siblingCount, versionIndex: fresh.versionIndex };
                }
                return msg;
              });
              return changed ? next : prev;
            });
          }
        } catch { /* non-critical */ }

      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : "Error occurred");
          setStatus("error");
          return;
        }
      } finally {
        abortRef.current = null;
      }

      setStatus("ready");
    },
    [],
  );

  const reload = useCallback(
    (messagesOverride?: ChatMessage[], editedMessageId?: string) => {
      const currentMessages = messagesOverride ?? messagesRef.current;
      const convId = conversationIdRef.current;
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

      const targetId = editedMessageId
        ?? (lastMsg.role === "assistant" ? lastMsg.id : lastUserMsg.id);

      // Use streamRegenerate only when we have a real conversation AND a valid
      // UUID message ID.  Hint messages start with nanoid IDs that haven't been
      // reconciled yet — fall back to streamResponse for those.
      const isValidUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(targetId);

      if (convId && isValidUuid) {
        streamRegenerate(
          convId,
          targetId,
          lastUserMsg.content,
          selectedModel,
          selectedReasoning,
        );
      } else {
        streamResponse(
          lastUserMsg.content,
          convId,
          selectedModel,
          selectedReasoning,
          currentDocumentIdRef.current,
        );
      }
    },
    [streamRegenerate, streamResponse, selectedModel, selectedReasoning],
  );

  const handleSwitchBranch = useCallback(
    async (messageId: string, direction: "next" | "prev") => {
      const convId = conversationIdRef.current;
      if (!convId || status !== "ready") return;

      // Always use server round-trip: the sibling may have children (subtree)
      // that only the backend can walk correctly via the recursive CTE.
      try {
        const { switchBranch } = await import("@/shared/api/chat-branch");
        const response = await switchBranch(convId, messageId, direction);

        const branchIndex = messagesRef.current.findIndex((m) => m.id === messageId);
        if (branchIndex === -1) return;

        const newTailMessages: ChatMessage[] = response.messages.map((msg) => ({
          id: msg.id,
          role: msg.role as "user" | "assistant",
          content: msg.content,
          metadata: msg.metadata,
          images: msg.images?.length ? msg.images : undefined,
          citations: msg.citations?.length ? msg.citations : undefined,
          attachments: msg.attachments?.length
            ? msg.attachments.map((a) => ({
                name: a.filename,
                type: a.mime_type,
                size: 0,
                url: a.url ?? "",
              }))
            : undefined,
          createdAt: msg.created_at,
          parentId: msg.parent_id ?? null,
          siblingCount: msg.sibling_count,
          versionIndex: msg.version_index,
        }));

        const head = messagesRef.current.slice(0, branchIndex);
        const newMessages = [...head, ...newTailMessages];

        setMessages(newMessages);
        cacheMessages(convId, newMessages);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to switch branch");
      }
    },
    [status],
  );

  return {
    messages,
    input,
    setInput,
    status,
    error,
    clearError,
    isLoading,
    handleSubmit,
    stop,
    reload,
    setMessages,
    conversationId,
    conversations,
    conversationsLoading,
    conversationsError,
    switchConversation,
    startNewChat,
    removeConversation,
    conversationTitle,
    selectedModel,
    setSelectedModel,
    selectedReasoning,
    setSelectedReasoning,
    currentDocumentId,
    setCurrentDocumentId,
    loadMoreMessages,
    hasMoreMessages,
    retryLoadConversations: loadConversations,
    taggedPart,
    setTaggedPart,
    renameConversation,
    reconcileHintConversationId,
    refreshConversationMessages,
    refreshConversationSummaries,
    bumpLoadGeneration,
    switchBranch: handleSwitchBranch,
  };
}
