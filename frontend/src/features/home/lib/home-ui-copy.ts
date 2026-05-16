export const HOME_FOLDER_TABS = [
  { label: "Предметы", param: null },
] as const satisfies ReadonlyArray<{
  label: string;
  param: string | null;
}>;

export const HOME_FOLDER_TAB_PARAMS = new Set<string>();

export const FIXED_FOLDER_SECTION_TITLE = "Предметы ЕГЭ";
