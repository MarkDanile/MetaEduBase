/**
 * REQ-060 Slice 4: Playwright e2e 配置。
 *
 * 项目分流（P1 修订）：
 * - chromium-desktop: 只跑 *-desktop.spec.ts + *-shared.spec.ts
 * - chromium-mobile: 只跑 *-mobile.spec.ts + *-shared.spec.ts
 * 通过 testMatch glob 模式实现，避免 mobile-only 测试在 desktop viewport 跑失败。
 *
 * CI 集成：
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
      testMatch: /.*(-desktop|-shared)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "chromium-mobile",
      testMatch: /.*(-mobile|-shared)\.spec\.ts/,
      use: { ...devices["Pixel 5"] },
    },
  ],
});