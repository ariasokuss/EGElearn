import assert from "node:assert/strict";
import test from "node:test";

import { getAuthCallbackRedirectMode } from "./auth-callback-redirect";

test("getAuthCallbackRedirectMode uses full page reload for desktop magic login", () => {
  assert.equal(getAuthCallbackRedirectMode({ desktopLoginToken: "token" }), "reload");
});

test("getAuthCallbackRedirectMode keeps client navigation for OAuth hash callback", () => {
  assert.equal(getAuthCallbackRedirectMode({ desktopLoginToken: null }), "client");
});
