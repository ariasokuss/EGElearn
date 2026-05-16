import { defineConfig } from "orval";

const specUrl = process.env.OPENAPI_SPEC_URL ?? "http://localhost:1984/openapi.json";

export default defineConfig({
  api: {
    input: {
      target: specUrl,
    },
    output: {
      mode: "single",
      target: "src/shared/api/generated/api.ts",
      schemas: "src/shared/api/generated/model",
      client: "fetch",
      baseUrl: "",
      clean: true,
    },
  },
});
