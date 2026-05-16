export const FOLDER_NAV_HOME_ARIA_LABEL = "На главную";

export function folderTabKey(folderId: string) {
  return `novalearn:folder-tab:${folderId}`;
}

export function readSavedTab(folderId: string | null): string | null {
  if (!folderId || typeof window === "undefined") return null;
  try { return localStorage.getItem(folderTabKey(folderId)); } catch { return null; }
}

export function writeSavedTab(folderId: string | null, param: string | null) {
  if (!folderId) return;
  try { localStorage.setItem(folderTabKey(folderId), param ?? ""); } catch { /* ignore */ }
}

export const FOLDER_TABS = [
  { label: "Подготовка", param: null },
  { label: "Уроки", param: "lessons" },
  { label: "Практика", param: "practice" },
  { label: "Ошибки", param: "feedback" },
] as const satisfies ReadonlyArray<{
  label: string;
  param: string | null;
}>;

export type FolderTabParam = (typeof FOLDER_TABS)[number]["param"];

const NON_ROADMAP_FOLDER_TAB_PARAMS = new Set(
  FOLDER_TABS
    .map((tab) => tab.param)
    .filter((param): param is Exclude<FolderTabParam, null> => param !== null),
);

export function normalizeFolderTabParam(param: string | null | undefined): FolderTabParam {
  if (param == null || param === "") return null;
  return NON_ROADMAP_FOLDER_TAB_PARAMS.has(param as Exclude<FolderTabParam, null>)
    ? (param as Exclude<FolderTabParam, null>)
    : null;
}

export function resolveInitialFolderTab(
  urlParam: string | null | undefined,
  savedTab: string | null | undefined,
): FolderTabParam {
  if (urlParam == null) {
    return normalizeFolderTabParam(savedTab);
  }
  return normalizeFolderTabParam(urlParam);
}

export function resolveDisplayedFolderTab(
  urlParam: string | null | undefined,
  fallbackTab: FolderTabParam = null,
): FolderTabParam {
  if (urlParam == null) return fallbackTab;
  return normalizeFolderTabParam(urlParam);
}

export function getFolderTabIndex(param: string | null | undefined): number {
  const normalized = normalizeFolderTabParam(param);
  const index = FOLDER_TABS.findIndex((tab) => tab.param === normalized);
  return index === -1 ? 0 : index;
}
