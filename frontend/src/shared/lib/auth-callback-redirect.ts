type AuthCallbackRedirectInput = {
  desktopLoginToken: string | null;
};

export type AuthCallbackRedirectMode = "client" | "reload";

export function getAuthCallbackRedirectMode({
  desktopLoginToken,
}: AuthCallbackRedirectInput): AuthCallbackRedirectMode {
  return desktopLoginToken ? "reload" : "client";
}
