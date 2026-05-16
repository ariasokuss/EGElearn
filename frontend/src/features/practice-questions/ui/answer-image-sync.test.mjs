import assert from "node:assert/strict";
import test from "node:test";

import {
  fileFingerprint,
  removeUploadedAnswerImageKey,
  syncAnswerImageKeys,
} from "./answer-image-sync.ts";

function imageFile(name, size, lastModified) {
  return { name, size, lastModified };
}

test("syncAnswerImageKeys uploads missing images before returning keys in file order", async () => {
  const first = imageFile("diagram.png", 100, 1);
  const second = imageFile("extract.png", 200, 2);
  const uploadedByFingerprint = {
    [fileFingerprint(first)]: "session-answers/existing-diagram.png",
  };
  const uploaded = [];

  const keys = await syncAnswerImageKeys({
    files: [first, second],
    uploadedByFingerprint,
    uploadFile: async (file) => {
      uploaded.push(file.name);
      return `session-answers/${file.name}`;
    },
  });

  assert.deepEqual(uploaded, ["extract.png"]);
  assert.deepEqual(keys, [
    "session-answers/existing-diagram.png",
    "session-answers/extract.png",
  ]);
  assert.equal(
    uploadedByFingerprint[fileFingerprint(second)],
    "session-answers/extract.png",
  );
});

test("removeUploadedAnswerImageKey clears the removed file fingerprint only", () => {
  const first = imageFile("diagram.png", 100, 1);
  const second = imageFile("extract.png", 200, 2);
  const uploadedByFingerprint = {
    [fileFingerprint(first)]: "session-answers/diagram.png",
    [fileFingerprint(second)]: "session-answers/extract.png",
  };

  removeUploadedAnswerImageKey(uploadedByFingerprint, first);

  assert.equal(uploadedByFingerprint[fileFingerprint(first)], undefined);
  assert.equal(
    uploadedByFingerprint[fileFingerprint(second)],
    "session-answers/extract.png",
  );
});
