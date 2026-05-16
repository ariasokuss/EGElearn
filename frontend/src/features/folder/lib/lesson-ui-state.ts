import type { ExplanationStage } from "../ui/lesson-panel/types";

const LESSON_TAB_KEYS = ["Study", "Explanation", "Testing", "Results"] as const;
export type LessonTab = (typeof LESSON_TAB_KEYS)[number];

export type TestingSubView = "start" | "test" | "results" | "review";

export type FolderUiState = {
  pastPaperTestHistoryTab: string
  practiceQuestionsTestHistoryTab: string
};

export type FolderLessonsUiState = {
  selectedLessonId: string | null;
  lessonsListVisible: boolean;
  chatVisible: boolean;
  lessonsMainScrollTop?: number;
};

export type LessonUiState = {
  activeTab: LessonTab;
  scrollTop: number;
  explanationStage?: ExplanationStage;
  explanationFeynmanSessionId?: string | null;
  explanationResultId?: string;
  testingView?: TestingSubView;
  testingSessionId?: string | null;
  testActive?: boolean;
};

const FOLDER_UI_PREFIX = "novalearn:folder-ui:";
const FOLDER_LESSONS_UI_PREFIX = "novalearn:folder-lesson-ui:";
const LESSON_UI_PREFIX = "novalearn:lesson-ui:";

function folderKey(folderId: string): string {
  return `${FOLDER_UI_PREFIX}${folderId}`;
}

function folderLessonsKey(folderId: string): string {
  return `${FOLDER_LESSONS_UI_PREFIX}${folderId}`;
}

function lessonKey(lessonId: string): string {
  return `${LESSON_UI_PREFIX}${lessonId}`;
}

function safeRead<T>(key: string): Partial<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as Partial<T>;
  } catch {
    return null;
  }
}

function safeWrite(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / disabled storage — ignore */
  }
}

export function readFolderUi(
  folderId: string | null | undefined,
): Partial<FolderUiState> | null {
  if (!folderId) return null;
  return safeRead<FolderUiState>(folderKey(folderId));
}

export function writeFolderUi(
  folderId: string | null | undefined,
  patch: Partial<FolderUiState>,
): void {
  if (!folderId) return;
  const current = readFolderUi(folderId) ?? {};
  safeWrite(folderKey(folderId), { ...current, ...patch });
}

export function readFolderLessonsUi(
  folderId: string | null | undefined,
): Partial<FolderLessonsUiState> | null {
  if (!folderId) return null;
  return safeRead<FolderLessonsUiState>(folderLessonsKey(folderId));
}

export function writeFolderLessonsUi(
  folderId: string | null | undefined,
  patch: Partial<FolderLessonsUiState>,
): void {
  if (!folderId) return;
  const current = readFolderLessonsUi(folderId) ?? {};
  safeWrite(folderLessonsKey(folderId), { ...current, ...patch });
}

export function readLessonUi(
  lessonId: string | null | undefined,
): Partial<LessonUiState> | null {
  if (!lessonId) return null;
  return safeRead<LessonUiState>(lessonKey(lessonId));
}

export function writeLessonUi(
  lessonId: string | null | undefined,
  patch: Partial<LessonUiState>,
): void {
  if (!lessonId) return;
  const current = readLessonUi(lessonId) ?? {};
  safeWrite(lessonKey(lessonId), { ...current, ...patch });
}

export type LessonRefLike = {
  lesson_id?: string | null;
  id?: string | null;
};

export function lessonUiStorageKey(lesson: LessonRefLike): string | null {
  const a = lesson.lesson_id?.trim();
  if (a) return a;
  const b = lesson.id?.trim();
  return b || null;
}

export function readLessonUiForLesson(
  lesson: LessonRefLike,
): Partial<LessonUiState> | null {
  const k1 = lesson.lesson_id?.trim();
  const k2 = lesson.id?.trim();
  if (!k1 && !k2) return null;
  if (k1 && k2 && k1 !== k2) {
    const fromNode = readLessonUi(k2) ?? {};
    const fromLesson = readLessonUi(k1) ?? {};
    const merged = { ...fromNode, ...fromLesson };
    return Object.keys(merged).length > 0 ? merged : null;
  }
  return readLessonUi(k1 ?? k2 ?? undefined);
}

export function writeLessonUiForLesson(
  lesson: LessonRefLike,
  patch: Partial<LessonUiState>,
): void {
  const key = lessonUiStorageKey(lesson);
  if (!key) return;
  const baseline = readLessonUiForLesson(lesson) ?? {};
  safeWrite(lessonKey(key), { ...baseline, ...patch });
}

export function clearLessonUiForLesson(lesson: LessonRefLike): void {
  const k1 = lesson.lesson_id?.trim();
  const k2 = lesson.id?.trim();
  if (k1) clearLessonUi(k1);
  if (k2 && k2 !== k1) clearLessonUi(k2);
}

/** Remove persisted tab + scroll state for a lesson (e.g. after Redo lesson). */
export function clearLessonUi(lessonId: string | null | undefined): void {
  if (!lessonId || typeof window === "undefined") return;
  try {
    localStorage.removeItem(lessonKey(lessonId));
  } catch {
    /* ignore */
  }
}

export function isLessonTab(value: unknown): value is LessonTab {
  return (
    typeof value === "string" &&
    (LESSON_TAB_KEYS as readonly string[]).includes(value)
  );
}

const EXPLANATION_STAGES = ["start", "chat", "result"] as const;

export function isExplanationStage(value: unknown): value is ExplanationStage {
  return (
    typeof value === "string" &&
    (EXPLANATION_STAGES as readonly string[]).includes(value)
  );
}

const TESTING_SUB_VIEWS = ["start", "test", "results", "review"] as const;

export function isTestingSubView(value: unknown): value is TestingSubView {
  return (
    typeof value === "string" &&
    (TESTING_SUB_VIEWS as readonly string[]).includes(value)
  );
}

export function isLessonTestFullscreenUi(
  u: Partial<LessonUiState> | null | undefined,
): boolean {
  if (!u) return false;
  if (u.testActive === true) return true;
  return u.testingView === "test";
}
