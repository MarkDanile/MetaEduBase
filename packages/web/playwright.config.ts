/**
 * REQ-060 Slice 4: Playwright e2e 配置。
 *
 * 覆盖：
 * - chromium-desktop (1280x800) + chromium-mobile (Pixel 5) 两 project
 * - webServer: 自启动 `vite preview --port 3000`（生产构建）
 * - baseURL: http://localhost:3000
 * - headless + CI 默认；本地开发可 `PWDEBUG=1` 调试
 *
 * CI 集成（计划在 turbo.json + .github/workflows）：
 * 1. `pnpm --filter @metaedu/web exec playwright install --with-deps chromium`
 * 2. `pnpm --filter @metaedu/web build`（先 build 才能 vite preview）
 * 3. `pnpm --filter @metaedu/web test:e2e`
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  webServer: {
    command: "pnpm vite preview --port 3000",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 5"] },
    },
  ],
});