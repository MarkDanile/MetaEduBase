/**
 * REQ-064 视觉证据采集专用配置（手动运行，不进 CI）。
 *
 * 与 `playwright.config.ts` 分开的原因：主配置的 project 级 `testMatch` 只收集
 * `*-desktop` / `*-mobile` / `*-shared`，本目录下的截图采集脚本按设计不参与
 * CI 常规 e2e（截图用于人工视觉确认，不建立像素基线）。用本配置显式运行：
 *
 *   REQ064_SHOT_LABEL=before METAEDU_E2E_PORT=3201 \
 *     pnpm --filter @metaedu/web exec playwright test --config=playwright.shots.config.ts
 *
 * 覆盖的截图 spec：S1a 外壳（`req064-s1a-shell-shots.spec.ts`）与 S4 数据预览
 * 分页（`req064-s4-pagination-shots.spec.ts`）。S4 采集「改前」时用
 * REQ064_SHOT_BASE_URL 指向改动前基线的预览服务。
 *
 * 端口规则与主配置一致：METAEDU_E2E_PORT（默认 3000，范围 1024–65535）、
 * --strictPort、reuseExistingServer=false（端口被占用时明确失败）。
 */
import { defineConfig, devices } from "@playwright/test";

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
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL,
    trace: "off",
  },
  webServer: {
    command: `pnpm vite preview --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    {
      name: "shots",
      testMatch:
        /req064-s1a-shell-shots\.spec\.ts|req064-s4-pagination-shots\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
