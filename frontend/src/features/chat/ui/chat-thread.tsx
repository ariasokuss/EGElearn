"use client";

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { ChatMessage, ChatStatus, TaggedPart } from "@/entities/chat";
import { Button } from "@/shared/ui";

import { ChatMessages } from "./chat-messages";

export type ChatThreadHandle = {
  /** Expand the bottom spacer and scroll to the last user message — call after sending. */
  scrollOnSend: VoidFunction;
  /** Scroll to the very bottom of the thread. */
  scrollToBottom: VoidFunction;
};

type ChatThreadProps = {
  messages: ChatMessage[];
  status: ChatStatus;
  conversationId?: string | null;
  onEdit?: (index: number, newContent: string) => void;
  onRegenerate?: (index: number) => void;
  onSwitchBranch?: (messageId: string, direction: "next" | "prev") => void;
  onSetTaggedPart?: (part: TaggedPart) => void;
  followUpdates?: boolean;
  afterMessages?: ReactNode;
  afterMessagesScrollKey?: string | number;
  afterMessageSlots?: Record<string, ReactNode>;
  /** Rendered between ChatMessages and the input row — e.g. an error block. */
  errorSlot?: ReactNode;
  /** Input area. The floating scroll-to-bottom button is absolutely positioned over this wrapper. */
  children: ReactNode;
  /** className for the wrapper holding the input + scroll-to-bottom button. Must be positioned. */
  inputWrapperClassName?: string;
};

function ChatThreadInner(
  {
    messages,
    status,
    conversationId,
    onEdit,
    onRegenerate,
    onSwitchBranch,
    onSetTaggedPart,
    followUpdates = true,
    afterMessages,
    afterMessagesScrollKey,
    afterMessageSlots,
    errorSlot,
    children,
    inputWrapperClassName = "relative px-4 pb-4",
  }: ChatThreadProps,
  ref: React.Ref<ChatThreadHandle>,
) {
  const [isAtBottom, setIsAtBottom] = useState(true);
  const scrollToBottomRef = useRef<VoidFunction>(() => {});
  const scrollToLatestAssistantStartRef = useRef<VoidFunction>(() => {});
  const scrollToLastUserRef = useRef<VoidFunction>(() => {});
  const prepareForSendRef = useRef<VoidFunction>(() => {});

  const handleScrollStateChange = useCallback(
    (
      atBottom: boolean,
      scrollFn: VoidFunction,
      scrollToAssistantStartFn: VoidFunction,
      scrollToUserFn: VoidFunction,
      prepareFn: VoidFunction,
    ) => {
      setIsAtBottom(atBottom);
      scrollToBottomRef.current = scrollFn;
      scrollToLatestAssistantStartRef.current = scrollToAssistantStartFn;
      scrollToLastUserRef.current = scrollToUserFn;
      prepareForSendRef.current = prepareFn;
    },
    [],
  );

  useImperativeHandle(
    ref,
    () => ({
      scrollOnSend: () => {
        // Delegates to useAutoScroll.prepareForSend: measures the real last
        // user message height and expands the spacer accordingly, then scrolls
        // the user's message to the top. The [...deps,status] effect in
        // useAutoScroll takes over and pulls the assistant response's start
        // into view as soon as the LLM's first chunk renders.
        prepareForSendRef.current();
      },
      scrollToBottom: () => {
        scrollToBottomRef.current();
      },
    }),
    [],
  );

  return (
    <>
      <ChatMessages
        messages={messages}
        status={status}
        conversationId={conversationId}
        onEdit={onEdit}
        onRegenerate={onRegenerate}
        onSwitchBranch={onSwitchBranch}
        onSetTaggedPart={onSetTaggedPart}
        onScrollStateChange={handleScrollStateChange}
        followUpdates={followUpdates}
        afterMessages={afterMessages}
        afterMessagesScrollKey={afterMessagesScrollKey}
        afterMessageSlots={afterMessageSlots}
      />

      {errorSlot}

      <div className={inputWrapperClassName}>
        {!isAtBottom && (
          <Button
            variant="outline"
            type="button"
            onClick={() => scrollToBottomRef.current()}
            className="absolute -top-10 left-1/2 z-10 -translate-x-1/2 text-[var(--ege-muted)]"
          >
            ↓ Down
          </Button>
        )}
        {children}
      </div>
    </>
  );
}

export const ChatThread = forwardRef<ChatThreadHandle, ChatThreadProps>(ChatThreadInner);
