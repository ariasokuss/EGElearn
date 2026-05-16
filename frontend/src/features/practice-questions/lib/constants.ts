/** Wizard step definitions */
export const WIZARD_STEPS = [
  { number: 1, label: "Темы" },
  { number: 2, label: "Вопросы" },
  { number: 3, label: "Генерация" },
] as const

export type TestMode = "practice" | "exam"

export const PRACTICE_HISTORY_GROUPS = {
  notStarted: "Новые тесты",
  started: "Начатые тесты",
  completed: "Завершенные тесты",
} as const

export function normalizePracticeHistoryGroup(group: string | null | undefined): string {
  if (!group) return ""
  if (group === "Not started tests") return PRACTICE_HISTORY_GROUPS.notStarted
  if (group === "Started tests") return PRACTICE_HISTORY_GROUPS.started
  if (group === "Completed tests") return PRACTICE_HISTORY_GROUPS.completed
  return group
}
