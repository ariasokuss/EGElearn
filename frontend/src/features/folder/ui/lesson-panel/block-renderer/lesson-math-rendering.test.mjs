import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";

import { normalizeLessonMathDelimiters } from "./math-delimiters.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const globalsCssPath = path.resolve(
  __dirname,
  "../../../../../shared/styles/globals.css",
);

test("lesson KaTeX setup supports mhchem chemical equations", async () => {
  await import("./katex-setup.ts");
  const katex = await import("katex");

  assert.doesNotThrow(() => {
    katex.default.renderToString("\\ce{N2(g) + 3H2(g) <=> 2NH3(g)}", {
      throwOnError: true,
    });
  });
});

test("lesson content keeps display math inside the lesson column", async () => {
  const css = await readFile(globalsCssPath, "utf8");

  assert.match(css, /\.lesson-content\s+\.katex-display\s*\{/);
  assert.match(css, /\.lesson-content\s+\.katex-display\s*>\s*\.katex\s*\{/);
  assert.match(css, /overflow-x:\s*auto/);
  assert.match(css, /max-width:\s*100%/);
  assert.match(css, /white-space:\s*nowrap/);
});

test("lesson markdown normalizes LaTeX math delimiters outside code spans", () => {
  const source = [
    "Inline \\(E=mc^2\\) and block:",
    "\\[a^2+b^2=c^2\\]",
    "`keep \\(code\\)`",
    "```",
    "keep \\[fenced\\]",
    "```",
  ].join("\n");

  assert.equal(
    normalizeLessonMathDelimiters(source),
    [
      "Inline $E=mc^2$ and block:",
      "$$a^2+b^2=c^2$$",
      "`keep \\(code\\)`",
      "```",
      "keep \\[fenced\\]",
      "```",
    ].join("\n"),
  );
});
