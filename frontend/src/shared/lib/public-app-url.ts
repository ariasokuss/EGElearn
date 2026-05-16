
export function getPublicAppOrigin(): string {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  const fromEnv = process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, "");
  return fromEnv ?? "";
}

export const PASSWORD_RESET_TOKEN_PARAM = "token" as const;

const PASSWORD_RESET_PATH = "/restore/reset";


export function getPasswordResetRedirectUrl(): string {
  return `${getPublicAppOrigin()}${PASSWORD_RESET_PATH}`;
}

/* http://localhost:3000/restore/reset?token */
export function getPasswordResetUrlTemplateForBackend(): string {
  const origin = getPublicAppOrigin();
  if (!origin) {
    return `<NEXT_PUBLIC_APP_URL>${PASSWORD_RESET_PATH}?${PASSWORD_RESET_TOKEN_PARAM}=`;
  }
  return `${origin}${PASSWORD_RESET_PATH}?${PASSWORD_RESET_TOKEN_PARAM}=`;
}
