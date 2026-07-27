import { defineConfig, configDefaults } from "vitest/config";
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
    // 在 Vitest 默认排除项基础上追加 e2e/**（由 `pnpm test:e2e` 单独跑）
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});