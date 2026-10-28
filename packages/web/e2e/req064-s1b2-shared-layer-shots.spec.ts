/**
 * REQ-064 S1b-2：共享组件采用的视觉证据采集（手动运行，不进 CI）。
 *
 * 用途：为 S1b-2「共享组件采用」提供「同环境、同视口、同主题、同 fixture」的
 * 改前/改后截图与结构化度量。与 e2e/README.md 既定策略一致——**不建立像素比较
 * 基线**，本脚本只产出人工评审用图，不做自动 diff 判定。
 *
 * 用法（先 build:bundle，preview 服务由 playwright 自行拉起）：
 *   REQ064_SHOT_LABEL=after METAEDU_E2E_PORT=3101 \
 *     pnpm exec playwright test --config=playwright.shots.config.ts req064-s1b2-shared-layer-shots
 *
 * 采集内容（本切片**在真实页面上可见**的共享层变化）：
 * - 导入模板对话框的**解析失败态**：文件输入的错误边框（S1b-2 新增 `.is-error` 生产者）；
 * - 导入模板对话框的**导入进行中**：文件输入的加载边框（S1b-2 新增 `.is-loading` 生产者）。
 *
 * 边界（不夸大覆盖）：`.ui-table` 表格契约的唯一消费方是无独立路由的嵌套组件、
 * `.ui-dialog-busy` 在真实流程中不可见、UiComposer 在本切片无生产消费方——
 * 三者均以组件级单测锁定，不在此处取证。
 */
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { setupE2E } from "./fixtures";

const SHOT_DIR = process.env.REQ064_SHOT_DIR ?? "/tmp/req064-s1b2-shots";
const LABEL = process.env.REQ064_SHOT_LABEL ?? "after";
const SHOT_BASE_URL = process.env.REQ064_SHOT_BASE_URL;

/** light/dark 做完整视觉检查。 */
const FULL_THEMES = ["light", "dark"] as const;

const VIEWPORTS = [
  { name: "1280x800", width: 1280, height: 800 },
  { name: "390x844", width: 390, height: 844 },
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

async function installTemplateMocks(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/templates**", async (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url.includes("/lookup")) {
      await route.fulfill({ json: [] });
      return;
    }
    if (url.endsWith("/import")) {
      // 保持请求 pending，用于观察导入进行中的加载态
      await new Promise((resolve) => setTimeout(resolve, 5000));
      await route.fulfill({ json: { ...TEMPLATE, id: "tpl-2" } });
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

/** 把对话框滚动进视口，保证改前改后取景一致。 */
async function focusDialog(page: import("@playwright/test").Page): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(120);
  await page.evaluate(() => {
    const el = document.querySelector(".modal");
    (el as HTMLElement | null)?.scrollIntoView({ block: "center" });
  });
  await page.waitForTimeout(180);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

test(`REQ-064 S1b-2 导入对话框错误态截图 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installTemplateMocks(page);

  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const theme of FULL_THEMES) {
      await page.goto(target("/data/templates"));
      await page.waitForLoadState("networkidle");
      await switchTheme(page, theme);
      await page.getByRole("button", { name: "导入模板" }).click();

      const fileInput = page.locator('input[type="file"]');
      await expect(fileInput).toBeVisible();
      await fileInput.setInputFiles({
        name: "bad.json",
        mimeType: "application/json",
        buffer: Buffer.from("{not-json", "utf-8"),
      });
      await expect(page.locator(".error-box")).toBeVisible();
      // 等 .ui-input 的 border-color 过渡（300ms）结束再取景，否则拍到的是过渡起始色
      await page.waitForTimeout(700);

      await focusDialog(page);
      await page.screenshot({
        path: path.join(SHOT_DIR, `${LABEL}-s1b2-import-error-${vp.name}-${theme}.png`),
      });
    }
  }
});

test(`REQ-064 S1b-2 导入对话框加载态截图 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installTemplateMocks(page);
  await page.setViewportSize({ width: 1280, height: 800 });

  for (const theme of FULL_THEMES) {
    await page.goto(target("/data/templates"));
    await page.waitForLoadState("networkidle");
    await switchTheme(page, theme);
    await page.getByRole("button", { name: "导入模板" }).click();

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "ok.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          format: "metaedu-template-v1",
          template: { name: "测试模板", doc_types: ["invoice"], fields: [] },
        }),
        "utf-8",
      ),
    });
    await expect(page.locator(".preview-box")).toBeVisible();
    await page.getByRole("button", { name: /确认导入/ }).click();
    // 改前基线没有 .is-loading 状态类，度量需容忍其不存在（只记录，不断言）
    await page.waitForTimeout(300);
    const hasLoading = await fileInput.evaluate((el) =>
      el.className.includes("is-loading"),
    );
    expect(typeof hasLoading).toBe("boolean");
    // 等过渡结束再取景
    await page.waitForTimeout(700);

    await focusDialog(page);
    await page.screenshot({
      path: path.join(SHOT_DIR, `${LABEL}-s1b2-import-loading-1280x800-${theme}.png`),
    });
  }
});

/**
 * 结构化度量：把「共享层改了什么」变成可复核的硬条件。
 * 「改前」基线没有新增的 opt-in 状态类，度量需容忍其不存在。
 */
test(`REQ-064 S1b-2 共享组件采用结构化度量 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installTemplateMocks(page);
  await page.goto(target("/data/templates"));
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "导入模板" }).click();

  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toBeVisible();
  const readState = () =>
    fileInput.evaluate((el) => {
      const cs = getComputedStyle(el);
      return {
        classes: el.className,
        borderTopColor: cs.borderTopColor,
        lineHeight: cs.lineHeight,
        fontSize: cs.fontSize,
      };
    });

  const rest = await readState();
  await fileInput.setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from("{not-json", "utf-8"),
  });
  await expect(page.locator(".error-box")).toBeVisible();
  // .ui-input 的 border-color 过渡为 300ms（all），过早读会拿到过渡起始色
  await page.waitForTimeout(700);
  const errorState = await readState();

  console.log(
    "METRICS " +
      JSON.stringify({
        label: LABEL,
        inputRest: rest,
        inputError: errorState,
        hasErrorOptIn: errorState.classes.includes("is-error"),
        hasLeadingOptIn: rest.classes.includes("ui-input-leading"),
      }),
  );
});
