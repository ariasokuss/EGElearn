"use client"

import { useState, useCallback, useRef, useEffect, useSyncExternalStore } from "react"
import { AnimatePresence, motion } from "motion/react"

import {
  useChat,
  useFileDrop,
} from "@/features/chat/model"
import {
  getEffectiveReasoning,
  getReasoningToSend,
  getVisibleReasoningLevels,
} from "@/features/chat/model/reasoning-options"
import { useAvailableModels } from "@/features/chat/model/use-available-models"
import { usePanelResize } from "@/features/chat/model/use-panel-resize"
import { Button, PageCard } from "@/shared/ui"

import { ChatThread, type ChatThreadHandle } from "./chat-thread"
import { ChatInput } from "./chat-input"
import { EmptyState } from "./empty-state"
import { DropOverlay } from "./drop-overlay"
import { ConversationPanel } from "./conversation-panel"
import { ChatHeader } from "./chat-header"
import { MobileChatHeader } from "./mobile-chat-header"
import { MobileConversationList } from "./mobile-conversation-list"

/* ── Media query hook ── */

function useMediaQuery(query: string) {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mql = window.matchMedia(query)
      mql.addEventListener("change", onStoreChange)
      return () => mql.removeEventListener("change", onStoreChange)
    },
    [query],
  )
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query])
  const getServerSnapshot = useCallback(() => false, [])
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

/* ── Types ── */

export type ChatModuleProps = {
  /** Pre-selected conversation ID (e.g. from URL routing) */
  initialConversationId?: string
  /** Folder scope for conversations. Defaults to null (all). */
  folderId?: string | null
  /**
   * Called when the active conversation changes.
   * Use this to sync external state (e.g. URL routing).
   */
  onConversationChange?: (id: string | null) => void
  /**
   * Called when the user starts a new chat.
   * Use this for external navigation (e.g. router.push("/chat")).
   */
  onNewChat?: VoidFunction
  /**
   * Called when user selects a conversation from the list.
   * Receives the conversation ID. Use for external navigation.
   */
  onSelectConversation?: (id: string) => void
}

/* ── ChatModule ── */

export function ChatModule({
  initialConversationId,
  folderId = null,
  onConversationChange,
  onNewChat,
  onSelectConversation,
}: ChatModuleProps) {
  const {
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
    conversationId,
    conversations,
    conversationsLoading,
    conversationsError,
    switchConversation,
    startNewChat: rawStartNewChat,
    removeConversation,
    setSelectedModel,
    setSelectedReasoning,
    retryLoadConversations,
    taggedPart,
    setTaggedPart,
    renameConversation,
    switchBranch,
  } = useChat({ folderId, initialConversationId })

  const { models, reasoningLevels, isLoading: modelsLoading, error: modelsError } = useAvailableModels()

  /* ── Notify parent of conversation changes ── */
  const prevConversationIdRef = useRef(conversationId)
  useEffect(() => {
    if (
      conversationId !== prevConversationIdRef.current &&
      !conversationId?.startsWith("__optimistic_")
    ) {
      onConversationChange?.(conversationId)
    }
    prevConversationIdRef.current = conversationId
  }, [conversationId, onConversationChange])

  /* ── Refs ── */
  const messagesRef = useRef(messages)
  useEffect(() => { messagesRef.current = messages }, [messages])

  /* ── Responsive state ── */
  const isDesktop = useMediaQuery("(min-width: 1024px)")
  const isMobile = useMediaQuery("(max-width: 767px)")

  /* ── Local UI state ── */
  const [userSelectedModelId, setUserSelectedModelId] = useState<string | null>(null)
  const [userSelectedReasoning, setUserSelectedReasoning] = useState<string | null>(null)
  const [attachedFiles, setAttachedFiles] = useState<File[]>([])
  const [mobileTab, setMobileTab] = useState<"chat" | "history">("chat")
  const [panelToggle, setPanelToggle] = useState<{ forDesktop: boolean; value: boolean } | null>(null)

  useEffect(() => {
    if (mobileTab !== "chat") {
      clearError()
    }
  }, [mobileTab, clearError])

  const showConversations =
    panelToggle && panelToggle.forDesktop === isDesktop
      ? panelToggle.value
      : isDesktop

  /* ── Derived model ── */
  const selectedModelId = userSelectedModelId ?? (models.length > 0 ? models[0].id : "")
  const visibleReasoningLevels = getVisibleReasoningLevels(reasoningLevels)
  const selectedReasoning = getEffectiveReasoning(visibleReasoningLevels, userSelectedReasoning)
  const reasoningToSend = getReasoningToSend(visibleReasoningLevels, selectedReasoning)
  useEffect(() => {
    if (selectedModelId) setSelectedModel(selectedModelId)
  }, [selectedModelId, setSelectedModel])
  useEffect(() => {
    setSelectedReasoning(reasoningToSend)
  }, [reasoningToSend, setSelectedReasoning])

  /* ── Handlers ── */
  const startNewChat = useCallback(() => {
    rawStartNewChat()
    onNewChat?.()
  }, [rawStartNewChat, onNewChat])

  const handleSelectConversation = useCallback(
    (id: string) => {
      switchConversation(id)
      onSelectConversation?.(id)
      if (isMobile) setMobileTab("chat")
    },
    [switchConversation, onSelectConversation, isMobile],
  )

  const handleMobileNewChat = useCallback(() => {
    startNewChat()
    setMobileTab("chat")
  }, [startNewChat])

  const handleFilesAdded = useCallback((newFiles: File[]) => {
    setAttachedFiles((prev) => [...prev, ...newFiles].slice(0, 5))
  }, [])

  const handleEdit = useCallback(
    (index: number, newContent: string) => {
      const msgs = messagesRef.current
      const originalId = msgs[index].id
      const editedMessage = { ...msgs[index], content: newContent }
      const trimmed = [...msgs.slice(0, index), editedMessage]
      reload(trimmed, originalId)
    },
    [reload],
  )

  const handleRegenerate = useCallback(
    (index: number) => {
      const msgs = messagesRef.current
      const targetMsg = msgs[index]
      if (!targetMsg) return
      // Pass the target message as editedMessageId so reload uses streamRegenerate
      reload(msgs.slice(0, index), targetMsg.id)
    },
    [reload],
  )

  const { isDragging } = useFileDrop()

  const chatThreadRef = useRef<ChatThreadHandle>(null)

  const handleSend = useCallback(() => {
    const files = attachedFiles.length > 0 ? [...attachedFiles] : undefined
    handleSubmit(files) // don't await — message is added synchronously, streaming runs in background
    setAttachedFiles([])
    chatThreadRef.current?.scrollOnSend()
  }, [handleSubmit, attachedFiles])

  const toggleConversations = useCallback(() => {
    setPanelToggle({ forDesktop: isDesktop, value: !showConversations })
  }, [isDesktop, showConversations])

  const collapsePanel = useCallback(() => {
    setPanelToggle({ forDesktop: isDesktop, value: false })
  }, [isDesktop])

  const isEmpty = messages.length === 0 && !isLoading

  /* ── Resizable panel ── */
  const {
    width: panelWidth,
    isResizing,
    handleMouseDown: handleResizeMouseDown,
  } = usePanelResize({
    defaultWidth: isDesktop ? 420 : 320,
    minWidth: 280,
    maxWidth: 480,
  })

  /* ── Conversation panel (shared element) ── */
  const conversationPanel = (
    <ConversationPanel
      conversations={conversations}
      activeId={conversationId}
      onSelect={handleSelectConversation}
      onNewChat={startNewChat}
      onDelete={removeConversation}
      visible={showConversations}
      loading={conversationsLoading}
      error={conversationsError}
      onRetry={retryLoadConversations}
      onCollapse={collapsePanel}
      onRename={renameConversation}
    />
  )

  /* ── Shared error block ── */
  const errorBlock = error && (
    <div className="mx-auto flex w-full max-w-[744px] items-center gap-2 px-4 pb-2">
      <div className="flex flex-1 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 nova-text-label-tiny text-red-600">
        <span>{error}</span>
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
  )

  /* ── Chat content area (shared between mobile & desktop) ── */
  const chatContent = (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      {!isMobile && !showConversations && (
        <div className="absolute top-2.5 left-2.5 z-10">
          <ChatHeader showToggle isOpen={false} onToggle={toggleConversations} />
        </div>
      )}

      {/* Main area — absolute-positioned panels for smooth crossfade */}
      <div className="relative flex min-h-0 flex-1">
        <AnimatePresence>
          {isLoading ? (
            <motion.div
              key="loading"
              className="absolute inset-0 flex items-center justify-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <div className="flex gap-1.5">
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]" style={{ animationDelay: "0ms" }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]" style={{ animationDelay: "150ms" }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ege-muted)]" style={{ animationDelay: "300ms" }} />
              </div>
            </motion.div>
          ) : isEmpty ? (
            /* ── Empty state: EmptyState + ChatInput centered together ── */
            <motion.div
              key="empty"
              className="absolute inset-0 flex flex-col items-center justify-center gap-6 overflow-y-auto px-4 pb-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
            >
              <EmptyState onSuggestionClick={(prompt) => setInput(prompt)} />
              {errorBlock}
              <ChatInput
                input={input}
                onInputChange={setInput}
                onSubmit={handleSend}
                status={status}
                onStop={stop}
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
            </motion.div>
          ) : (
            /* ── Chat state: messages + ChatInput at bottom ── */
            <motion.div
              key="chat"
              className="absolute inset-0 flex flex-col"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
            >
              <ChatThread
                ref={chatThreadRef}
                messages={messages}
                status={status}
                conversationId={conversationId}
                onEdit={handleEdit}
                onRegenerate={handleRegenerate}
                onSetTaggedPart={setTaggedPart}
                onSwitchBranch={switchBranch}
                errorSlot={errorBlock}
                inputWrapperClassName="relative px-4 pb-4"
              >
                <ChatInput
                  input={input}
                  onInputChange={setInput}
                  onSubmit={handleSend}
                  status={status}
                  onStop={stop}
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
              </ChatThread>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {isDragging && <DropOverlay onFilesAdded={handleFilesAdded} />}
      </AnimatePresence>
    </div>
  )

  /* ── Mobile layout ── */
  if (isMobile) {
    return (
      <div className="relative flex h-full flex-1">
        <PageCard className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <MobileChatHeader
            activeTab={mobileTab}
            onTabChange={setMobileTab}
            onNewChat={handleMobileNewChat}
          />
          {mobileTab === "chat" ? (
            chatContent
          ) : (
            <MobileConversationList
              conversations={conversations}
              activeId={conversationId}
              onSelect={handleSelectConversation}
              onDelete={removeConversation}
              loading={conversationsLoading}
              error={conversationsError}
              onRetry={retryLoadConversations}
            />
          )}
        </PageCard>
      </div>
    )
  }

  /* ── Tablet / Desktop layout ── */
  return (
    <div className="relative flex h-full flex-1">
      <PageCard className="relative flex min-w-0 flex-1">
        <AnimatePresence initial={false}>
          {showConversations && (
            <motion.div
              initial={{ width: 0 }}
              animate={{
                width: panelWidth,
                transition: isResizing
                  ? { duration: 0 }
                  : { type: "tween", duration: 0.25, ease: [0.4, 0, 0.2, 1] },
              }}
              exit={{
                width: 0,
                transition: { type: "tween", duration: 0.25, ease: [0.4, 0, 0.2, 1] },
              }}
              className="relative shrink-0 overflow-hidden"
            >
              <motion.div
                initial={{ x: -panelWidth, opacity: 0 }}
                animate={{
                  x: 0,
                  opacity: 1,
                  transition: isResizing
                    ? { duration: 0 }
                    : { type: "tween", duration: 0.25, ease: [0, 0, 0.2, 1] },
                }}
                exit={{
                  x: -panelWidth,
                  opacity: 0,
                  transition: { type: "tween", duration: 0.2, ease: [0.4, 0, 1, 1] },
                }}
                className="flex h-full"
                style={{ width: panelWidth, willChange: "transform, opacity" }}
              >
                {conversationPanel}
              </motion.div>

              <div
                onMouseDown={handleResizeMouseDown}
                className="absolute inset-y-0 right-0 z-20 flex w-1 cursor-col-resize items-center justify-center transition-colors hover:bg-[var(--ege-surface)]"
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize sidebar"
              >
                <div className="h-8 w-0.5 rounded-full bg-transparent group-hover:bg-[var(--ege-muted)]" />
              </div>

              <div className="absolute inset-y-0 right-0 w-px bg-[var(--ege-border)]" />
            </motion.div>
          )}
        </AnimatePresence>

        {chatContent}
      </PageCard>
    </div>
  )
}
