import assert from "node:assert/strict";
import test from "node:test";

import { getDesktopLoginTokenFromSearch } from "./desktop-login-token";

test("getDesktopLoginTokenFromSearch reads desktop login token from callback query", () => {
  assert.equal(
    getDesktopLoginTokenFromSearch("?desktop_login_token=abc123"),
    "abc123",
  );
});

test("getDesktopLoginTokenFromSearch returns null when token is missing", () => {
  assert.equal(getDesktopLoginTokenFromSearch("?other=value"), null);
  assert.equal(getDesktopLoginTokenFromSearch(""), null);
});
