export type MdSegment = {
  kind: "markdown";
  content: string;
};

export type DirectiveName =
  | "definition"
  | "formula"
  | "application"
  | "takeaway"
  | "feynman"
  | "question";

export type DirectiveSegment = {
  kind: "directive";
  name: DirectiveName;
  subtype?: string;
  label?: string;
  body: string;
};

export type Segment = MdSegment | DirectiveSegment;

export type McqOption = { key: string; text: string };

export type McqData = {
  question: string;
  options: McqOption[];
  correct: string;
  feedback: string;
};

export type OpenQuestionData = {
  question: string;
  marks: number;
  markscheme: string;
  modelAnswer: string;
};

export type FeynmanData = {
  question: string;
  points: string[];
};

function parseDirectiveHeader(rest: string): { subtype?: string; label?: string } {
  const trimmed = rest.trim();
  if (!trimmed) return {};
  const labelMatch = trimmed.match(/\[([^\]]+)\]/);
  const subtypeMatch = !trimmed.startsWith("[") ? trimmed.match(/^(\w+)/) : null;
  return {
    subtype: subtypeMatch?.[1],
    label: labelMatch?.[1],
  };
}

export function parseMcq(body: string): McqData {
  const correctMatch = body.match(/^correct:\s*([A-D])/m);
  const feedbackMatch = body.match(/^feedback:\s*(.+)$/m);

  const stripped = body
    .replace(/^correct:.*$/m, "")
    .replace(/^feedback:.*$/m, "")
    .trim();

  const optionRe = /^(?:-\s+)?([A-D])[.)]\s+(.+)$/gm;
  const options: McqOption[] = [];
  let match: RegExpExecArray | null;
  let firstOptionIndex = stripped.length;

  const firstCheck = /^(?:-\s+)?[A-D][.)]\s/m.exec(stripped);
  if (firstCheck) firstOptionIndex = firstCheck.index;

  while ((match = optionRe.exec(stripped)) !== null) {
    options.push({ key: match[1], text: match[2].trim() });
  }

  return {
    question: stripped.slice(0, firstOptionIndex).trim(),
    options,
    correct: correctMatch?.[1] ?? "",
    feedback: feedbackMatch?.[1]?.trim() ?? "",
  };
}

export function parseOpenQuestion(body: string, marksStr?: string): OpenQuestionData {
  const markschemeIdx = body.search(/^mark_?scheme:/m);
  const modelAnswerIdx = body.search(/^model_answer:/m);

  const firstMetaIdx = Math.min(
    markschemeIdx !== -1 ? markschemeIdx : Infinity,
    modelAnswerIdx !== -1 ? modelAnswerIdx : Infinity,
  );

  const question = firstMetaIdx === Infinity ? body.trim() : body.slice(0, firstMetaIdx).trim();

  let markschemeRaw = "";
  if (markschemeIdx !== -1) {
    const keyMatch = body.slice(markschemeIdx).match(/^mark_?scheme:/);
    const keyLen = keyMatch ? keyMatch[0].length : "markscheme:".length;
    const start = markschemeIdx + keyLen;
    const end = modelAnswerIdx !== -1 && modelAnswerIdx > markschemeIdx ? modelAnswerIdx : body.length;
    markschemeRaw = body.slice(start, end).trim();
  }

  let modelAnswerRaw = "";
  if (modelAnswerIdx !== -1) {
    const start = modelAnswerIdx + "model_answer:".length;
    const end = markschemeIdx !== -1 && markschemeIdx > modelAnswerIdx ? markschemeIdx : body.length;
    modelAnswerRaw = body.slice(start, end).trim().replace(/^"|"$/g, "");
  }

  return {
    question,
    marks: parseInt(marksStr ?? "0", 10) || 0,
    markscheme: markschemeRaw,
    modelAnswer: modelAnswerRaw,
  };
}

export function parseFeynman(body: string): FeynmanData {
  const pointsIdx = body.search(/^points:/m);
  if (pointsIdx === -1) return { question: body.trim(), points: [] };
  const question = body.slice(0, pointsIdx).trim();
  const pointsSection = body.slice(pointsIdx);
  const points: string[] = [];
  const pointRe = /^-\s+(.+)$/gm;
  let match: RegExpExecArray | null;
  while ((match = pointRe.exec(pointsSection)) !== null) {
    points.push(match[1].trim());
  }
  return { question, points };
}

function preprocessMarkdown(md: string): string {
  return md
    .replace(
      /\[DIAGRAM:\s*([^\]]+)\]\s*\n\s*!\[(?:[^\]]*)\]\(([^)]+)\)/g,
      (_, desc, url) =>
        `\n\`\`\`diagram\n${desc.trim()}\n${url.trim()}\n\`\`\`\n`,
    )
    .replace(
      /\[DIAGRAM:\s*([^\]]+)\]/g,
      (_, desc) => `\n\`\`\`diagram\n${desc.trim()}\n\`\`\`\n`,
    );
}

export type PartBlock = {
  title: string | null;
  segments: Segment[];
};

export function parseContentWithParts(content: string): PartBlock[] {
  const partOpenRe = /^<!--\s*PART\s+\d+:\s*(.+?)\s*-->$/;
  const partCloseRe = /^<!--\s*\/PART\s+\d+\s*-->$/;

  const lines = content.split("\n");
  const parts: PartBlock[] = [];
  let currentLines: string[] = [];
  let currentTitle: string | null = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");
    const openMatch = line.match(partOpenRe);
    const closeMatch = line.match(partCloseRe);

    if (openMatch) {
      if (currentLines.length > 0) {
        const text = currentLines.join("\n").trim();
        if (text) parts.push({ title: currentTitle, segments: parseContent(text) });
        currentLines = [];
      }
      currentTitle = openMatch[1];
    } else if (closeMatch) {
      if (currentLines.length > 0) {
        const text = currentLines.join("\n").trim();
        if (text) parts.push({ title: currentTitle, segments: parseContent(text) });
        currentLines = [];
      }
      currentTitle = null;
    } else {
      currentLines.push(line);
    }
  }

  if (currentLines.length > 0) {
    const text = currentLines.join("\n").trim();
    if (text) parts.push({ title: currentTitle, segments: parseContent(text) });
  }

  return parts;
}

export function parseContent(content: string): Segment[] {
  const lines = content.split("\n");
  const segments: Segment[] = [];
  let currentMd: string[] = [];
  let inBlock = false;
  let blockName = "";
  let blockRest = "";
  let blockLines: string[] = [];

  for (const line of lines) {
    if (!inBlock) {
      const openMatch = line.match(/^:::\s+(\w+)([ \t].*)?$/);
      if (openMatch) {
        if (currentMd.length > 0) {
          const md = currentMd.join("\n").trim();
          if (md) segments.push({ kind: "markdown", content: preprocessMarkdown(md) });
          currentMd = [];
        }
        inBlock = true;
        blockName = openMatch[1];
        blockRest = openMatch[2] ?? "";
        blockLines = [];
      } else {
        currentMd.push(line);
      }
    } else {
      if (/^:::\s*$/.test(line)) {
        const { subtype, label } = parseDirectiveHeader(blockRest);
        segments.push({
          kind: "directive",
          name: blockName as DirectiveName,
          subtype,
          label,
          body: blockLines.join("\n").trim(),
        });
        inBlock = false;
        blockName = "";
        blockRest = "";
        blockLines = [];
      } else {
        blockLines.push(line);
      }
    }
  }

  if (!inBlock && currentMd.length > 0) {
    const md = currentMd.join("\n").trim();
    if (md) segments.push({ kind: "markdown", content: preprocessMarkdown(md) });
  }

  return segments;
}
