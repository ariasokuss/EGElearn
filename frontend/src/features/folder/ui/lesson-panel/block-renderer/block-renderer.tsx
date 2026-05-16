"use client";

import { memo, useMemo } from "react";

import type { FeynmanBlockRead, SessionHistoryItem } from "@/shared/api/generated/model";

import { LessonCard } from "@/shared/ui/lesson-card";

import type { AnswerRecord } from "../use-inline-quiz";
import { ContentBlock } from "./content-block";
import { FeynmanBlock } from "./feynman-block";
import { FormulaBlock } from "./formula-block";
import { Md } from "./md";
import { QuestionBlock } from "./question-block";
import {
  parseContentWithParts,
  parseFeynman,
  type Segment,
} from "./parse-content";

type BlockRendererProps = {
  content: string;
  feynmanBlocks: FeynmanBlockRead[];
  miniFeynmanHistory: SessionHistoryItem[];
  lessonId: string;
  blockId?: string;
  answers?: Map<string, AnswerRecord>;
  onSubmitAnswer?: (blockId: string, questionIndex: number, record: AnswerRecord) => void;
  /** Forwarded to FeynmanBlock so "Ask Nova" over Feynman chat text routes to the main chat. */
  onAskNova?: (text: string) => void;
};

function normalizeQuestion(text: string): string {
  return text.replace(/[*_`#>[\]]/g, "").trim().toLowerCase().replace(/\s+/g, " ");
}

/** Build a flat list of segments with pre-resolved feynman blocks and question indices. */
function resolveSegments(
  parts: { title: string | null; segments: Segment[] }[],
  feynmanBlocks: FeynmanBlockRead[],
) {
  let feynmanIdx = 0;
  let questionIdx = 0;
  return parts.map((part) => ({
    title: part.title,
    resolved: part.segments.map((seg) => {
      if (seg.kind === "directive" && seg.name === "feynman") {
        const data = parseFeynman(seg.body);
        const normalizedQ = normalizeQuestion(data.question);
        const fb =
          feynmanBlocks.find((b) => normalizeQuestion(b.question) === normalizedQ) ??
          feynmanBlocks[feynmanIdx];
        feynmanIdx++;
        return { seg, feynmanData: data, feynmanBlock: fb, questionIndex: -1 } as const;
      }
      if (seg.kind === "directive" && seg.name === "question") {
        const qi = questionIdx++;
        return { seg, feynmanData: null, feynmanBlock: undefined, questionIndex: qi } as const;
      }
      return { seg, feynmanData: null, feynmanBlock: undefined, questionIndex: -1 } as const;
    }),
  }));
}

export const BlockRenderer = memo(function BlockRenderer({
  content,
  feynmanBlocks,
  miniFeynmanHistory,
  lessonId,
  blockId,
  answers,
  onSubmitAnswer,
  onAskNova,
}: BlockRendererProps) {
  const resolved = useMemo(() => {
    const parts = parseContentWithParts(content);
    return resolveSegments(parts, feynmanBlocks);
  }, [content, feynmanBlocks]);

  return (
    <div className="flex flex-col">
      {resolved.map((part, pi) => {
        const inner = part.resolved.map((item, si) => {
          const { seg } = item;

          if (seg.kind === "markdown") {
            return <div key={si} className="px-3.5"><Md>{seg.content}</Md></div>;
          }

          if (seg.name === "feynman" && item.feynmanData) {
            return (
              <FeynmanBlock
                key={si}
                data={item.feynmanData}
                feynmanBlock={item.feynmanBlock}
                lessonId={lessonId}
                miniFeynmanHistory={miniFeynmanHistory}
                onAskNova={onAskNova}
              />
            );
          }

          if (seg.name === "question") {
            const savedAnswer = blockId && answers
              ? answers.get(`${blockId}:${item.questionIndex}`)
              : undefined;
            return (
              <QuestionBlock
                key={si}
                segment={seg}
                savedAnswer={savedAnswer}
                onSubmit={
                  blockId && onSubmitAnswer
                    ? (record) => onSubmitAnswer(blockId, item.questionIndex, record)
                    : undefined
                }
              />
            );
          }

          if (seg.name === "formula") {
            return <FormulaBlock key={si} title={seg.label} body={seg.body} />;
          }

          return <ContentBlock key={si} title={seg.label} body={seg.body} />;
        });

        return part.title ? (
          <LessonCard key={pi} className="p-1.5">
            <div className="flex flex-col gap-4">{inner}</div>
          </LessonCard>
        ) : (
          <div key={pi} className="flex flex-col gap-4">{inner}</div>
        );
      })}
    </div>
  );
});
