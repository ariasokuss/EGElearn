export type SettingsNavId =
  | "profile"
  | "limits"
  | "upgrade-plan"
  | "support"
  | "terms";

export type SettingsNavItem = {
  id: SettingsNavId;
  href: string;
  label: string;
  disabled?: boolean;
};

export const SETTINGS_NAV_MAIN: SettingsNavItem[] = [
  { id: "profile", href: "/settings/profile", label: "Профиль" },
  { id: "limits", href: "/settings/limits", label: "Лимиты", disabled: true },
  { id: "upgrade-plan", href: "/settings/upgrade-plan", label: "Тариф", disabled: true },
  { id: "support", href: "/settings/support", label: "Поддержка" },
  { id: "terms", href: "/settings/terms", label: "Условия и приватность" },
];
