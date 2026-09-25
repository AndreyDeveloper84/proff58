import { resolve } from "node:path";

import { defineConfig } from "vitest/config";

// Юнит- и компонентные тесты фронта (#435, #474). Раннер — vitest; окружение jsdom
// (нужно для рендера компонентов через Testing Library); алиас @/* как в tsconfig.
export default defineConfig({
  resolve: {
    alias: { "@": resolve(__dirname, ".") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules", ".next"],
  },
});
