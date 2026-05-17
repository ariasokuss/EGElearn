export function scoreMessage(p: number): string {
  if (p >= 90) return "Отличный результат!";
  if (p >= 70) return "Хорошая работа!";
  if (p >= 50) return "Неплохая попытка!";
  return "Продолжай тренироваться!";
}
