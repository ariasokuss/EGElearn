import assert from "node:assert/strict";
import test from "node:test";

import { SETTINGS_NAV_MAIN } from "./settings-nav.ts";

test("settings navigation is russian-only", () => {
  assert.deepEqual(
    SETTINGS_NAV_MAIN.map((item) => item.label),
    ["Профиль", "Лимиты", "Тариф", "Поддержка", "Условия и приватность"],
  );
});
