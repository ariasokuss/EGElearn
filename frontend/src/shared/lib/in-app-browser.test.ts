import assert from "node:assert/strict";
import test from "node:test";

import {
  getChromeIntentUrl,
  isInAppBrowserUserAgent,
} from "./in-app-browser";

test("isInAppBrowserUserAgent detects common embedded app browsers", () => {
  const embeddedUserAgents = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro Build/AP2A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.0.0 Mobile Safari/537.36 Instagram 356.0.0.0.81 Android",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 337.0.0.28.77",
    "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/442.0.0.0.0;]",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 TikTok 34.1.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 LinkedInApp",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/121.0.0.0 Mobile Safari/537.36 Threads",
  ];

  for (const userAgent of embeddedUserAgents) {
    assert.equal(isInAppBrowserUserAgent(userAgent), true, userAgent);
  }
});

test("isInAppBrowserUserAgent allows regular mobile browsers", () => {
  const browserUserAgents = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
  ];

  for (const userAgent of browserUserAgents) {
    assert.equal(isInAppBrowserUserAgent(userAgent), false, userAgent);
  }
});

test("getChromeIntentUrl builds an Android intent for https pages", () => {
  assert.equal(
    getChromeIntentUrl("https://novalearn.ai/auth?ref=abc#start"),
    "intent://novalearn.ai/auth?ref=abc#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=https%3A%2F%2Fnovalearn.ai%2Fauth%3Fref%3Dabc%23start;end",
  );
});

test("getChromeIntentUrl returns the original URL for non-http pages", () => {
  assert.equal(getChromeIntentUrl("mailto:support@novalearn.ai"), "mailto:support@novalearn.ai");
});
