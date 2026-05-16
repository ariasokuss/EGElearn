"use client"

import { useState, useRef, useEffect, useCallback } from "react"

/* ── Types ── */

export type VoiceState = "idle" | "listening" | "processing" | "error" | "unsupported"

export type VoiceError =
  | "not-allowed"
  | "no-speech"
  | "aborted"
  | "network"
  | "unsupported"
  | "unknown"

/* eslint-disable @typescript-eslint/no-explicit-any */
type SpeechRecognitionInstance = any

export type UseVoiceInputReturn = {
  /** Current state of the voice input */
  state: VoiceState
  /** Interim (live) transcription while user speaks */
  interimText: string
  /** Last error type, if any */
  error: VoiceError | null
  /** Toggle listening on/off */
  toggle: VoidFunction
  /** Force stop */
  stop: VoidFunction
  /** Web Audio analyser node for waveform visualisation — null when not listening */
  analyserNode: AnalyserNode | null
}

/* ── Error mapping ── */

function mapSpeechError(error: string): VoiceError {
  switch (error) {
    case "not-allowed":
      return "not-allowed"
    case "no-speech":
      return "no-speech"
    case "aborted":
      return "aborted"
    case "network":
      return "network"
    default:
      return "unknown"
  }
}

/* ── Hook ── */

/**
 * useVoiceInput — production-ready speech-to-text hook.
 *
 * State machine: idle → listening → processing → idle
 *                              ↘ error → idle (auto-clear after 3s)
 *
 * @param onFinalTranscript  Called with finalized text (appended to input by caller)
 */
export function useVoiceInput(
  onFinalTranscript: (text: string) => void,
): UseVoiceInputReturn {
  const [state, setState] = useState<VoiceState>("unsupported")

  // Check browser support after mount to avoid SSR/client hydration mismatch
  useEffect(() => {
    if ("SpeechRecognition" in window || "webkitSpeechRecognition" in window) {
      queueMicrotask(() => {
        setState("idle")
      })
    }
  }, [])

  const [interimText, setInterimText] = useState("")
  const [error, setError] = useState<VoiceError | null>(null)
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null)

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const onFinalRef = useRef(onFinalTranscript)
  const errorTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  // Keep callback ref fresh (avoids stale closure in recognition events)
  useEffect(() => {
    onFinalRef.current = onFinalTranscript
  }, [onFinalTranscript])

  /* ── Audio cleanup ── */
  const cleanupAudio = useCallback(() => {
    const stream = streamRef.current
    const ctx = audioCtxRef.current
    streamRef.current = null
    audioCtxRef.current = null
    setAnalyserNode(null)
    stream?.getTracks().forEach((t) => t.stop())
    if (ctx && ctx.state !== "closed") ctx.close().catch(() => {})
  }, [])

  // Full cleanup on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      clearTimeout(errorTimerRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      if (audioCtxRef.current?.state !== "closed") audioCtxRef.current?.close().catch(() => {})
    }
  }, [])

  const startListening = useCallback(() => {
    if (state !== "idle" && state !== "error") return

    const SpeechRecognition =
      window.SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setState("unsupported")
      return
    }

    // Prevent duplicate sessions
    recognitionRef.current?.abort()

    const recognition = new SpeechRecognition() as any
    recognition.lang = navigator.language || "en-US"
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      setState("listening")
      setError(null)
      setInterimText("")
    }

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalChunk = ""
      let interimChunk = ""

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          finalChunk += result[0].transcript
        } else {
          interimChunk += result[0].transcript
        }
      }

      if (finalChunk) {
        // Commit finalized text to input via callback
        onFinalRef.current(finalChunk)
        setInterimText("")
      } else {
        setInterimText(interimChunk)
      }
    }

    recognition.onend = () => {
      cleanupAudio()
      // Brief "processing" state for visual feedback
      setState("processing")
      setInterimText("")
      recognitionRef.current = null
      setTimeout(() => setState("idle"), 300)
    }

    recognition.onerror = (event: { error: string }) => {
      const mapped = mapSpeechError(event.error)
      cleanupAudio()
      recognitionRef.current = null
      setInterimText("")

      // "aborted" and "no-speech" are normal — just go back to idle
      if (mapped === "aborted" || mapped === "no-speech") {
        setState("idle")
        return
      }

      setState("error")
      setError(mapped)

      // Auto-clear error after 3s
      clearTimeout(errorTimerRef.current)
      errorTimerRef.current = setTimeout(() => {
        setState("idle")
        setError(null)
      }, 3000)
    }

    recognitionRef.current = recognition

    try {
      recognition.start()
    } catch {
      setState("error")
      setError("unknown")
      return
    }

    // Set up Web Audio analyser for waveform visualisation (non-blocking)
    if (navigator.mediaDevices?.getUserMedia) {
      navigator.mediaDevices
        .getUserMedia({ audio: true, video: false })
        .then((stream) => {
          // Guard: recognition may have ended by the time this resolves
          if (!recognitionRef.current) {
            stream.getTracks().forEach((t) => t.stop())
            return
          }
          const AudioCtx =
            window.AudioContext || (window as any).webkitAudioContext
          if (!AudioCtx) {
            stream.getTracks().forEach((t) => t.stop())
            return
          }
          const ctx = new AudioCtx() as AudioContext
          const analyser = ctx.createAnalyser()
          analyser.fftSize = 64
          analyser.smoothingTimeConstant = 0.8
          ctx.createMediaStreamSource(stream).connect(analyser)
          streamRef.current = stream
          audioCtxRef.current = ctx
          setAnalyserNode(analyser)
        })
        .catch(() => {
          // Visualisation unavailable — voice input still works normally
        })
    }
  }, [state, cleanupAudio])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    cleanupAudio()
  }, [cleanupAudio])

  const toggle = useCallback(() => {
    if (state === "listening") {
      stop()
    } else {
      startListening()
    }
  }, [state, stop, startListening])

  return { state, interimText, error, toggle, stop, analyserNode }
}
