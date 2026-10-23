import { defineConfig, devices } from "@playwright/test";

/**
 * REQ-060 Slice 4: Playwright e2e 配置。
 *
 * 项目分流（P1 修订）：
 * - chromium-desktop: 只跑 *-desktop.spec.ts + *-shared.spec.ts
 * - chromium-mobile: 只跑 *-mobile.spec.ts + *-shared.spec.ts
 * 通过 testMatch glob 模式实现，避免 mobile-only 测试在 desktop viewport 跑失败。
 *
 * REQ-064 S1a：预览服务端口隔离。
 * - `METAEDU_E2E_PORT` 指定本 worktree 独占的预览端口（默认 3000，合法范围 1024–65535）。
 * - `--strictPort`：端口已被占用时 vite 直接失败，不静默改端口。
 * - `reuseExistingServer: false`：不复用其他 checkout 已在运行的同名服务，
 *   避免测试实际打到别的 worktree 的构建产物（并行 Agent 场景）。
 *
 * CI 集成：
 * 1. `pnpm --filter @metaedu/web exec playwright install --with-deps chromium`
 * 2. `pnpm --filter @metaedu/web build`（先 build 才能 vite preview）
 * 3. `pnpm --filter @metaedu/web test:e2e`
 */
const DEFAULT_E2E_PORT = 3000;
const rawPort = process.env.METAEDU_E2E_PORT?.trim();
const port = rawPort ? Number(rawPort) : DEFAULT_E2E_PORT;
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error(
    `METAEDU_E2E_PORT must be an integer between 1024 and 65535, got "${rawPort ?? ""}"`,
  );
}
const baseURL = `http://localhost:${port}`;

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
    baseURL,
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  webServer: {
    command: `pnpm vite preview --port ${port} --strictPort`,
    url: baseURL,
    // 端口被占用时明确失败，不复用其他 checkout 的服务。
    reuseExistingServer: false,
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
