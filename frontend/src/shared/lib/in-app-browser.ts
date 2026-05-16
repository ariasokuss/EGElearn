const IN_APP_BROWSER_PATTERNS = [
  /\bFBAN\b/i,
  /\bFBAV\b/i,
  /\bFB_IAB\b/i,
  /\bInstagram\b/i,
  /\bThreads\b/i,
  /\bTikTok\b/i,
  /\bLinkedInApp\b/i,
  /\bLine\//i,
  /\bSnapchat\b/i,
  /\bPinterest\b/i,
  /\bReddit\b/i,
  /\bTwitter\b/i,
  /\bX\b.*\bTwitter\b/i,
  /;\s*wv\)/i,
];

export function isInAppBrowserUserAgent(userAgent: string | undefined | null): boolean {
  if (!userAgent) return false;
  return IN_APP_BROWSER_PATTERNS.some((pattern) => pattern.test(userAgent));
}

export function getChromeIntentUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return url;
  }

  const path = `${parsed.host}${parsed.pathname}${parsed.search}`;
  const scheme = parsed.protocol.replace(":", "");
  return `intent://${path}#Intent;scheme=${scheme};package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(url)};end`;
}
