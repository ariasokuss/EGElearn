import assert from "node:assert/strict";
import test from "node:test";

import {
  FIXED_FOLDER_SECTION_TITLE,
  HOME_FOLDER_TABS,
  HOME_FOLDER_TAB_PARAMS,
} from "./home-ui-copy.ts";

test("home copy is ege-only and russian", () => {
  assert.equal(FIXED_FOLDER_SECTION_TITLE, "Предметы ЕГЭ");
  assert.deepEqual(HOME_FOLDER_TABS, [{ label: "Предметы", param: null }]);
  assert.equal(HOME_FOLDER_TAB_PARAMS.size, 0);
});
