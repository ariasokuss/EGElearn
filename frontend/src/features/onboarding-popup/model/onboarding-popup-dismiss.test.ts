import assert from "node:assert/strict";
import test from "node:test";

import { getOnboardingDismissAction } from "./onboarding-popup-dismiss.ts";

test("getOnboardingDismissAction closes immediately before the video is complete", () => {
  assert.equal(
    getOnboardingDismissAction({ watchedVideoFully: false }),
    "close",
  );
});

test("getOnboardingDismissAction closes after the video is complete", () => {
  assert.equal(
    getOnboardingDismissAction({ watchedVideoFully: true }),
    "close",
  );
});
