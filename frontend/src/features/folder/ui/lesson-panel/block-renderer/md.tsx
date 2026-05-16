import {
  memo,
  useMemo,
  type ComponentProps,
  type ReactNode,
} from "react";
import type { Components } from "react-markdown";
import Image from "next/image";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import "./katex-setup";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { cn } from "@/shared/lib";

import { LessonCard } from "@/shared/ui/lesson-card";

import { normalizeLessonMathDelimiters } from "./math-delimiters";

const TEST_MARKDOWN_IMAGE_CLASS =
  "block h-auto w-auto max-w-full max-h-[min(22rem,65vh)] object-contain";

type FenceSegment =
  | { type: "md"; body: string }
  | { type: "fenced"; lang: string; body: string };

/**
 * (Source: https://x) and (Source adapted from: https://x) -> markdown where only "Source" is a link, URL is not shown in text.
 * Tolerates spaces before the closing paren, optional <...> around the URL, fullwidth parentheses.
 */
function applySourceCitationMarkdown(source: string): string {
  const s = source
    .replace(/\r\n/g, "\n")
    .replace(/[\uFF08]/g, "(")
    .replace(/[\uFF09]/g, ")");
  return s
    .replace(
      /\(Source adapted from:\s*<?(https?:\/\/\S+?)>?\s*\)/gi,
      "([Source]($1) adapted from:)",
    )
    .replace(/\(Source:\s*<?(https?:\/\/\S+?)>?\s*\)/gi, "([Source]($1):)");
}

/** Splits on ```-fenced blocks; preserves order of prose vs. diagram/extract. */
function splitMarkdownByFences(input: string): FenceSegment[] {
  const s = input.replace(/\r\n/g, "\n");
  const re = /```([a-zA-Z-]*)\s*\n([\s\S]*?)```/g;
  const out: FenceSegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) {
      const body = s.slice(last, m.index);
      if (body.trim()) out.push({ type: "md", body });
    }
    out.push({ type: "fenced", lang: (m[1] || "").trim().toLowerCase(), body: m[2] ?? "" });
    last = m.index + m[0].length;
  }
  if (last < s.length) {
    const rest = s.slice(last);
    if (rest.trim()) out.push({ type: "md", body: rest });
  }
  if (out.length === 0 && s.trim()) {
    out.push({ type: "md", body: s });
  }
  return out;
}

const TEST_CONTEXT_DIRECTIVE_LINE = /^\s*:::\s*(text|figure)(?:\s+\[([^\]]*)\])?\s*$/;
const TEST_CONTEXT_NEW_DIRECTIVE = /^\s*:::\s*(text|figure)\b/;

function isGfmTableSeparatorLine(line: string): boolean {
  const t = line.trim();
  if (t.length === 0 || !t.includes("|") || !/[-]{1,}/.test(t)) {
    return false;
  }
  if (t.replace(/[|\s:\-]+/g, "") !== "") {
    return false;
  }
  return true;
}

function stripTrailingStandaloneTripleColonLines(input: string): string {
  const lines = input.replace(/\r\n/g, "\n").split("\n");
  while (lines.length > 0 && /^\s*:::\s*$/.test(lines[lines.length - 1] ?? "")) {
    lines.pop();
  }
  return lines.join("\n").trimEnd();
}

type TestContextTopSegment =
  | { kind: "legacy"; content: string }
  | { kind: "text"; label: string | null; body: string }
  | { kind: "figure"; label: string | null; body: string };

function sourceHasTestContextDirectives(s: string): boolean {
  return /^\s*:::\s*(text|figure)\b/m.test(s.replace(/\r\n/g, "\n"));
}

function parseTestContextDirectives(s: string): TestContextTopSegment[] {
  const text = stripTrailingStandaloneTripleColonLines(s.replace(/\r\n/g, "\n"),);
  const lines = text.split("\n");
  const out: TestContextTopSegment[] = [];
  const legacyBuf: string[] = [];

  let inFence = false;
  let i = 0;

  const flushLegacy = () => {
    const joined = stripTrailingStandaloneTripleColonLines(
      legacyBuf.join("\n").trim(),
    );
    legacyBuf.length = 0;
    if (joined) {
      out.push({ kind: "legacy", content: joined });
    }
  };

  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      legacyBuf.push(line);
      i += 1;
      continue;
    }
    if (inFence) {
      legacyBuf.push(line);
      i += 1;
      continue;
    }
    const m = line.match(TEST_CONTEXT_DIRECTIVE_LINE);
    if (m) {
      flushLegacy();
      const dir = m[1] as "text" | "figure";
      const label =
        m[2] === undefined ? null : m[2].trim() || null;
      i += 1;
      const bodyBuf: string[] = [];
      let bodyInFence = false;
      while (i < lines.length) {
        const bl = lines[i] ?? "";
        if (/^\s*```/.test(bl)) {
          bodyInFence = !bodyInFence;
          bodyBuf.push(bl);
          i += 1;
          continue;
        }
        if (!bodyInFence && TEST_CONTEXT_NEW_DIRECTIVE.test(bl)) {
          break;
        }
        bodyBuf.push(bl);
        i += 1;
      }
      const body = stripTrailingStandaloneTripleColonLines(
        bodyBuf.join("\n").trim(),
      );
      if (dir === "text") {
        out.push({ kind: "text", label, body });
      } else {
        out.push({ kind: "figure", label, body });
      }
    } else {
      legacyBuf.push(line);
      i += 1;
    }
  }
  flushLegacy();
  return out;
}

const TEST_CONTEXT_EXTRACT_LABEL_CLASS = "font-(family-name:--font-inter) text-[14px] font-semibold text-[#242529] leading-[22px]";

/** Context column: use card shell for prose-only; skip card when an image/figure renders (avoids “plate” under photos). */
function contextSegmentHasFigure(markdown: string): boolean {
  const s = markdown.replace(/\r\n/g, "\n");
  if (/!\[[^\]]*\]\([^)\s]+\)/.test(s)) return true;
  if (/!\[[^\]]*\]\s*\[[^\]]+\]/.test(s)) return true;
  if (/<img[\s/>]/i.test(s)) return true;
  if (/<figure[\s>]/i.test(s)) return true;

  if (/(?:^|\n)\s*[\w.-]+\.(?:png|jpe?g|gif|webp|svg)\s*(?:\n|$)/i.test(s)) {
    return true;
  }
  return false;
}

function contextSegmentHasMarkdownTable(markdown: string): boolean {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    const row = (lines[i] ?? "").trim();
    const sep = (lines[i + 1] ?? "").trim();
    if (!row.includes("|")) continue;
    if (isGfmTableSeparatorLine(sep)) {
      return true;
    }
  }
  return false;
}

function contextSegmentUseContextRail(markdown: string): boolean {
  return (
    contextSegmentHasFigure(markdown) || contextSegmentHasMarkdownTable(markdown)
  );
}

export type MdVariant = "default" | "boldQuestion" | "testContext" | "testQuestion";

type MdInternalVariant = MdVariant | "testContextExtractBody";

function TestContextFigureBlock({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        "my-3 min-w-0",
        "text-[#242529] [&_p]:mb-2 [&_p:last-child]:mb-0",
      )}
    >
      {children}
    </div>
  );
}

function ExtractPanelShell({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        "my-3 min-w-0 p-px backdrop-blur-[2px]",
        "rounded-[17px] border border-[rgba(228,228,231,0.42)]",
        "text-[#242529] [&_p]:mb-2 [&_p:last-child]:mb-0",
      )}
    >
      <div
        className={cn(
          "relative min-w-0 overflow-hidden rounded-2xl bg-white",
          "shadow-[0_2px_4px_-2px_rgba(0,0,0,0.02),0_4px_6px_-1px_rgba(0,0,0,0.04)]",
        )}
      >
        <div className="flex min-w-0 items-stretch gap-3 p-3.5">
          <div
            className="pointer-events-none w-1 shrink-0 rounded-full bg-[#E7DFDA]"
            aria-hidden
          />
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

type MdProps = {
  children: string;
  inline?: boolean;
  oneLine?: boolean;
  variant?: MdVariant;
};

const REMARK_PLUGINS = [remarkGfm, remarkBreaks, remarkMath];
const REHYPE_PLUGINS = [rehypeKatex];

/** Inter Semi Bold 18px / 26px, #242529 — Figma stem (classes inlined so Tailwind always picks them up from this module). */
const BOLD_QUESTION_TEXT =
  "font-(family-name:--font-inter) text-[18px] font-semibold leading-[26px] text-[#242529] tracking-normal not-italic";

/** Diagram from ```diagram``` — no card/substrate (past papers & timed tests). */
function PlainTestDiagramBlock({
  body,
  contextColumn = false,
}: {
  body: string;
  /** Softer corners in question column; flat in Context so it does not read as a “tile”. */
  contextColumn?: boolean;
}) {
  const raw = body.trim();
  const lines = raw.split("\n");
  const lastLine = lines[lines.length - 1];
  const hasImage = lastLine?.startsWith("http");
  const description = hasImage ? lines.slice(0, -1).join("\n") : raw;
  const imageUrl = hasImage ? lastLine : null;
  const captionClass =
    "whitespace-pre-line font-(family-name:--font-inter) text-[14px] font-normal leading-[22px] text-[rgba(36,37,41,0.68)]";

  return (
    <div className={cn("min-w-0", contextColumn ? "my-2" : "my-4")}>
      {description.trim() ? (
        <p className={cn("mb-3", captionClass)}>{description}</p>
      ) : null}
      {imageUrl ? (
        <div className="flex min-w-0 w-full max-w-full justify-start">
          <Image
            src={imageUrl}
            alt={description.trim() || "Diagram"}
            width={800}
            height={500}
            className={cn(
              "h-auto w-auto max-w-full max-h-[min(22rem,65vh)] object-contain",
              contextColumn ? "rounded-none" : "rounded-lg",
            )}
            unoptimized
          />
        </div>
      ) : null}
    </div>
  );
}

function createMarkdownComponents(textStyle: MdInternalVariant) {
  const isBold = textStyle === "boldQuestion";
  const isTestQuestion = textStyle === "testQuestion";
  const isQuestionStem = isBold || isTestQuestion;
  const isTestContext = textStyle === "testContext";
  const isExtractBody = textStyle === "testContextExtractBody";

  const testContextBodyClass =
    "font-(family-name:--font-inter) font-normal text-[14px] leading-[22px] text-[rgba(36,37,41,0.68)]";

  const textClass = isQuestionStem
    ? BOLD_QUESTION_TEXT
    : isTestContext
      ? testContextBodyClass
      : isExtractBody
        ? "font-(family-name:--font-inter) font-normal text-[14px] leading-[22px] text-[rgba(36,37,41,0.68)]"
        : "nova-text-p-base";

  const strongClass =
    isQuestionStem
      ? cn(textClass, "font-semibold leading-[26px]")
      : isTestContext
        ? "font-(family-name:--font-inter) text-[14px] font-semibold leading-[22px] text-[#242529]"
        : isExtractBody
          ? "font-(family-name:--font-inter) text-[14px] font-semibold text-[#242529] leading-[22px]"
          : cn("nova-text-p-base", "font-semibold leading-6");

  const h1Class =
    isTestContext
      ? "mb-3 mt-6 first:mt-0 font-semibold nova-text-h-small text-[#242529]"
      : isExtractBody
        ? "mb-3 mt-6 first:mt-0 font-semibold nova-text-h-small text-[#242529]"
        : "mb-3 mt-6 nova-text-h-small text-[#242529] first:mt-0";
  const h2Class = isTestContext
    ? "mb-2 mt-5 first:mt-0 font-semibold nova-text-h-tiny text-[#242529]"
    : isExtractBody
      ? "mb-2 mt-5 first:mt-0 font-semibold nova-text-h-xss text-[#242529]"
      : "mb-2 mt-5 nova-text-h-tiny text-[#242529] first:mt-0";
  const h3Class = isTestContext
    ? "mb-2 mt-4 first:mt-0 font-semibold nova-text-h-tiny text-[#242529]"
    : isExtractBody
      ? "mb-2 mt-4 first:mt-0 font-semibold nova-text-label-base text-[#242529]"
      : "mb-2 mt-4 nova-text-h-tiny text-[#242529] first:mt-0";

  const components: NonNullable<ComponentProps<typeof ReactMarkdown>["components"]> =
    {
      p: ({ children: c }) => (
        <p className={cn("mb-2 last:mb-0", textClass)}>{c}</p>
      ),
      h1: ({ children: c }) => <h1 className={h1Class}>{c}</h1>,
      h2: ({ children: c }) => <h2 className={h2Class}>{c}</h2>,
      h3: ({ children: c }) => <h3 className={h3Class}>{c}</h3>,
      strong: ({ children: c }) => (
        <strong className={strongClass}>{c}</strong>
      ),
      em: ({ children: c }) => <em className="italic">{c}</em>,
      ul: ({ children: c }) => (
        <ul
          className={cn(
            "mb-2 ml-4 list-disc space-y-0.5 last:mb-0",
            textClass,
          )}
        >
          {c}
        </ul>
      ),
      ol: ({ children: c }) => (
        <ol
          className={cn(
            "mb-2 ml-4 list-decimal space-y-0.5 last:mb-0",
            textClass,
          )}
        >
          {c}
        </ol>
      ),
      li: ({ children: c }) => <li className="text-inherit">{c}</li>,
      ...(isQuestionStem || isTestContext || isExtractBody
        ? {
            figure: ({ children: c }) => (
              <figure className="my-4 min-w-0">{c}</figure>
            ),
            figcaption: ({ children: c }) => (
              <figcaption className="mt-2 font-(family-name:--font-inter) text-[14px] font-normal leading-[22px] text-[rgba(36,37,41,0.68)]">
                {c}
              </figcaption>
            ),
          }
        : {}),
      ...(isExtractBody
        ? {
            blockquote: ({ children: c }) => (
              <div className="my-1 not-italic [&>p]:mb-2 [&>p:last-child]:mb-0">
                {c}
              </div>
            ),
          }
        : {}),
      a: ({ href, children, className, ...rest }) => {
        if (isTestContext || isExtractBody) {
          return (
            <a
              href={href}
              className={cn(
                "font-(family-name:--font-inter) text-[14px] font-medium text-[#2563EB] underline decoration-[#2563EB] underline-offset-2 outline-none transition-opacity hover:opacity-80",
                className,
              )}
              rel="noopener noreferrer"
              target={href?.startsWith("http") ? "_blank" : undefined}
              {...rest}
            >
              {children}
            </a>
          );
        }
        return (
          <a
            href={href}
            className={cn(
              "text-[#2563EB] underline underline-offset-2 outline-none",
              className,
            )}
            {...rest}
          >
            {children}
          </a>
        );
      },
      table: ({ children: c }) =>
        isTestContext || isExtractBody ? (
          <div className="my-3 min-w-0 overflow-x-auto">
            <table className="w-full border-collapse nova-text-label-small">
              {c}
            </table>
          </div>
        ) : (
          <div className="my-3 overflow-x-auto rounded-xl border border-[#E4E4E77A] p-1.5 backdrop-blur-[4px]">
            <table className="w-full border-collapse nova-text-label-small">
              {c}
            </table>
          </div>
        ),
      th: ({ children: c }) => (
        <th className="border-b border-r border-[#F4F4F5] px-4 py-2 text-left font-medium text-[#71717A] last:border-r-0">
          {c}
        </th>
      ),
      td: ({ children: c }) => (
        <td className="border-b border-r border-[#F4F4F5] px-4 py-2 font-medium text-[#242529] last:border-r-0 [tr:last-child>&]:border-b-0">
          {c}
        </td>
      ),
      img: ({ src, alt }) => {
        const inTestLayout = isTestContext || isExtractBody || isTestQuestion;
        return (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={alt ?? ""}
            className={cn(
              "my-2 max-w-full rounded-lg",
              inTestLayout && `my-3 ${TEST_MARKDOWN_IMAGE_CLASS}`,
              isExtractBody && "rounded-none shadow-none ring-0",
            )}
            loading="lazy"
          />
        );
      },
      pre({ children: c }) {
        return <>{c}</>;
      },
      code({ className, children: c, ...props }) {
        if (className === "language-extract") {
          const raw = String(c).trim();
          if (isExtractBody || isTestQuestion) {
            return (
              <ReactMarkdown
                remarkPlugins={REMARK_PLUGINS}
                rehypePlugins={REHYPE_PLUGINS}
                components={createMarkdownComponents("testContextExtractBody")}
              >
                {raw}
              </ReactMarkdown>
            );
          }
          return (
            <ExtractPanelShell>
              <ReactMarkdown
                remarkPlugins={REMARK_PLUGINS}
                rehypePlugins={REHYPE_PLUGINS}
                components={createMarkdownComponents("testContextExtractBody")}
              >
                {raw}
              </ReactMarkdown>
            </ExtractPanelShell>
          );
        }
        if (className === "language-diagram") {
          const raw = String(c).trim();
          const lines = raw.split("\n");
          const lastLine = lines[lines.length - 1];
          const hasImage = lastLine?.startsWith("http");
          const description = hasImage ? lines.slice(0, -1).join("\n") : raw;
          const imageUrl = hasImage ? lastLine : null;

          if (isTestContext || isExtractBody) {
            return <PlainTestDiagramBlock body={raw} />;
          }

          if (isTestQuestion) {
            return <PlainTestDiagramBlock body={raw} />;
          }

          return (
            <LessonCard className="my-3 px-3.5 pt-4 pb-3.5">
              <div className="border-b border-[#F4F4F5] pb-6">
                <span className="nova-text-label-tiny-sb text-[#A1A1AA]">
                  Diagram
                </span>
              </div>

              {imageUrl && (
                <div className="flex items-center justify-start px-3.5">
                  <Image
                    src={imageUrl}
                    alt={description}
                    width={800}
                    height={500}
                    className="h-auto w-full max-w-full max-h-[min(22rem,65vh)] rounded-lg object-contain"
                    unoptimized
                  />
                </div>
              )}

              <div className="border-t border-[#F4F4F5] pt-3">
                <p className="nova-text-p-base text-[#000000AD]">
                  {description}
                </p>
              </div>
            </LessonCard>
          );
        }
        return (
          <code
            className="rounded bg-[#F1ECE9] px-1 py-0.5 font-mono text-[12px] text-[#3F3C47]"
            {...props}
          >
            {c}
          </code>
        );
      },
    };

  return components;
}

type TestContextLegacyFencedProps = { source: string; extractComps: Components };

function TestContextLegacyFenced({ source, extractComps }: TestContextLegacyFencedProps) {
  const blocks = useMemo(
    () => splitMarkdownByFences(stripTrailingStandaloneTripleColonLines(source)),
    [source],
  );
  return (
    <div>
      {blocks.map((seg, i) => {
        if (seg.type === "md") {
          const body = stripTrailingStandaloneTripleColonLines(seg.body.trim());
          if (!body) return null;
          const inner = (
            <ReactMarkdown
              remarkPlugins={REMARK_PLUGINS}
              rehypePlugins={REHYPE_PLUGINS}
              components={extractComps}
            >
              {body}
            </ReactMarkdown>
          );
          if (contextSegmentUseContextRail(body)) {
            return (
              <TestContextFigureBlock key={`md-${i}`}>{inner}</TestContextFigureBlock>
            );
          }
          return <ExtractPanelShell key={`md-${i}`}>{inner}</ExtractPanelShell>;
        }
        if (seg.type === "fenced" && seg.lang === "diagram") {
          return (
            <TestContextFigureBlock key={`dia-${i}`}>
              <PlainTestDiagramBlock body={seg.body} contextColumn />
            </TestContextFigureBlock>
          );
        }
        if (seg.type === "fenced" && (seg.lang === "extract" || seg.lang === "")) {
          const innerBody = stripTrailingStandaloneTripleColonLines(seg.body.trim());
          if (!innerBody) return null;
          const inner = (
            <ReactMarkdown
              remarkPlugins={REMARK_PLUGINS}
              rehypePlugins={REHYPE_PLUGINS}
              components={extractComps}
            >
              {innerBody}
            </ReactMarkdown>
          );
          if (contextSegmentUseContextRail(innerBody)) {
            return (
              <TestContextFigureBlock key={`ex-${i}`}>
                {inner}
              </TestContextFigureBlock>
            );
          }
          return <ExtractPanelShell key={`ex-${i}`}>{inner}</ExtractPanelShell>;
        }
        if (seg.type === "fenced") {
          return (
            <pre
              key={`c-${i}`}
              className="my-3 overflow-x-auto rounded-lg bg-zinc-900 p-3 font-mono text-[13px] text-zinc-100"
            >
              <code>{seg.body}</code>
            </pre>
          );
        }
        return null;
      })}
    </div>
  );
}

function TestContextBlockMarkdown({ source }: { source: string }) {
  const extractComps = useMemo(
    () => createMarkdownComponents("testContextExtractBody") as Components,
    [],
  );
  const normalizedSource = useMemo(
    () => stripTrailingStandaloneTripleColonLines(source),
    [source],
  );
  const topSegments = useMemo(() => {
    if (!sourceHasTestContextDirectives(normalizedSource)) {
      return null;
    }
    return parseTestContextDirectives(normalizedSource);
  }, [normalizedSource]);

  if (topSegments === null) {
    return (
      <TestContextLegacyFenced
        source={normalizedSource}
        extractComps={extractComps}
      />
    );
  }

  return (
    <div>
      {topSegments.map((seg, idx) => {
        const k = `tc-${idx}`;
        if (seg.kind === "legacy") {
          return (
            <TestContextLegacyFenced
              key={k}
              source={seg.content}
              extractComps={extractComps}
            />
          );
        }
        if (seg.kind === "text") {
          return (
            <ExtractPanelShell key={k}>
              {seg.label ? (
                <p
                  className={cn("mb-2 last:mb-0", TEST_CONTEXT_EXTRACT_LABEL_CLASS)}
                >
                  {seg.label}
                </p>
              ) : null}
              {seg.body ? (
                <ReactMarkdown
                  remarkPlugins={REMARK_PLUGINS}
                  rehypePlugins={REHYPE_PLUGINS}
                  components={extractComps}
                >
                  {seg.body}
                </ReactMarkdown>
              ) : null}
            </ExtractPanelShell>
          );
        }
        return (
          <TestContextFigureBlock key={k}>
            {seg.label ? (
              <p
                className={cn("mb-2 last:mb-0", TEST_CONTEXT_EXTRACT_LABEL_CLASS)}
              >
                {seg.label}
              </p>
            ) : null}
            {seg.body ? (
              <ReactMarkdown
                remarkPlugins={REMARK_PLUGINS}
                rehypePlugins={REHYPE_PLUGINS}
                components={extractComps}
              >
                {seg.body}
              </ReactMarkdown>
            ) : null}
          </TestContextFigureBlock>
        );
      })}
    </div>
  );
}

export const Md = memo(function Md({
  children,
  inline = false,
  oneLine,
  variant = "default",
}: MdProps) {
  const prepared = useMemo(
    () => normalizeLessonMathDelimiters(applySourceCitationMarkdown(String(children))),
    [children],
  );

  const components = useMemo((): Components => {
    const block = createMarkdownComponents(variant) as Components;
    if (inline || oneLine) {
      return {
        ...block,
        p: ({ children: pChildren }) => (
          <span
            className={cn(
              "inline",
              (variant === "boldQuestion" || variant === "testQuestion") &&
                BOLD_QUESTION_TEXT,
              variant === "testContext" &&
                "font-(family-name:--font-inter) text-[14px] font-normal leading-[22px] text-[rgba(36,37,41,0.68)]",
            )}
          >
            {pChildren}
          </span>
        ),
      };
    }
    return block;
  }, [inline, oneLine, variant]);

  if (variant === "testContext" && !inline && !oneLine) {
    return <TestContextBlockMarkdown source={prepared} />;
  }

  const disallowedElements: (keyof HTMLElementTagNameMap)[] = oneLine
    ? ["ol", "ul", "img", "code", "table"]
    : [];

  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      disallowedElements={disallowedElements}
      components={components}
    >
      {prepared}
    </ReactMarkdown>
  );
});
