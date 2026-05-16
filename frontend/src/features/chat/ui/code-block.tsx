"use client"

import { Button } from "@/shared"
import { useState, useCallback, useRef, type ReactNode } from "react"

type CodeBlockProps = {
  language?: string
  children: ReactNode
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const codeRef = useRef<HTMLPreElement>(null)

  const handleCopy = useCallback(() => {
    const text = codeRef.current?.textContent ?? ""
    navigator.clipboard.writeText(text)
    setCopied(true)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 2000)
  }, [])

  return (
    <div
      className="my-3 overflow-hidden rounded-2xl border border-[var(--ege-border)]"

    >
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-2xl bg-[var(--ege-surface-raised)] py-1.5 pr-2 pl-4">
        <span className="nova-text-code-header text-[var(--ege-muted)]">
          {language || "Code"}
        </span>

        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 text-[var(--ege-muted)]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M11.3106 5.98895C11.309 4.02219 11.2793 3.00346 10.7067 2.30591C10.5962 2.1712 10.4727 2.04769 10.338 1.93714C9.60205 1.33325 8.50875 1.33325 6.32208 1.33325C4.13543 1.33325 3.04211 1.33325 2.30622 1.93714C2.17151 2.04768 2.04798 2.1712 1.93742 2.30591C1.3335 3.04175 1.3335 4.135 1.3335 6.3215C1.3335 8.50802 1.3335 9.60124 1.93742 10.3371C2.04797 10.4718 2.17151 10.5953 2.30622 10.7058C3.00381 11.2784 4.02262 11.3081 5.98951 11.3097" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M9.35369 6.01743L11.3308 5.98901M9.34434 14.6686L11.3215 14.6402M14.6492 9.34915L14.6306 11.3222M6.00839 9.35817L5.98975 11.3313M7.65969 6.01743C7.10451 6.11687 6.21338 6.21914 6.00839 7.36695M12.9979 14.6402C13.5546 14.5492 14.4472 14.4607 14.6698 13.3161M12.9979 6.01743C13.5531 6.11687 14.4442 6.21914 14.6492 7.36695M7.66818 14.6393C7.11295 14.5401 6.22176 14.4383 6.01615 13.2906" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{copied ? "Copied" : "Copy"}</span>
        </Button>
      </div>

      {/* Code area */}
      <pre
        ref={codeRef}
        className="no-scrollbar overflow-x-auto rounded-b-2xl bg-[var(--ege-surface)] p-4 nova-text-code-content text-[var(--ege-text)]"
      >
        {children}
      </pre>
    </div>
  )
}
