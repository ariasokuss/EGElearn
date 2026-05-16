export const APP_PATHS = {
  home: "/",
  learning: "/learning",
  chat: "/chat",
  notes: "/notes",
} as const;

export type AppPath = (typeof APP_PATHS)[keyof typeof APP_PATHS];
