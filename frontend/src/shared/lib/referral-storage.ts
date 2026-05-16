const REF_COOKIE = "novalearn_ref";
const VID_COOKIE = "novalearn_vid";
const MAX_AGE = 30 * 24 * 60 * 60; // 30 days in seconds

function setCookie(name: string, value: string, maxAge = MAX_AGE) {
  document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${maxAge};SameSite=Lax`;
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

// --- Referral code ---

export function getRefCode(): string | null {
  return getCookie(REF_COOKIE);
}

export function setRefCode(code: string) {
  setCookie(REF_COOKIE, code);
}

// --- Visitor ID ---

export function getVisitorId(): string | null {
  return getCookie(VID_COOKIE);
}

export function ensureVisitorId(): string {
  const existing = getCookie(VID_COOKIE);
  if (existing) return existing;
  const id = crypto.randomUUID();
  setCookie(VID_COOKIE, id);
  return id;
}
