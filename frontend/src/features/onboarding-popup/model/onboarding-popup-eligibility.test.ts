import assert from "node:assert/strict";
import test from "node:test";

import { isDesktopOnboardingEnvironment } from "./onboarding-popup-eligibility";

test("isDesktopOnboardingEnvironment rejects smartphone user agents", () => {
  assert.equal(
    isDesktopOnboardingEnvironment({
      userAgent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
      maxTouchPoints: 5,
      platform: "iPhone",
      viewportWidth: 390,
    }),
    false,
  );
});

test("isDesktopOnboardingEnvironment rejects narrow mobile-sized viewports even with desktop UA", () => {
  assert.equal(
    isDesktopOnboardingEnvironment({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      maxTouchPoints: 0,
      platform: "MacIntel",
      viewportWidth: 430,
    }),
    false,
  );
});

test("isDesktopOnboardingEnvironment allows desktop browsers", () => {
  assert.equal(
    isDesktopOnboardingEnvironment({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      maxTouchPoints: 0,
      platform: "MacIntel",
      viewportWidth: 1280,
    }),
    true,
  );
});
