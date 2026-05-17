"use client"

import Image from "next/image"
import { memo, useState, useCallback, useRef, useEffect } from "react"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeHighlight from "rehype-highlight"
import rehypeKatex from "rehype-katex"
import "katex/dist/katex.min.css"

import { cn } from "@/shared/lib"
import type { ChatMessage, ChatStatus } from "@/entities/chat"
import { CopyIcon, EditIcon, RedoIcon } from "@/shared/assets/icons"

import { MarkdownContent } from "./markdown-content"
import { ImageLightbox } from "./image-lightbox"
import { QuoteBlock } from "./quote-tag"
import { BranchNavigator } from "./branch-navigator"
import { Button } from "@/shared"

const REMARK_PLUGINS = [remarkGfm, remarkMath]
const REHYPE_PLUGINS = [rehypeHighlight, rehypeKatex]

type ActionButtonProps = {
  onClick: VoidFunction;
  label: string;
  children: React.ReactNode;
};

function ActionButton({ onClick, label, children }: ActionButtonProps) {
  return (
    <Button
      variant="plain"
      iconOnly
      rounded={false}
      size="sm"
      type="button"
      onClick={onClick}
      className="flex items-center justify-center text-[var(--ege-muted)] hover:text-[var(--ege-text)]"
      aria-label={label}
      title={label}
    >
      {children}
    </Button>
  );
}

const CHAT_TEXT_CLASS =
  "nova-text-chat-message text-[var(--ege-text)]"

type MessageBubbleProps = {
  message: ChatMessage
  index: number
  isLast: boolean
  status: ChatStatus
  onEdit?: (index: number, newContent: string) => void
  onRegenerate?: (index: number) => void
  onSwitchBranch?: (messageId: string, direction: "next" | "prev") => void
}

export const MessageBubble = memo(
  function MessageBubble({
    message,
    index,
    isLast,
    status,
    onEdit,
    onRegenerate,
    onSwitchBranch,
  }: MessageBubbleProps) {
    const isUser = message.role === "user"
    const isStreaming = isLast && status === "streaming" && !isUser
    const isBusy = isLast && (status === "streaming" || status === "submitted")
    const hasAttachments = !!message.attachments?.length
    const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
    // Citations: prefer the official API field, fallback to metadata.tagged_part (legacy)
    const citationText =
      message.citations?.[0] ??
      (message.metadata?.tagged_part as { text?: string } | undefined)?.text

    const [isEditing, setIsEditing] = useState(false)
    const [editContent, setEditContent] = useState("")
    const textareaInitRef = useRef(false)

    const handleStartEdit = useCallback(() => {
      setEditContent(message.content)
      setIsEditing(true)
    }, [message.content])

    const handleCancelEdit = useCallback(() => {
      textareaInitRef.current = false
      setIsEditing(false)
      setEditContent("")
    }, [])

    const handleSaveEdit = useCallback(() => {
      const trimmed = editContent.trim()
      if (!trimmed || !onEdit) return
      textareaInitRef.current = false
      onEdit(index, trimmed)
      setIsEditing(false)
      setEditContent("")
    }, [editContent, index, onEdit])

    const handleEditKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault()
          handleSaveEdit()
        } else if (e.key === "Escape") {
          handleCancelEdit()
        }
      },
      [handleSaveEdit, handleCancelEdit]
    )

    const [showCopyCheck, setShowCopyCheck] = useState(false)
    const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
    useEffect(() => () => clearTimeout(copyTimerRef.current), [])
    const handleCopy = useCallback(() => {
      navigator.clipboard.writeText(message.content)
      setShowCopyCheck(true)
      clearTimeout(copyTimerRef.current)
      copyTimerRef.current = setTimeout(() => setShowCopyCheck(false), 2000)
    }, [message.content])

    return (
      <div
        data-message-id={message.id}
        data-message-role={message.role}
        className={cn(
          "group flex w-full",
          isUser ? "justify-end" : "justify-start",
        )}
      >
        <div className={cn("relative", isUser ? (isEditing ? "w-full" : cn("max-w-[85%] md:max-w-[75%] flex flex-col items-end", citationText && "min-w-[min(100%,260px)]")) : "w-full max-w-[95%]")}>
          {/* Quoted fragment — rendered ABOVE the message bubble. */}
          {citationText && (
            <div className="self-stretch overflow-hidden">
              <QuoteBlock text={citationText} />
            </div>
          )}

          {/* Image attachments — outside the message bubble */}
          {message.images && message.images.length > 0 && (
            <div className={cn(
              "mb-2 grid gap-2",
              message.images.length === 1 ? "grid-cols-1" : "grid-cols-2",
            )}>
              {message.images.map((src, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setLightboxSrc(src)}
                  className="overflow-hidden rounded-2xl outline-none"
                >
                  <Image
                    src={src}
                    alt={`Attachment ${i + 1}`}
                    width={800}
                    height={600}
                    className={cn(
                      "w-full cursor-pointer object-cover transition-opacity hover:opacity-90",
                      message.images!.length === 1 ? "max-h-80 rounded-2xl" : "aspect-square",
                    )}
                    loading="lazy"
                    unoptimized
                  />
                </button>
              ))}
            </div>
          )}

          {/* File attachments — outside the message bubble */}
          {hasAttachments && (
            <div className="mb-2 flex flex-col gap-2">
              {message.attachments!.map((file) => {
                const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
                const isPdf = file.type === "application/pdf" || ext === "pdf"

                const iconBg = "bg-[var(--ege-surface)]"

                const label = isPdf ? "PDF" : ext.length <= 4 ? ext.toUpperCase() : "File"

                return (
                  <a
                    key={file.name}
                    href={file.url || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex max-w-xs items-center gap-3 rounded-2xl border border-[var(--ege-border)] bg-[var(--ege-surface-raised)] p-2 transition-colors hover:bg-[var(--ege-surface)]"
                    style={{ pointerEvents: file.url ? "auto" : "none" }}
                  >
                    <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl nova-text-label-xxs uppercase text-[var(--ege-muted)]", iconBg)}>
                      {label}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate nova-text-label-small text-[var(--ege-text)]">{file.name}</p>
                      <p className="nova-text-label-tiny text-[var(--ege-muted)]">{label}</p>
                    </div>
                  </a>
                )
              })}
            </div>
          )}

          <div
            className={cn(
              "relative",
              isUser
                ? "rounded-2xl p-3.5 bg-[var(--ege-surface)] border border-[var(--ege-border)]"
                : undefined,
            )}
            style={
              isUser ? { boxShadow: "0px 2px 4px -2px #00000005" } : undefined
            }
          >
            {isUser ? (
              <div className={cn("relative", isEditing && "min-h-30")}>
                <p
                  className={cn(
                    CHAT_TEXT_CLASS,
                    "whitespace-pre-wrap [word-break:break-word]",
                    isEditing && "invisible",
                  )}
                  aria-hidden={isEditing}
                >
                  {isEditing ? editContent || "\u00A0" : message.content}
                </p>

                {isEditing && (
                  <textarea
                    id="edit-message"
                    name="edit-message"
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    onKeyDown={handleEditKeyDown}
                    ref={(el) => {
                      if (el && !textareaInitRef.current) {
                        textareaInitRef.current = true;
                        el.focus({ preventScroll: true });
                        el.selectionStart = el.value.length;
                        el.selectionEnd = el.value.length;
                      }
                    }}
                    className={cn(
                      CHAT_TEXT_CLASS,
                      "absolute inset-0 w-full resize-none whitespace-pre-wrap [word-break:break-word] bg-transparent outline-none",
                    )}
                  />
                )}
              </div>
            ) : (
              <div className={cn(CHAT_TEXT_CLASS, "chat-prose max-w-none")}>
                <MarkdownContent
                  content={message.content}
                  remarkPlugins={REMARK_PLUGINS}
                  rehypePlugins={REHYPE_PLUGINS}
                />
              </div>
            )}

          </div>

          {isEditing && (
            <div className="absolute -bottom-9 right-0 flex gap-2">
              <Button
                variant="plain"
                rounded={false}
                type="button"
                onClick={handleCancelEdit}
                className="text-[var(--ege-muted)] hover:text-[var(--ege-text)]"
              >
                Отмена
              </Button>
              <Button //No button variant
                rounded={false}
                type="button"
                onClick={handleSaveEdit}
                disabled={!editContent.trim()}
                className="bg-[var(--ege-accent)] text-white hover:bg-[var(--ege-accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Готово
              </Button>
            </div>
          )}

          {/* Action row: absolute so it never shifts content */}
          {!isEditing && !isStreaming && !isBusy && (
            <div
              className={cn(
                "absolute top-full mt-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100",
                isUser ? "right-0" : "left-0",
              )}
            >
              {isUser ? (
                <>
                  {message.siblingCount > 1 && onSwitchBranch && (
                    <BranchNavigator
                      versionIndex={message.versionIndex}
                      siblingCount={message.siblingCount}
                      onPrev={() => onSwitchBranch(message.id, "prev")}
                      onNext={() => onSwitchBranch(message.id, "next")}
                    />
                  )}
                  {onEdit && (
                    <ActionButton onClick={handleStartEdit} label="Редактировать">
                      <EditIcon />
                    </ActionButton>
                  )}
                  <ActionButton onClick={handleCopy} label="Скопировать">
                    {showCopyCheck ? (
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M2 6.5l3 3 5-6.5" />
                      </svg>
                    ) : (
                      <CopyIcon />
                    )}
                  </ActionButton>
                </>
              ) : (
                <>
                  {onRegenerate && !message.metadata?.practice_hint && (
                    <ActionButton onClick={() => onRegenerate(index)} label="Ответить заново">
                      <RedoIcon />
                    </ActionButton>
                  )}
                  <ActionButton onClick={handleCopy} label="Скопировать">
                    {showCopyCheck ? (
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M2 6.5l3 3 5-6.5" />
                      </svg>
                    ) : (
                      <CopyIcon />
                    )}
                  </ActionButton>
                  {message.siblingCount > 1 && onSwitchBranch && (
                    <BranchNavigator
                      versionIndex={message.versionIndex}
                      siblingCount={message.siblingCount}
                      onPrev={() => onSwitchBranch(message.id, "prev")}
                      onNext={() => onSwitchBranch(message.id, "next")}
                    />
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {lightboxSrc && (
          <ImageLightbox
            src={lightboxSrc}
            onClose={() => setLightboxSrc(null)}
          />
        )}
      </div>
    );
  },
  (prev, next) =>
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.images === next.message.images &&
    prev.message.citations === next.message.citations &&
    prev.message.siblingCount === next.message.siblingCount &&
    prev.message.versionIndex === next.message.versionIndex &&
    prev.isLast === next.isLast &&
    prev.status === next.status &&
    prev.index === next.index
)
