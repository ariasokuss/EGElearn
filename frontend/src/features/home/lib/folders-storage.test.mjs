import assert from "node:assert/strict";
import test from "node:test";

import {
  clearAllFoldersCaches,
  clearFoldersCache,
} from "./folders-storage.ts";

const legacyALevelPrefix = "novalearn_folders_fixed_" + "a" + "_" + "level_";
const legacyGcsePrefix = "novalearn_folders_fixed_" + "g" + "c" + "s" + "e_";

function installLocalStorage(initialEntries) {
  const store = new Map(initialEntries);

  globalThis.window = {};
  globalThis.localStorage = {
    get length() {
      return store.size;
    },
    key(index) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key) {
      store.delete(key);
    },
    getItem(key) {
      return store.get(key) ?? null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
  };

  return store;
}

test("clearFoldersCache removes legacy fixed folder caches for the user", () => {
  const store = installLocalStorage([
    ["novalearn_folders_cache_user-1", "[]"],
    ["novalearn_folders_fixed_ege_user-1", "[]"],
    [legacyALevelPrefix + "user-1", "[]"],
    [legacyGcsePrefix + "user-1", "[]"],
    [legacyALevelPrefix + "user-2", "[]"],
  ]);

  clearFoldersCache("user-1");

  assert.deepEqual(Array.from(store.keys()), [legacyALevelPrefix + "user-2"]);
});

test("clearAllFoldersCaches removes all legacy fixed folder caches", () => {
  const store = installLocalStorage([
    ["novalearn_folders_cache_user-1", "[]"],
    ["novalearn_folders_fixed_ege_user-1", "[]"],
    [legacyALevelPrefix + "user-1", "[]"],
    [legacyGcsePrefix + "user-1", "[]"],
    ["unrelated", "value"],
  ]);

  clearAllFoldersCaches();

  assert.deepEqual(Array.from(store.keys()), ["unrelated"]);
});
