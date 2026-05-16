export type OAuthCallbackParsed =
  | {
      ok: true;
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }
  | { ok: false; error: string; error_description?: string };

export function parseOAuthCallbackHash(hash: string): OAuthCallbackParsed | null {
  if (!hash || hash === "#") return null;
  const trimmed = hash.startsWith("#") ? hash.slice(1) : hash;
  const params = new URLSearchParams(trimmed);

  const err = params.get("error");
  if (err) {
    return {
      ok: false,
      error: err,
      error_description: params.get("error_description") ?? undefined,
    };
  }

  const access_token = params.get("access_token");
  const refresh_token = params.get("refresh_token");
  const expires_in_raw = params.get("expires_in");
  if (!access_token || !refresh_token || !expires_in_raw) return null;

  const expires_in = Number.parseInt(expires_in_raw, 10);
  if (!Number.isFinite(expires_in)) return null;

  return { ok: true, access_token, refresh_token, expires_in };
}
