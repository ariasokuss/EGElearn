import { getGoogleOauthStartApiV1AuthGoogleGetUrl } from "@/shared/api/generated/api";
import { getRefCode, getVisitorId } from "@/shared/lib/referral-storage";

/**
 * Same-origin URL for GET /api/v1/auth/google (browser redirect).
 * Per API: omit `prompt` to let the backend use `select_account` (account picker).
 *
 * Override: `NEXT_PUBLIC_GOOGLE_OAUTH_PROMPT` — space-separated OIDC values
 * (`none`, `login`, `consent`, `select_account`). Empty / `0` / `false` — no query param (backend default).
 */
export function getGoogleOAuthRedirectUrl(): string {
  const raw = process.env.NEXT_PUBLIC_GOOGLE_OAUTH_PROMPT?.trim();
  const params: Record<string, string> = {};
  if (raw && raw !== "0" && raw !== "false") {
    params.prompt = raw;
  }

  const refCode = getRefCode();
  const visitorId = getVisitorId();
  if (refCode) params.ref_code = refCode;
  if (visitorId) params.visitor_id = visitorId;

  if (Object.keys(params).length === 0) {
    return getGoogleOauthStartApiV1AuthGoogleGetUrl();
  }
  return getGoogleOauthStartApiV1AuthGoogleGetUrl(params as Parameters<typeof getGoogleOauthStartApiV1AuthGoogleGetUrl>[0]);
}
