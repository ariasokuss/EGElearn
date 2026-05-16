"use client"

import {
  Component,
  useMemo,
  type ReactNode,
  type HTMLAttributes,
} from "react"
import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { CodeBlock } from "./code-block"

type MarkdownContentProps = {
  content: string
  remarkPlugins?: Parameters<typeof import("react-markdown").default>[0]["remarkPlugins"]
  rehypePlugins?: Parameters<typeof import("react-markdown").default>[0]["rehypePlugins"]
  className?: string
}

type ErrorBoundaryState = {
  hasError: boolean
}

class MarkdownErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

/**
 * Extract language from className like "language-python" -> "Python"
 */
function extractLanguage(className?: string): string | undefined {
  if (!className) return undefined
  const match = className.match(/language-(\w+)/)
  if (!match) return undefined
  const lang = match[1]
  // Capitalize first letter
  return lang.charAt(0).toUpperCase() + lang.slice(1)
}

function useMdComponents(): Components {
  return useMemo<Components>(
    () => ({
      pre({ children }) {
        return <>{children}</>
      },
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      code({ className, children, node, ...rest }: HTMLAttributes<HTMLElement> & { inline?: boolean; node?: unknown }) {
        // Detect block code: has a language class OR contains newlines.
        // The language class is the most reliable signal — it means the
        // markdown parser found a fenced code block (```lang).
        const hasLanguage = className?.startsWith("language-")
        const hasNewline =
          typeof children === "string"
            ? children.includes("\n")
            : Array.isArray(children) &&
              children.some((c) => typeof c === "string" && c.includes("\n"))

        if (hasLanguage || hasNewline) {
          const language = extractLanguage(className)
          return (
            <CodeBlock language={language}>
              <code className={className} {...rest}>
                {children}
              </code>
            </CodeBlock>
          )
        }

        // Inline code — styled via .chat-prose :not(pre) > code
        return (
          <code className={className} {...rest}>
            {children}
          </code>
        )
      },
      table({ children }) {
        return (
          <div className="table-wrap">
            <table>{children}</table>
          </div>
        )
      },
    }),
    [],
  )
}

/**
 * Convert LaTeX-style math delimiters to standard markdown math delimiters
 * so that remark-math can parse them.
 *
 *   \( ... \)  →  $...$    (inline)
 *   \[ ... \]  →  $$...$$  (block)
 *
 * Skips content inside fenced code blocks (``` ... ```) and inline code (` ... `).
 */
function normalizeMathDelimiters(text: string): string {
  // Split on code fences and inline code, only transform non-code segments
  const parts = text.split(/(```[\s\S]*?```|`[^`]+`)/g)

  return parts
    .map((part, i) => {
      // Odd indices are code matches — leave them untouched
      if (i % 2 === 1) return part

      // Block math: \[ ... \]
      let result = part.replace(
        /\\\[([\s\S]*?)\\\]/g,
        (_match, inner: string) => `$$${inner}$$`,
      )
      // Inline math: \( ... \)
      result = result.replace(
        /\\\((.*?)\\\)/g,
        (_match, inner: string) => `$${inner}$`,
      )
      return result
    })
    .join("")
}

export function MarkdownContent({
  content,
  remarkPlugins,
  rehypePlugins,
  className,
}: MarkdownContentProps) {
  const components = useMdComponents()
  const processed = useMemo(() => normalizeMathDelimiters(content), [content])

  return (
    <MarkdownErrorBoundary
      fallback={
        <p className="whitespace-pre-wrap [word-break:break-word]">{content}</p>
      }
    >
        <div className={className}>
          <ReactMarkdown
            remarkPlugins={remarkPlugins}
            rehypePlugins={rehypePlugins}
            components={components}
          >
            {processed}
          </ReactMarkdown>
        </div>
    </MarkdownErrorBoundary>
  )
}
