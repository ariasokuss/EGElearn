export function scoreMessage(p: number): string {
  if (p >= 90) return "Excellent!";
  if (p >= 70) return "Well done!";
  if (p >= 50) return "Good effort!";
  return "Keep practicing!";
}
