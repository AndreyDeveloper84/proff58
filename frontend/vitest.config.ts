import { resolve } from "node:path";

import { defineConfig } from "vitest/config";

// Юнит-тесты фронта (#435/M-12). Раннер — vitest; алиас @/* как в tsconfig.
export default defineConfig({
  resolve: {
    alias: { "@": resolve(__dirname, ".") },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules", ".next"],
  },
});
