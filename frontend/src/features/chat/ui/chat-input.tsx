"use client"

import { useCallback, useRef, useEffect, JSX } from "react"
import TextareaAutosize from "react-textarea-autosize"
import { AnimatePresence, motion } from "motion/react"

import { cn } from "@/shared/lib"
import type { ChatStatus, ModelOption, TaggedPart } from "@/entities/chat"
import { useVoiceInput } from "@/features/chat/model/use-voice-input"
import { AttachmentIcon, MicIcon, PaperAirplaneIcon } from "@/shared/assets/icons"
import { ACCEPTED_INPUT_TYPES, validateFiles } from "@/features/chat/lib"

import { FilePreview } from "./file-preview"
import { ModelSelector } from "./model-selector"
import { ReasoningSelector } from "./reasoning-selector"
import { QuoteTag } from "./quote-tag"
import { Button } from "@/shared"

/* ─────────────────────────────────────────────────────────────────────────────
   Wide voice waveform — full-width canvas stretching across the input top area
   ───────────────────────────────────────────────────────────────────────────── */

/**
 * WideVoiceWaveform — recording track style.
 *
 * Bars grow left → right as audio is captured, building a visible history.
 * Once the track fills the canvas, it auto-scrolls so the newest bar
 * is always at the right edge — like a voice message recording in
 * WhatsApp/Telegram.
 */
function WideVoiceWaveform({ analyser }: { analyser: AnalyserNode | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>(0)
  const sizeRef = useRef({ cw: 0, ch: 0, dpr: 1 })
  // Accumulated amplitude samples (0–1 each)
  const historyRef = useRef<number[]>([])
  const lastSampleRef = useRef(0)

  // Pre-fill history with minimum-amplitude bars when a new recording starts,
  // so the canvas is never blank — it shows a full track of tiny grey bars.
  useEffect(() => {
    lastSampleRef.current = 0
    const { cw, dpr } = sizeRef.current
    const BAR_W = Math.round(2.5 * (dpr || 1))
    const GAP = Math.round(2 * (dpr || 1))
    const UNIT = BAR_W + GAP
    const nBars = cw > 0 ? Math.floor((cw + GAP) / UNIT) : 80
    historyRef.current = Array.from({ length: nBars }, () => 0.04)
  }, [analyser])

  /* Sync canvas pixel dims to CSS size */
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const sync = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.getBoundingClientRect()
      canvas.width = Math.round(rect.width * dpr)
      canvas.height = Math.round(rect.height * dpr)
      sizeRef.current = { cw: canvas.width, ch: canvas.height, dpr }
    }
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [])

  /* RAF animation loop */
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const freqData = analyser ? new Uint8Array(analyser.frequencyBinCount) : null
    const SAMPLE_INTERVAL = 55 // ms between samples (~18 per second)

    const draw = (time: number) => {
      const { cw, ch, dpr } = sizeRef.current
      if (cw === 0 || ch === 0) { rafRef.current = requestAnimationFrame(draw); return }

      // Sample amplitude at throttled rate
      if (time - lastSampleRef.current >= SAMPLE_INTERVAL) {
        lastSampleRef.current = time
        let amp = 0.04 // minimum amplitude (silence)

        if (analyser && freqData) {
          analyser.getByteFrequencyData(freqData)
          // RMS of frequency data
          let sum = 0
          for (let i = 0; i < freqData.length; i++) sum += freqData[i] * freqData[i]
          amp = Math.max(0.04, Math.sqrt(sum / freqData.length) / 255)
        }

        historyRef.current.push(amp)
      }

      // Draw accumulated bars
      ctx.clearRect(0, 0, cw, ch)

      const history = historyRef.current
      const BAR_W = Math.round(2.5 * dpr)
      const GAP = Math.round(2 * dpr)
      const UNIT = BAR_W + GAP
      const maxVisible = Math.floor((cw + GAP) / UNIT)

      // Determine visible slice (auto-scroll when overflow)
      const startIdx = Math.max(0, history.length - maxVisible)
      const visible = history.slice(startIdx)

      // Right-align: newest bar at right edge
      const totalBarsW = visible.length * UNIT - GAP
      const originX = cw - totalBarsW - Math.round(4 * dpr)
      const waveformColor = getComputedStyle(document.documentElement)
        .getPropertyValue("--ege-muted")
        .trim() || "#5b6472"

      for (let i = 0; i < visible.length; i++) {
        const amp = visible[i]
        const minH = Math.round(2 * dpr)
        const maxH = ch * 0.78
        const barH = Math.max(minH, Math.round(amp * maxH))
        const x = originX + i * UNIT
        const y = Math.round((ch - barH) / 2)
        const r = Math.min(BAR_W / 2, barH / 2)

        ctx.fillStyle = waveformColor
        ctx.beginPath()
        if (ctx.roundRect) {
          ctx.roundRect(x, y, BAR_W, barH, r)
        } else {
          ctx.rect(x, y + r, BAR_W, barH - 2 * r)
          ctx.arc(x + r, y + r, r, Math.PI, 0)
          ctx.arc(x + r, y + barH - r, r, 0, Math.PI)
        }
        ctx.fill()
      }

      rafRef.current = requestAnimationFrame(draw)
    }

    rafRef.current = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(rafRef.current)
      const { cw: w, ch: h } = sizeRef.current
      ctx.clearRect(0, 0, w, h)
    }
  }, [analyser])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="block w-full"
      style={{ height: "52px" }}
    />
  )
}

/* ── Types ── */

type ChatInputProps = {
  input: string
  onInputChange: (value: string) => void
  onSubmit: VoidFunction
  status: ChatStatus
  onStop: VoidFunction
  attachedFiles: File[]
  onFilesChange: (files: File[]) => void
  autoFocus?: boolean
} & ({
  customButton: JSX.Element
  models?: never
  selectedModelId?: never
  onModelChange?: never
  reasoningLevels?: never
  selectedReasoning?: never
  onReasoningChange?: never
  modelsLoading?: never
  modelsError?: never
  taggedPart?: TaggedPart | null
  onRemoveTaggedPart?: VoidFunction
  variant?: "default" | "panel"
} | {
  customButton?: never
  models: ModelOption[]
  selectedModelId: string
  onModelChange: (modelId: string) => void
  reasoningLevels: string[]
  selectedReasoning: string
  onReasoningChange: (reasoning: string) => void
  modelsLoading?: boolean
  modelsError?: string | null
  taggedPart?: TaggedPart | null
  onRemoveTaggedPart?: VoidFunction
  /** "default" = full-width main chat, "panel" = narrow sidebar (compact layout, all features) */
  variant?: "default" | "panel"
})

export function ChatInput({
  input,
  onInputChange,
  onSubmit,
  status,
  onStop,
  attachedFiles,
  onFilesChange,
  autoFocus = true,
  customButton,
  models,
  selectedModelId,
  onModelChange,
  reasoningLevels,
  selectedReasoning,
  onReasoningChange,
  modelsLoading,
  modelsError,
  taggedPart,
  onRemoveTaggedPart,
  variant = "default",
}: ChatInputProps) {
  const isPanel = variant === "panel"
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const inputRef = useRef(input)
  const voiceSessionBaseInputRef = useRef<string | null>(null)
  const isCancellingVoiceRef = useRef(false)
  const wasListeningRef = useRef(false)
  useEffect(() => { inputRef.current = input }, [input])

  // Auto-focus the input on mount
  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus()
  }, [autoFocus])

  // Auto-focus when a tagged part quote is set.
  // Delay accounts for panel open animation when chat was closed
  useEffect(() => {
    if (taggedPart) {
      const timer = setTimeout(() => textareaRef.current?.focus(), 150)
      return () => clearTimeout(timer)
    }
  }, [taggedPart])

  const handleVoiceTranscript = useCallback(
    (text: string) => {
      if (isCancellingVoiceRef.current) return
      const current = inputRef.current
      const separator = current && !current.endsWith(" ") && !current.endsWith("\n") ? " " : ""
      onInputChange(current + separator + text)
    },
    [onInputChange],
  )

  const { state: voiceState, interimText, toggle: toggleVoice, stop: stopVoice, analyserNode } =
    useVoiceInput(handleVoiceTranscript)

  const voiceSupported = voiceState !== "unsupported"
  const isListening = voiceState === "listening"

  // Composite display value: real input + interim speech text
  const displayValue = isListening && interimText
    ? input + (input && !input.endsWith(" ") && !input.endsWith("\n") ? " " : "") + interimText
    : input

  const isLoading = status === "streaming" || status === "submitted"
  const canSend = (input.trim().length > 0 || attachedFiles.length > 0) && !isLoading

  // Capture the pre-dictation value once when listening starts.
  useEffect(() => {
    if (isListening && !wasListeningRef.current) {
      voiceSessionBaseInputRef.current = inputRef.current
    }
    wasListeningRef.current = isListening
  }, [isListening])

  useEffect(() => {
    if (voiceState === "idle") {
      isCancellingVoiceRef.current = false
    }
  }, [voiceState])

  // Stop voice recognition before sending to prevent interim text leaking
  const handleSendAction = useCallback(() => {
    if (isListening) stopVoice()
    onSubmit()
  }, [isListening, stopVoice, onSubmit])

  const handleCancelVoice = useCallback(() => {
    isCancellingVoiceRef.current = true
    stopVoice()
    onInputChange(voiceSessionBaseInputRef.current ?? "")
    voiceSessionBaseInputRef.current = null
  }, [stopVoice, onInputChange])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        if (canSend) handleSendAction()
      }
    },
    [canSend, handleSendAction]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files) return
      const valid = validateFiles(Array.from(files), attachedFiles)
      if (valid.length > 0) {
        onFilesChange([...attachedFiles, ...valid])
      }
      e.target.value = ""
    },
    [attachedFiles, onFilesChange]
  )

  const handleRemoveFile = useCallback(
    (index: number) => {
      onFilesChange(attachedFiles.filter((_, i) => i !== index))
    },
    [attachedFiles, onFilesChange]
  )

  const handleInputContainerMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const target = e.target as HTMLElement
      const interactive = target.closest(
        "button, a, input, textarea, select, [role='button'], [contenteditable='true']",
      )
      if (interactive) return

      e.preventDefault()
      textareaRef.current?.focus({ preventScroll: true })
    },
    [],
  )

  return (
    <div
      className={cn(
        "mx-auto w-full rounded-3xl p-1.5 px-4 md:px-1.5",
        !isPanel && "max-w-[744px] mb-4",
        attachedFiles.length > 0 &&
        "border border-[var(--ege-border)] backdrop-blur-sm",
      )}
      style={{
        boxShadow:
          "0px 8px 16px -4px #0000000A, 0px 4px 8px -2px #00000008, 0px 2px 4px -1px #00000005, 0px 1px 2px 0px #00000003",
        border: "1px solid var(--ege-border)",
      }}
    >
      {/* ── Quote + File attachments — above the input box but inside outer container ── */}
      <AnimatePresence>
        {taggedPart && onRemoveTaggedPart && (
          <motion.div
            key="quote-tag"
            initial={{ opacity: 0, y: 6, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: 6, height: 0 }}
            transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <QuoteTag
              taggedPart={taggedPart}
              onRemove={onRemoveTaggedPart}
              hasAttachedFiles={attachedFiles.length > 0}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <FilePreview files={attachedFiles} onRemove={handleRemoveFile} />

      <div className="mx-auto w-full">
        <div
          className={cn(
            "flex flex-col rounded-[17px] backdrop-blur-xs min-h-38.5",
            (attachedFiles.length > 0 || !!taggedPart) &&
            "border border-[var(--ege-border)]",
          )}
          style={{ padding: "10px 8px 8px 6px" }}
          onMouseDown={handleInputContainerMouseDown}
        >
          {/* ── Top area: textarea OR waveform (fade-swap) ── */}
          <AnimatePresence mode="wait" initial={false}>
            {isListening ? (
              <motion.div
                key="waveform"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="flex flex-1 flex-col justify-start"
              >
                <WideVoiceWaveform analyser={analyserNode} />
              </motion.div>
            ) : (
              <motion.div
                key="textarea"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="flex-1"
              >
                <label
                  htmlFor="chat-input"
                  className="block flex-1 cursor-text"
                >
                  <TextareaAutosize
                    ref={textareaRef}
                    id="chat-input"
                    name="chat-input"
                    value={displayValue}
                    onChange={(e) => {
                      if (!isListening) onInputChange(e.target.value);
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={
                      isListening ? "Слушаю..." : "Спроси Алису AI о чём угодно"
                    }
                    readOnly={isListening}
                    minRows={1}
                    maxRows={8}
                    className={cn(
                      "w-full resize-none bg-transparent pl-3 pr-2 pt-2.5 nova-text-label-medium outline-none backdrop-blur-xs",
                      isListening
                        ? "text-[var(--ege-muted)] placeholder:text-[var(--ege-muted)]"
                        : "text-[var(--ege-text)] placeholder:text-[var(--ege-muted)]",
                    )}
                  />
                </label>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div>
                <Button
                  variant="plain"
                  iconOnly
                  rounded={false}
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  aria-label="Прикрепить файл"
                  className="flex items-center justify-center text-[var(--ege-muted)] hover:text-[var(--ege-text)]"
                >
                  <AttachmentIcon />
                </Button>

                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_INPUT_TYPES}
                  onChange={handleFileSelect}
                  hidden
                />
              </div>

              {customButton !== undefined
                ? customButton
                : (
                  <>
                    <ModelSelector
                      models={models}
                      selectedModelId={selectedModelId}
                      onModelChange={onModelChange}
                      isLoading={modelsLoading}
                      error={modelsError}
                    />
                    <ReasoningSelector
                      reasoningLevels={reasoningLevels}
                      selectedReasoning={selectedReasoning}
                      onReasoningChange={onReasoningChange}
                      isLoading={modelsLoading}
                      error={modelsError}
                    />
                  </>
                )
              }
            </div>

            <div className="flex gap-1.5">
              {isListening ? (
                <>
                  <Button
                    variant="plain"
                    iconOnly
                    type="button"
                    onClick={handleCancelVoice}
                    aria-label="Отменить голосовой ввод"
                    title="Отменить голосовой ввод"
                    className="flex items-center justify-center text-[var(--ege-text)] hover:text-[var(--ege-muted)]"
                  >
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 20 20"
                      fill="none"
                      aria-hidden="true"
                    >
                      <path
                        d="M5 5L15 15M15 5L5 15"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                      />
                    </svg>
                  </Button>
                  <Button
                    iconOnly
                    type="button"
                    onClick={stopVoice}
                    aria-label="Подтвердить голосовой ввод"
                    title="Подтвердить голосовой ввод"
                    className="flex items-center justify-center"
                  >
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 20 20"
                      fill="none"
                      aria-hidden="true"
                    >
                      <path
                        d="M4.5 10.5L8.5 14.5L15.5 5.5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </Button>
                </>
              ) : isLoading ? (
                <>
                  {voiceSupported && (
                    <Button
                      variant="plain"
                      iconOnly
                      type="button"
                      onClick={toggleVoice}
                      className={cn(
                        "relative flex items-center justify-center transition-all duration-200",
                        voiceState === "error"
                          ? "text-[#EF4444]"
                          : "text-[var(--ege-muted)] hover:text-[var(--ege-text)]",
                      )}
                      aria-label="Голосовой ввод"
                      title={
                        voiceState === "error"
                          ? "Микрофон не сработал, нажми ещё раз"
                          : "Голосовой ввод"
                      }
                    >
                      <MicIcon className="h-[18px] w-[18px]" />
                    </Button>
                  )}
                  <Button
                    iconOnly
                    variant="outline"
                    type="button"
                    onClick={onStop}
                    aria-label="Остановить ответ"
                    className="ml-auto flex shrink-0 items-center justify-center"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="18"
                      height="18"
                      viewBox="0 0 18 18"
                      fill="none"
                    >
                      <path
                        fillRule="evenodd"
                        clipRule="evenodd"
                        d="M3.375 5.625C3.375 4.38236 4.38236 3.375 5.625 3.375H12.375C13.6176 3.375 14.625 4.38236 14.625 5.625V12.375C14.625 13.6176 13.6176 14.625 12.375 14.625H5.625C4.38236 14.625 3.375 13.6176 3.375 12.375V5.625Z"
                        fill="var(--ege-muted)"
                      />
                    </svg>
                  </Button>
                </>
              ) : (
                <>
                  {voiceSupported && (
                    <Button
                      variant="plain"
                      iconOnly
                      type="button"
                      onClick={toggleVoice}
                      className={cn(
                        "relative flex items-center justify-center transition-all duration-200",
                        voiceState === "error"
                          ? "text-[#EF4444]"
                          : "text-[var(--ege-muted)] hover:text-[var(--ege-text)]",
                      )}
                      aria-label="Голосовой ввод"
                      title={
                        voiceState === "error"
                          ? "Микрофон не сработал, нажми ещё раз"
                          : "Голосовой ввод"
                      }
                    >
                      <MicIcon className="h-[18px] w-[18px]" />
                    </Button>
                  )}
                  <Button
                    iconOnly
                    type="button"
                    onClick={handleSendAction}
                    disabled={!canSend}
                    aria-label="Отправить сообщение"
                    className="ml-auto flex shrink-0 items-center justify-center rounded-full"
                  >
                    <PaperAirplaneIcon />
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
