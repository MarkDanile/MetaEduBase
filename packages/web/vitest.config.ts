import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    // 排除 Playwright e2e 目录（由 `pnpm test:e2e` 单独跑）
    exclude: ["node_modules/**", "dist/**", "e2e/**"],
  },
});
