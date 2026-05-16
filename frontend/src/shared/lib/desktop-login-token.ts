export function getDesktopLoginTokenFromSearch(search: string): string | null {
  if (!search) return null;
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return params.get("desktop_login_token");
}
