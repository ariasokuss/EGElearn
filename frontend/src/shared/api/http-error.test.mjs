import assert from "node:assert/strict";
import test from "node:test";

import { HttpError, getHttpStatus, throwHttpError } from "./http-error.ts";
import { getUploadErrorMessage } from "./http-error-message.ts";

test("throwHttpError parses JSON detail field", async () => {
  const response = new Response(JSON.stringify({ detail: "File too large" }), {
    status: 413,
    statusText: "Payload Too Large",
    headers: { "content-type": "application/json" },
  });

  await assert.rejects(
    () => throwHttpError(response),
    (error) => {
      assert.ok(error instanceof HttpError);
      assert.equal(error.status, 413);
      assert.equal(error.details, "File too large");
      return true;
    },
  );
});

test("throwHttpError ignores html payload details", async () => {
  const response = new Response("<html><body>nginx error page</body></html>", {
    status: 500,
    statusText: "Internal Server Error",
    headers: { "content-type": "text/html" },
  });

  await assert.rejects(
    () => throwHttpError(response),
    (error) => {
      assert.ok(error instanceof HttpError);
      assert.equal(error.details, undefined);
      return true;
    },
  );
});

test("getHttpStatus returns status only for HttpError", () => {
  assert.equal(getHttpStatus(new HttpError(429, "Too Many Requests")), 429);
  assert.equal(getHttpStatus(new Error("generic error")), null);
});

test("getUploadErrorMessage maps known statuses", () => {
  assert.match(getUploadErrorMessage(413, "paper"), /too large/i);
  assert.match(getUploadErrorMessage(429, "paper"), /too many upload attempts/i);
  assert.match(getUploadErrorMessage(500, "mark_scheme"), /server error/i);
  assert.match(getUploadErrorMessage(null, "paper"), /try again/i);
});
