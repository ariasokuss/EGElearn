import assert from "node:assert/strict";
import test from "node:test";

import { shouldRenderMainAppChildren } from "./main-app-mobile-gate-visibility";

test("shouldRenderMainAppChildren hides desktop app children on phone after auth loading", () => {
  assert.equal(shouldRenderMainAppChildren({ isPhone: true, isLoading: false }), false);
});

test("shouldRenderMainAppChildren keeps desktop app children on desktop", () => {
  assert.equal(shouldRenderMainAppChildren({ isPhone: false, isLoading: false }), true);
});

test("shouldRenderMainAppChildren hides desktop app children while phone auth is loading", () => {
  assert.equal(shouldRenderMainAppChildren({ isPhone: true, isLoading: true }), false);
});
