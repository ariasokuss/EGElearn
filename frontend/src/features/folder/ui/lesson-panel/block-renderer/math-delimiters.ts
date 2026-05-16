export function normalizeLessonMathDelimiters(text: string): string {
  const parts = text.split(/(```[\s\S]*?```|`[^`]+`)/g);

  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part;

      return part
        .replace(/\\\[([\s\S]*?)\\\]/g, (_match, inner: string) => `$$${inner}$$`)
        .replace(/\\\((.*?)\\\)/g, (_match, inner: string) => `$${inner}$`);
    })
    .join("");
}
