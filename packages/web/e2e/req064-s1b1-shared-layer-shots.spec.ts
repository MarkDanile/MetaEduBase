/**
 * REQ-064 S1b-1：共享层视觉证据采集（手动运行，不进 CI）。
 *
 * 用途：为 S1b-1「共享 CSS / 语义 token」切片提供「同环境、同视口、同主题、
 * 同 fixture」的改前/改后截图与结构化度量。与 e2e/README.md 既定策略一致——
 * **不建立像素比较基线**，本脚本只产出人工评审用图，不做自动 diff 判定。
 *
 * 用法（先 build:bundle，preview 服务由 playwright 自行拉起）：
 *   REQ064_SHOT_LABEL=after METAEDU_E2E_PORT=3101 \
 *     pnpm exec playwright test --config=playwright.shots.config.ts req064-s1b1-shared-layer-shots
 *
 * 环境变量：
 *   REQ064_SHOT_LABEL      before | after（写入文件名与度量输出）
 *   REQ064_SHOT_DIR        输出目录（默认 /tmp/req064-s1b1-shots）
 *   REQ064_SHOT_BASE_URL   采集目标地址（缺省用 playwright baseURL）
 *
 * 文件名不匹配 `(-desktop|-shared|-mobile)\.spec\.ts`，因此不会被
 * `chromium-desktop` / `chromium-mobile` 两个 project 收集，不进入 CI。
 */
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { setupE2E } from "./fixtures";

const SHOT_DIR = process.env.REQ064_SHOT_DIR ?? "/tmp/req064-s1b1-shots";
const LABEL = process.env.REQ064_SHOT_LABEL ?? "after";
const SHOT_BASE_URL = process.env.REQ064_SHOT_BASE_URL;

/** light/dark 做完整视觉检查。 */
const FULL_THEMES = ["light", "dark"] as const;

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
];

/** 模板列表页需要的最小模板数据（形状镜像 services/template.ts 的 Template）。 */
const TEMPLATE = {
  id: "tpl-1",
  name: "测试模板",
  doc_types: ["invoice"],
  fields: [{ key: "amount", label: "金额", type: "number" }],
  ai_prompt: null,
  ai_context: null,
  source_file_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  schema_version: 1,
  is_deprecated: false,
  deprecated_at: null,
  deprecated_reason: null,
};

function target(pathname: string): string {
  if (!SHOT_BASE_URL) return pathname;
  return `${SHOT_BASE_URL.replace(/\/$/, "")}${pathname}`;
}

/**
 * Playwright 路由以最后注册者胜出，这些 mock 必须注册在 setupE2E 的
 * 通用 API 前缀 catch-all 之后。
 */
async function installSharedLayerMocks(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/knowledge/nodes**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/templates**", async (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.includes("/lookup")) {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: [TEMPLATE] });
  });
}

/** 经真实主题 store 的持久化键切换主题并重载，保持与用户路径一致。 */
async function switchTheme(
  page: import("@playwright/test").Page,
  stored: string,
  expected: string = stored,
): Promise<void> {
  await page.evaluate((t: string) => {
    window.localStorage.setItem("metaedu_theme", t);
  }, stored);
  await page.reload();
  await page.waitForLoadState("networkidle");
  expect(
    await page.evaluate(() => document.documentElement.getAttribute("data-theme")),
  ).toBe(expected);
}

/** 把目标元素滚到视口中部，保证改前改后取景一致。 */
async function focusElement(
  page: import("@playwright/test").Page,
  selector: string,
): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(120);
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    (el as HTMLElement | null)?.scrollIntoView({ block: "center" });
  }, selector);
  await page.waitForTimeout(180);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

test(`REQ-064 S1b-1 静态空态面板截图 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installSharedLayerMocks(page);
  await page.goto(target("/knowledge"));
  await page.waitForLoadState("networkidle");
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const theme of FULL_THEMES) {
      await switchTheme(page, theme);
      await focusElement(page, ".ui-panel");
      await page.screenshot({
        path: path.join(SHOT_DIR, `${LABEL}-s1b1-empty-panel-${vp.name}-${theme}.png`),
      });
    }
  }
});

test(`REQ-064 S1b-1 表单输入截图 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installSharedLayerMocks(page);
  await page.goto(target("/data/templates"));
  await page.waitForLoadState("networkidle");
  await page.setViewportSize({ width: 1280, height: 800 });
  for (const theme of FULL_THEMES) {
    await switchTheme(page, theme);
    await page.getByTitle("复制").first().click();
    await focusElement(page, ".ui-input");
    await page.screenshot({
      path: path.join(SHOT_DIR, `${LABEL}-s1b1-input-${theme}.png`),
    });
  }
});

/**
 * 结构化度量：把「共享层改了什么」变成可复核的硬条件。
 * 「改前」基线没有 opt-in 类，度量需容忍其不存在。
 */
test(`REQ-064 S1b-1 共享层结构化度量 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installSharedLayerMocks(page);

  await page.goto(target("/knowledge"));
  await page.waitForLoadState("networkidle");
  const emptyPanel = page.locator(".ui-panel").first();
  await expect(emptyPanel).toBeVisible();
  const emptyMetrics = await emptyPanel.evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      hasStaticOptIn: el.classList.contains("ui-panel-static"),
      hasInteractiveOptIn: el.classList.contains("ui-panel-interactive"),
      boxShadow: cs.boxShadow,
      borderTopColor: cs.borderTopColor,
      cursor: cs.cursor,
    };
  });

  await page.goto(target("/data/templates"));
  await page.waitForLoadState("networkidle");
  await page.getByTitle("复制").first().click();
  const input = page.locator(".ui-input").first();
  await expect(input).toBeVisible();
  const inputMetrics = await input.evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      hasLeadingOptIn: el.classList.contains("ui-input-leading"),
      lineHeight: cs.lineHeight,
      fontSize: cs.fontSize,
      borderTopColor: cs.borderTopColor,
      backgroundColor: cs.backgroundColor,
    };
  });

  console.log(
    "METRICS " +
      JSON.stringify({
        label: LABEL,
        emptyPanel: emptyMetrics,
        formInput: inputMetrics,
      }),
  );
});
