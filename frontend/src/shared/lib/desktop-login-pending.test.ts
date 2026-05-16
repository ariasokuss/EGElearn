import assert from "node:assert/strict";
import test from "node:test";

import { hasDesktopLoginTokenInSearch } from "./desktop-login-pending";

test("hasDesktopLoginTokenInSearch detects pending desktop login callback", () => {
  assert.equal(hasDesktopLoginTokenInSearch("?desktop_login_token=abc"), true);
});

test("hasDesktopLoginTokenInSearch ignores regular auth callback URLs", () => {
  assert.equal(hasDesktopLoginTokenInSearch("?foo=bar"), false);
  assert.equal(hasDesktopLoginTokenInSearch(""), false);
});
