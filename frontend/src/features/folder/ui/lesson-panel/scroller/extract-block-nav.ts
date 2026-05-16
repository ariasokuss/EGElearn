import type { LessonBlockSchema } from "@/shared/api/generated/model";

import { parseContent } from "../block-renderer/parse-content";

export type ScrollerNavItem = {
  blockId: string;
  title: string;
  description: string;
};

const HEADING_RE = /^#{1,3}\s+(.+)/m;
const PART_TITLE_RE = /^<!--\s*PART\s+\d+:\s*(.+?)\s*-->/m;
const MAX_DESC_LENGTH = 120;

function extractIntroDescription(content: string): string {
  const lines = content.split("\n");
  const result: string[] = [];
  let pastHeading = false;

  for (const line of lines) {
    if (/^#\s/.test(line)) {
      pastHeading = true;
      continue;
    }
    if (pastHeading) {
      result.push(line);
    }
  }

  const text = result.join("\n").trim();
  return text.length > MAX_DESC_LENGTH ? text.slice(0, MAX_DESC_LENGTH) : text;
}

function extractBlockTitle(block: LessonBlockSchema): string {
  if (block.title) return block.title;

  const headingMatch = block.content.match(HEADING_RE);
  if (headingMatch) return headingMatch[1].trim();

  const partMatch = block.content.match(PART_TITLE_RE);
  if (partMatch) return partMatch[1].trim();

  return `Section ${block.block_number}`;
}

function extractBlockDescription(content: string): string {
  const segments = parseContent(content);
  for (const seg of segments) {
    if (seg.kind !== "markdown") continue;
    const lines = seg.content.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || /^#{1,3}\s/.test(trimmed)) continue;
      return trimmed.length > MAX_DESC_LENGTH
        ? trimmed.slice(0, MAX_DESC_LENGTH)
        : trimmed;
    }
  }
  return "";
}

export function extractBlockNav(
  blocks: LessonBlockSchema[],
  lessonTitle: string,
): ScrollerNavItem[] {
  return blocks.map((block, idx) => {
    if (idx === 0) {
      return {
        blockId: block.id,
        title: lessonTitle,
        description: extractIntroDescription(block.content),
      };
    }
    return {
      blockId: block.id,
      title: extractBlockTitle(block),
      description: extractBlockDescription(block.content),
    };
  });
}
