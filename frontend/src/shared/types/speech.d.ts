interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionResultList {
  readonly length: number
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionAlternative {
  readonly confidence: number
  readonly transcript: string
}

declare class webkitSpeechRecognition {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onend: (VoidFunction) | null
  onerror: ((event: Event) => void) | null
  start(): void
  stop(): void
  abort(): void
}

interface Window {
  SpeechRecognition: typeof webkitSpeechRecognition
  webkitSpeechRecognition: typeof webkitSpeechRecognition
}
