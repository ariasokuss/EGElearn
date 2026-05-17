/** Wizard step definitions */
export const WIZARD_STEPS = [
  { number: 1, label: "Выбор тем" },
  { number: 2, label: "Настройка вопросов" },
  { number: 3, label: "Создание теста" },
] as const

export type TestMode = "practice" | "exam"
