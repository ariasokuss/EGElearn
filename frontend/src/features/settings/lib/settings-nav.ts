export type SettingsNavId = "profile";

export type SettingsNavItem = {
  id: SettingsNavId;
  href: string;
  label: string;
  disabled?: boolean;
};

export const SETTINGS_NAV_MAIN: SettingsNavItem[] = [
  { id: "profile", href: "/settings/profile", label: "Профиль" },
];
