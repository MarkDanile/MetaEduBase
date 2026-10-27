/**
 * REQ-064 S4 数据预览分页：视觉与度量证据采集（手动运行，不进 CI）。
 *
 * 用途：为 S4「列表筛选/分页」强制验收节点提供「同环境、同视口、同主题、同 fixture」的
 * 改前/改后截图与结构化度量。与 e2e/README.md 既定策略一致——**不建立像素比较基线**，
 * 本脚本只产出人工评审用图，不做自动 diff 判定。
 *
 * 用法（先 build:bundle，preview 服务由 playwright 自行拉起）：
 *   REQ064_SHOT_LABEL=after METAEDU_E2E_PORT=3211 \
 *     pnpm --filter @metaedu/web exec playwright test e2e/req064-s4-pagination-shots.spec.ts
 *
 * 采集「改前」时，用 REQ064_SHOT_BASE_URL 指向**改动前基线**的预览服务：
 *   REQ064_SHOT_LABEL=before REQ064_SHOT_BASE_URL=http://localhost:3212 \
 *     METAEDU_E2E_PORT=3211 pnpm --filter @metaedu/web exec playwright test \
 *     e2e/req064-s4-pagination-shots.spec.ts
 *
 * 环境变量：
 *   REQ064_SHOT_LABEL      before | after（写入文件名与度量输出）
 *   REQ064_SHOT_DIR        输出目录（默认 /tmp/req064-s4-pagination-shots）
 *   REQ064_SHOT_BASE_URL   采集目标地址（缺省用 playwright baseURL）
 *
 * 文件名不匹配 `(-desktop|-shared|-mobile)\.spec\.ts`，因此不会被
 * `chromium-desktop` / `chromium-mobile` 两个 project 收集，不进入 CI。
 */
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { setupE2E } from "./fixtures";
import {
  CATALOG_CODE,
  installPaginationMocks,
  type DatasetSpec,
} from "./req064-s4-pagination-fixtures";

const SHOT_DIR = process.env.REQ064_SHOT_DIR ?? "/tmp/req064-s4-pagination-shots";
const LABEL = process.env.REQ064_SHOT_LABEL ?? "after";
const SHOT_BASE_URL = process.env.REQ064_SHOT_BASE_URL;

/** light/dark 做完整视觉检查。 */
const FULL_THEMES = ["light", "dark"] as const;

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
];

/** fixture 数据：41 行 → 第 1 页探测到第 21 行（共 3 页）。 */
const DATASETS: DatasetSpec[] = [{ id: "ds-bill", name: "账单数据集", total: 41 }];

function target(pathname: string): string {
  if (!SHOT_BASE_URL) return pathname;
  return `${SHOT_BASE_URL.replace(/\/$/, "")}${pathname}`;
}

/**
 * 经真实主题 store 的持久化键切换主题并重载，保持与用户路径一致。
 */
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
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(expected);
}

async function openPreview(page: import("@playwright/test").Page) {
  await page.goto(target(`/database/${CATALOG_CODE}`));
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /账单数据集/ }).first().click();
  await page.waitForTimeout(600);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await mkdir(SHOT_DIR, { recursive: true });
});

test(`REQ-064 S4 数据预览分页截图 light/dark [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installPaginationMocks(page, DATASETS);
  await openPreview(page);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    for (const theme of FULL_THEMES) {
      await switchTheme(page, theme);
      await page.screenshot({
        path: path.join(SHOT_DIR, `${LABEL}-s4-data-preview-${vp.name}-${theme}.png`),
      });
    }
  }
});

test(`REQ-064 S4 数据预览分页第二页截图 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  await installPaginationMocks(page, DATASETS);
  await openPreview(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await switchTheme(page, "light");
  const next = page.getByTestId("dataset-rows-next");
  if (await next.isVisible()) {
    await next.click();
    await page.waitForTimeout(600);
  }
  await page.screenshot({
    path: path.join(SHOT_DIR, `${LABEL}-s4-data-preview-page2-1280x800-light.png`),
  });
});

/**
 * 结构化度量：把"改了什么"变成可复核的硬条件。
 * 与截图同环境（同 fixture、同角色、同视口），供人工评审对照。
 * 「改前」基线没有分页控件，度量需容忍其不存在。
 */
test(`REQ-064 S4 数据预览分页结构化度量 [${LABEL}]`, async ({ page }) => {
  await setupE2E(page, "super_admin");
  const requests = await installPaginationMocks(page, DATASETS);
  await openPreview(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await switchTheme(page, "light");

  const metrics = await page.evaluate(() => {
    const pagination = document.querySelector('[data-testid="dataset-rows-pagination"]');
    const indicator = document.querySelector('[data-testid="dataset-rows-page-indicator"]');
    const prev = document.querySelector('[data-testid="dataset-rows-prev"]') as
      | HTMLButtonElement
      | null;
    const next = document.querySelector('[data-testid="dataset-rows-next"]') as
      | HTMLButtonElement
      | null;
    const rows = document.querySelectorAll("tbody tr");
    const firstRow = rows[0]?.textContent?.trim() ?? "";
    return {
      paginationPresent: pagination !== null,
      pageIndicator: indicator?.textContent?.trim() ?? "",
      rowsOnPage: rows.length,
      prevDisabled: prev ? prev.disabled : null,
      nextDisabled: next ? next.disabled : null,
      firstRowText: firstRow,
      hasTotalText: (pagination?.textContent ?? "").includes("共 "),
      hasTotalPagesText: (pagination?.textContent ?? "").includes("总页"),
    };
  });

  console.log(
    "METRICS " +
      JSON.stringify({
        label: LABEL,
        ...metrics,
        requestedLimits: requests.map((r) => r.limit),
        requestedOffsets: requests.map((r) => r.offset),
      }),
  );

  // 改动后必须出现分页控件、当页 20 行、无总数文案
  expect(metrics.rowsOnPage).toBe(20);
  expect(metrics.hasTotalText).toBe(false);
  expect(metrics.hasTotalPagesText).toBe(false);
});
