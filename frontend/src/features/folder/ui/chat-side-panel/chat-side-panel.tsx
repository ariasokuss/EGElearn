"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { nanoid } from "nanoid";

import type { ChatMessage } from "@/entities/chat";
import { useChat, ChatInput } from "@/features/chat";
import { ChatThread, type ChatThreadHandle } from "@/features/chat/ui/chat-thread";
import type { PracticeChatScope } from "@/features/chat/model";
import { useFileDrop } from "@/features/chat/model";
import {
  getEffectiveReasoning,
  getReasoningToSend,
  getVisibleReasoningLevels,
} from "@/features/chat/model/reasoning-options";
import type { AnswerRecord } from "../lesson-panel/use-inline-quiz";
import { useAvailableModels } from "@/features/chat/model/use-available-models";
import { DropOverlay } from "@/features/chat/ui/drop-overlay";
import { useNotes } from "../../model/notes-context";
import { NotebookList } from "./notebook-list";

import { ChatHistoryList } from "@/features/chat/ui/history/chat-history-list";
import { HideBarIcon, PencilEditIcon } from "@/shared/assets/icons";
import { TabsNav, type TabItem } from "@/shared/ui/tabs-nav/tabs-nav";
import { Button } from "@/shared";
import { savePracticeHint } from "@/shared/api/save-practice-hint";
import { getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet } from "@/shared/api/generated/api";

const TAB_KEYS_WITH_NOTEBOOK = ["Chat", "History", "Notebook"] as const;
const TAB_KEYS_NO_NOTEBOOK = ["Chat", "History"] as const;
type Tab = (typeof TAB_KEYS_WITH_NOTEBOOK)[number];

type SetTaggedPartFn = (text: string) => void;

type ChatSidePanelProps = {
  folderId: string;
  /** Practice Questions: API scope for list + messages (per question). */
  practiceChatScope?: PracticeChatScope | null;
  lessonId?: string | null;
  /** The currently visible lesson block UUID — forwarded to the chat API. */
  currentBlockId?: string | null;
  /** Inline quiz answers from the lesson — forwarded to the chat API for context. */
  inlineQuizAnswers?: Map<string, AnswerRecord> | null;
  /** When false, hides the Notebook tab (e.g. Practice test chat). Default true. */
  showNotebook?: boolean;
  /** Practice: increment to insert pre-generated hint as a chat message. */
  hintRequestNonce?: number;
  /** Practice: the pre-generated hint text to display when nonce increments. */
  pendingHintText?: string | null;
  tabsClassName?: string;
  headerAfter?: React.ReactNode;
  onNewChatRef?: React.MutableRefObject<VoidFunction | null>;
  onSetTaggedPartRef?: React.MutableRefObject<SetTaggedPartFn | null>;
  onSwitchToNotebookRef?: React.MutableRefObject<VoidFunction | null>;
  onScrollToHighlightRef?: React.MutableRefObject<((text: string) => void) | null>;
  onClose?: VoidFunction;
};

export function ChatSidePanel({
  folderId,
  practiceChatScope,
  lessonId,
  currentBlockId,
  inlineQuizAnswers,
  showNotebook = true,
  hintRequestNonce = 0,
  pendingHintText,
  tabsClassName,
  headerAfter,
  onNewChatRef,
  onSetTaggedPartRef,
  onSwitchToNotebookRef,
  onScrollToHighlightRef,
  onClose,
}: ChatSidePanelProps) {
  const tabKeys = showNotebook ? TAB_KEYS_WITH_NOTEBOOK : TAB_KEYS_NO_NOTEBOOK;
  const tabs: TabItem[] = tabKeys.map((tab) => ({ key: tab, label: tab }));

  const [activeTab, setActiveTab] = useState<Tab>("Chat");
  const { notes, removeNote, updateNoteComment } = useNotes();

  const displayTab: Tab =
    !showNotebook && activeTab === "Notebook" ? "Chat" : activeTab;

  const activeTabIndex = Math.max(
    0,
    (tabKeys as readonly string[]).indexOf(displayTab),
  );

  const handleTabChange = useCallback(
    (index: number) => {
      const key = tabKeys[index];
      if (key) setActiveTab(key as Tab);
    },
    [tabKeys],
  );

  // --- Chat state (full destructure) ---
  const {
    messages,
    input,
    setInput,
    status,
    error,
    clearError,
    handleSubmit,
    stop,
    reload,
    conversationId,
    conversations,
    conversationsLoading,
    conversationsError,
    switchConversation,
    startNewChat,
    removeConversation,
    renameConversation,
    setSelectedModel,
    setSelectedReasoning,
    retryLoadConversations,
    taggedPart,
    setTaggedPart,
    setMessages,
    bumpLoadGeneration,
    reconcileHintConversationId,
    refreshConversationMessages,
    refreshConversationSummaries,
    switchBranch,
  } = useChat({
    folderId,
    practiceChatScope,
    lessonId: practiceChatScope ? null : lessonId ?? null,
    currentBlockId: practiceChatScope ? null : currentBlockId ?? null,
    inlineQuizAnswers: practiceChatScope ? null : inlineQuizAnswers ?? null,
  });

  useEffect(() => {
    if (displayTab !== "Chat") {
      clearError();
    }
  }, [displayTab, clearError]);

  const handleNewChat = useCallback(() => {
    startNewChat();
    setActiveTab("Chat");
  }, [startNewChat]);

  useEffect(() => {
    if (onNewChatRef) onNewChatRef.current = handleNewChat;
  }, [onNewChatRef, handleNewChat]);

  useEffect(() => {
    if (onSetTaggedPartRef)
      onSetTaggedPartRef.current = (text: string) => {
        setTaggedPart({ text, messageId: "", start: 0, end: 0 });
        setActiveTab("Chat");
      };
  }, [onSetTaggedPartRef, setTaggedPart]);

  useEffect(() => {
    if (onSwitchToNotebookRef)
      onSwitchToNotebookRef.current = () => setActiveTab("Notebook");
  }, [onSwitchToNotebookRef]);

  const {
    models,
    reasoningLevels,
    isLoading: modelsLoading,
    error: modelsError,
  } = useAvailableModels();

  const [userSelectedModelId, setUserSelectedModelId] = useState<string | null>(null);
  const [userSelectedReasoning, setUserSelectedReasoning] = useState<string | null>(null);
  const selectedModelId = userSelectedModelId ?? (models.length > 0 ? models[0].id : "");
  const visibleReasoningLevels = getVisibleReasoningLevels(reasoningLevels);
  const selectedReasoning = getEffectiveReasoning(visibleReasoningLevels, userSelectedReasoning);
  const reasoningToSend = getReasoningToSend(visibleReasoningLevels, selectedReasoning);

  useEffect(() => {
    if (selectedModelId) setSelectedModel(selectedModelId);
  }, [selectedModelId, setSelectedModel]);
  useEffect(() => {
    setSelectedReasoning(reasoningToSend);
  }, [reasoningToSend, setSelectedReasoning]);

  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const { isDragging } = useFileDrop();

  const handleFilesAdded = useCallback((newFiles: File[]) => {
    setAttachedFiles((prev) => [...prev, ...newFiles].slice(0, 5));
  }, []);

  const [hintStreaming, setHintStreaming] = useState(false);

  // --- Message refs for edit/regenerate ---
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // --- Hint: word-by-word streaming + background persist ---
  const reconcileRef = useRef(reconcileHintConversationId);
  useEffect(() => { reconcileRef.current = reconcileHintConversationId; }, [reconcileHintConversationId]);
  const refreshMsgsRef = useRef(refreshConversationMessages);
  useEffect(() => { refreshMsgsRef.current = refreshConversationMessages; }, [refreshConversationMessages]);
  const refreshSummariesRef = useRef(refreshConversationSummaries);
  useEffect(() => { refreshSummariesRef.current = refreshConversationSummaries; }, [refreshConversationSummaries]);

  useEffect(() => {
    if (!practiceChatScope || hintRequestNonce === 0 || !pendingHintText) return;

    // Always start a fresh chat for hints
    startNewChat();
    bumpLoadGeneration();

    const assistantId = nanoid();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      siblingCount: 1,
      versionIndex: 0,
      metadata: { practice_hint: true },
    };
    setMessages([assistantMsg]);
    setHintStreaming(true);

    // Scroll to bottom after insertion
    requestAnimationFrame(() => {
      chatThreadRef.current?.scrollToBottom();
    });

    // Word-by-word streaming effect
    const words = pendingHintText.split(/(\s+)/);
    let idx = 0;
    const timer = setInterval(() => {
      idx += 1;
      const partial = words.slice(0, idx).join("");
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: partial } : m)),
      );
      if (idx >= words.length) {
        clearInterval(timer);
        setHintStreaming(false);
      }
    }, 30);

    // Background persist — always create a new conversation (no conversation_id)
    void savePracticeHint(
      practiceChatScope.testSessionId,
      practiceChatScope.questionId,
      { folder_id: folderId },
    ).then(async ({ conversation_id }) => {
      reconcileRef.current(conversation_id);
      await refreshSummariesRef.current();
      // Reconcile hint message nanoid IDs → real DB UUIDs without wiping
      // any messages the user may have sent in the meantime.
      try {
        const res = await getConversationMessagesApiV1ChatConversationsConversationIdMessagesGet(
          conversation_id, undefined,
        );
        if (res.status === 200) {
          const serverMsgs = (res.data as { messages: Array<{ id: string; role: string; content: string }> }).messages;
          setMessages((prev) => {
            const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
            let changed = false;
            const next = prev.map((m) => {
              if (uuidRe.test(m.id)) return m; // already reconciled
              const match = serverMsgs.find((s) => s.role === m.role && s.content === m.content);
              if (match && match.id !== m.id) {
                changed = true;
                return { ...m, id: match.id };
              }
              return m;
            });
            return changed ? next : prev;
          });
        }
      } catch { /* non-critical — IDs reconcile on next conversation load */ }
    }).catch(() => { /* keep optimistic messages */ });

    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    hintRequestNonce,
    practiceChatScope?.testSessionId,
    practiceChatScope?.questionId,
    setMessages,
    bumpLoadGeneration,
    folderId,
  ]);

  const combinedStatus = hintStreaming ? "streaming" as const : status;

  const isOutboundBusy =
    hintStreaming ||
    status === "streaming" ||
    status === "submitted";

  const handleStop = useCallback(() => {
    stop();
  }, [stop]);

  const chatThreadRef = useRef<ChatThreadHandle>(null);

  // --- Edit & Regenerate (skip for hint messages — they're static, not LLM-generated) ---
  const isHintMessage = (msg: ChatMessage) =>
    msg.metadata?.practice_hint_request === true || msg.metadata?.practice_hint === true;

  const handleEdit = useCallback(
    (index: number, newContent: string) => {
      if (isOutboundBusy) return;
      const msgs = messagesRef.current;
      if (isHintMessage(msgs[index])) return;
      const originalId = msgs[index].id;
      const editedMessage = { ...msgs[index], content: newContent };
      const trimmed = [...msgs.slice(0, index), editedMessage];
      reload(trimmed, originalId);
    },
    [reload, isOutboundBusy],
  );

  const handleRegenerate = useCallback(
    (index: number) => {
      if (isOutboundBusy) return;
      const msgs = messagesRef.current;
      const targetMsg = msgs[index];
      if (!targetMsg || isHintMessage(targetMsg)) return;
      reload(msgs.slice(0, index), targetMsg.id);
    },
    [reload, isOutboundBusy],
  );

  // --- Send with file clearing + scroll ---
  const handleSend = useCallback(() => {
    if (isOutboundBusy) return;
    handleSubmit(attachedFiles.length > 0 ? [...attachedFiles] : undefined);
    setAttachedFiles([]);
    chatThreadRef.current?.scrollOnSend();
  }, [handleSubmit, attachedFiles, isOutboundBusy]);

  // History item click → switch conversation + go to Chat tab
  const handleHistorySelect = useCallback(
    (id: string) => {
      switchConversation(id);
      setActiveTab("Chat");
    },
    [switchConversation],
  );

  const isEmpty =
    messages.length === 0 &&
    combinedStatus === "ready";

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden">
      {/* Header with tabs */}
      <TabsNav
        tabs={tabs}
        activeIndex={activeTabIndex}
        onTabChange={handleTabChange}
        className={tabsClassName ?? "border-b border-[#E8E5E180] px-5 pt-6 pb-2"}
        after={
          headerAfter ?? (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                iconOnly
                type="button"
                onClick={handleNewChat}
                aria-label="New chat"
                title="New chat"
                className="flex items-center justify-center rounded-full h-7 w-7 transition-all duration-150 hover:bg-[#F0EFED] active:bg-[#E8E5E1]"
              >
                <PencilEditIcon />
              </Button>
              <div className="h-4 w-px shrink-0 bg-[#E4E4E77A]" />
              {onClose && (
                <Button
                  size="sm"
                  variant="outline"
                  iconOnly
                  type="button"
                  onClick={onClose}
                  aria-label="Close chat"
                  title="Close chat"
                  className="flex items-center justify-center rounded-full h-7 w-7 transition-all duration-150 hover:bg-[#F0EFED] active:bg-[#E8E5E1]"
                >
                  <HideBarIcon />
                </Button>
              )}
            </div>
          )
        }
      />

      {/* Tab content */}
      {displayTab === "Chat" && (() => {
        const chatInputEl = (
          <ChatInput
            variant="panel"
            autoFocus={false}
            input={input}
            onInputChange={setInput}
            onSubmit={handleSend}
            status={combinedStatus}
            onStop={handleStop}
            attachedFiles={attachedFiles}
            onFilesChange={setAttachedFiles}
            models={models}
            selectedModelId={selectedModelId}
            onModelChange={setUserSelectedModelId}
            reasoningLevels={visibleReasoningLevels}
            selectedReasoning={selectedReasoning}
            onReasoningChange={setUserSelectedReasoning}
            modelsLoading={modelsLoading}
            modelsError={modelsError}
            taggedPart={taggedPart}
            onRemoveTaggedPart={() => setTaggedPart(null)}
          />
        );

        const errorBlock = error && (
          <div className="px-3 pb-1">
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 nova-text-label-tiny text-red-600">
              <span className="flex-1">{error}</span>
              <Button
                rounded={false}
                size="xs"
                type="button"
                onClick={() => reload()}
                className="ml-auto shrink-0 bg-red-100 text-red-700 hover:bg-red-200"
              >
                Retry
              </Button>
            </div>
          </div>
        );

        return (
          <div className="flex flex-1 flex-col overflow-hidden">
            {isEmpty ? (
              <>
                <div className="flex flex-1 items-center justify-center px-6">
                  <p className="text-center nova-text-p-base text-[#A1A1AA]">
                    Ask anything about this lesson
                  </p>
                </div>
                {errorBlock}
                <div className="shrink-0 px-2 pb-2">{chatInputEl}</div>
              </>
            ) : (
              <ChatThread
                ref={chatThreadRef}
                messages={messages}
                status={combinedStatus}
                conversationId={conversationId}
                onEdit={handleEdit}
                onRegenerate={handleRegenerate}
                onSwitchBranch={switchBranch}
                onSetTaggedPart={setTaggedPart}
                followUpdates
                errorSlot={errorBlock}
                inputWrapperClassName="relative shrink-0 px-2 pb-2"
              >
                {chatInputEl}
              </ChatThread>
            )}
          </div>
        );
      })()}

      {displayTab === "History" && (
        <div className="flex-1 overflow-y-auto pt-1">
          <ChatHistoryList
            conversations={conversations}
            activeId={conversationId}
            onSelect={handleHistorySelect}
            onDelete={removeConversation}
            onRename={renameConversation}
            loading={conversationsLoading}
            error={conversationsError}
            onRetry={retryLoadConversations}
          />
        </div>
      )}

      {showNotebook && displayTab === "Notebook" && (
        <div className="flex-1 overflow-y-auto p-4">
          <NotebookList
            notes={notes}
            onDelete={removeNote}
            onUpdateComment={updateNoteComment}
            onSelect={onScrollToHighlightRef ? (note) => onScrollToHighlightRef.current?.(note.text) : undefined}
          />
        </div>
      )}

      {isDragging && !practiceChatScope ? (
        <DropOverlay onFilesAdded={handleFilesAdded} />
      ) : null}
    </div>
  );
}
