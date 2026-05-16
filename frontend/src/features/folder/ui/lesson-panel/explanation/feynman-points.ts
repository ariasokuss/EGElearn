import type { ThemeFeedbackItem } from "@/shared/api/generated/model";

export type CoveredPointValue = number | null | boolean;

export function coercePointScore(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (v === true) return 5;
  if (v === false) return 0;
  return 0;
}

export function sumCoveredPoints(
  points: readonly CoveredPointValue[] | null | undefined,
): number {
  if (!points?.length) return 0;
  return points.reduce<number>((sum, cur) => sum + coercePointScore(cur), 0);
}

export function percentFromCoveredPoints(
  points: readonly CoveredPointValue[] | null | undefined,
): number {
  const n = points?.length ?? 0;
  if (n === 0) return 0;
  return Math.round((sumCoveredPoints(points) / (n * 5)) * 100);
}

export function feedbackTextAt(
  feedback: readonly ThemeFeedbackItem[] | null | undefined,
  index: number,
): string {
  return feedback?.[index]?.feedback ?? "";
}
