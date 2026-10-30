import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.REQ064_SHOT_BASE_URL;
if (!baseURL) {
  throw new Error("REQ064_SHOT_BASE_URL is required; start the isolated S2 preview first");
}

/** S2 专用手动证据配置；不修改共享 shots config，不启动或复用其他服务。 */
export default defineConfig({
  testDir: ".",
  testMatch: /req064-chat-shots\.spec\.ts/,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL,
    ...devices["Desktop Chrome"],
    contextOptions: { reducedMotion: "reduce" },
    trace: "off",
  },
});
