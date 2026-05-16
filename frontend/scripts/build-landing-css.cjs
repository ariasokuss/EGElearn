/** Concat Astro landing `<style>` blocks (+ stripped global css) into one stylesheet. Run from repo root: node frontend/scripts/build-landing-css.cjs */
const fs = require("fs");
const path = require("path");

const landingDir = path.join(__dirname, "../../landing/src");
const FILES = [
  "components/Logo.astro",
  "components/Header.astro",
  "components/Hero.astro",
  "components/Problem.astro",
  "components/HowItWorksLoader.astro",
  "components/HowItWorks.astro",
  "components/Roadmap.astro",
  "components/Lesson.astro",
  "components/Subjects.astro",
  "components/Testing.astro",
  "components/FinalCTA.astro",
  "components/Footer.astro",
];

function extractStyle(ast) {
  const parts = [...ast.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)];
  if (parts.length === 0) return "";
  return parts.map((x) => x[1].trim()).join("\n\n");
}

let out =
  `:root {\n` +
  `  --nl-primary: #d26b3c;\n` +
  `  --nl-peach-50: #fff5ec;\n` +
  `  --nl-peach-100: #fde8d4;\n` +
  `  --nl-peach-200: #f9d4b4;\n` +
  `  --nl-cream: #fdf7f1;\n` +
  `  --nl-ink: #2a201a;\n` +
  `  --nl-ink-muted: #6b6258;\n` +
  `}\n` +
  `#nl-landing-root {\n` +
  `  font-family: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;\n` +
  `  color: var(--nl-ink);\n` +
  `  background: var(--nl-cream);\n` +
  `  scroll-behavior: smooth;\n` +
  `}\n\n` +
  `#nl-landing-root h1,\n#nl-landing-root h2,\n#nl-landing-root h3,\n#nl-landing-root .nl-font-serif {\n` +
  `  font-family: KaTeX_Main, "Fraunces", Georgia, "Times New Roman", serif;\n` +
  `  font-optical-sizing: auto;\n` +
  `}\n\n`;

for (const rel of FILES) {
  const fp = path.join(landingDir, rel);
  if (!fs.existsSync(fp)) {
    console.warn("skip missing", fp);
    continue;
  }
  let chunk = "";
  if (rel.endsWith(".astro")) {
    chunk = extractStyle(fs.readFileSync(fp, "utf8"));
  } else {
    chunk = fs.readFileSync(fp, "utf8");
    chunk = chunk.replace(/@import "tailwindcss";\s*\n\s*@theme\s*\{[\s\S]*?\}\s*\n?\s*/m, "");
  }
  if (!chunk) continue;
  out += `/* === ${rel} === */\n${chunk}\n\n`;
}

const dest = path.join(__dirname, "../src/features/landing/landing-import.css");
fs.mkdirSync(path.dirname(dest), { recursive: true });

fs.writeFileSync(dest, out, "utf8");
console.log("Wrote", dest, out.length + " chars");
