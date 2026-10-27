/**
 * REQ-064 S4 数据预览分页 e2e（D-P1=3a 数据预览 + D-P2=B `limit+1` 探测）。
 *
 * 覆盖：
 * - 每页展示 20 行，请求 21 行（页大小 + 1）探测下一页。
 * - 有第 21 行 → 「下一页」可用；末页（不足 21 行）→ 「下一页」禁用。
 * - 翻页请求 offset = 页码 * 20；首页「上一页」禁用；页码指示同步更新。
 * - 不展示总条数 / 总页数。
 * - 并发保护：切换数据集时，上一个数据集的迟到响应不得覆盖当前数据集的数据。
 *
 * 数据全部来自 e2e fixture mock，不接入真实后端，也不代表生产数据形态。
 */
import { test, expect, type Page } from "@playwright/test";
import { setupE2E } from "./fixtures";
import {
  CATALOG_CODE,
  PAGE_SIZE,
  PROBE_SIZE,
  installPaginationMocks,
} from "./req064-s4-pagination-fixtures";

async function openDataPreview(page: Page, datasetName: string) {
  await page.goto(`/database/${CATALOG_CODE}`);
  await page.getByRole("button", { name: new RegExp(datasetName) }).first().click();
  await expect(page.getByTestId("dataset-rows-pagination")).toBeVisible();
}

test.describe("REQ-064 S4 数据预览分页 (D-P1=3a + D-P2=B)", () => {
  test("请求页大小 + 1 行探测下一页，且只展示当前页 20 行", async ({ page }) => {
    await setupE2E(page, "super_admin");
    const requests = await installPaginationMocks(page, [
      { id: "ds-bill", name: "账单数据集", total: 41 },
    ]);
    await openDataPreview(page, "账单数据集");

    await expect(page.locator("tbody tr")).toHaveCount(PAGE_SIZE);
    expect(requests[0]).toMatchObject({ offset: 0, limit: PROBE_SIZE });
    // 探测上限不得越过数据集 rows 端点 limit 上限 200
    expect(requests[0].limit).toBeLessThanOrEqual(200);
  });

  test("有第 21 行时「下一页」可用，翻页请求 offset = 页码 * 20", async ({ page }) => {
    await setupE2E(page, "super_admin");
    const requests = await installPaginationMocks(page, [
      { id: "ds-bill", name: "账单数据集", total: 41 },
    ]);
    await openDataPreview(page, "账单数据集");

    await expect(page.getByTestId("dataset-rows-prev")).toBeDisabled();
    await expect(page.getByTestId("dataset-rows-next")).toBeEnabled();
    await expect(page.getByTestId("dataset-rows-page-indicator")).toHaveText("第 1 页");

    await page.getByTestId("dataset-rows-next").click();
    await expect(page.getByTestId("dataset-rows-page-indicator")).toHaveText("第 2 页");
    expect(requests.some((r) => r.offset === PAGE_SIZE && r.limit === PROBE_SIZE)).toBe(true);
    await expect(page.locator("tbody tr")).toHaveCount(PAGE_SIZE);
    await expect(page.locator("tbody tr").first()).toContainText("ds-bill#20");
    await expect(page.getByTestId("dataset-rows-prev")).toBeEnabled();
  });

  test("末页不足 21 行时「下一页」禁用", async ({ page }) => {
    await setupE2E(page, "super_admin");
    await installPaginationMocks(page, [{ id: "ds-bill", name: "账单数据集", total: 41 }]);
    await openDataPreview(page, "账单数据集");

    await page.getByTestId("dataset-rows-next").click();
    await expect(page.getByTestId("dataset-rows-page-indicator")).toHaveText("第 2 页");
    await page.getByTestId("dataset-rows-next").click();
    await expect(page.getByTestId("dataset-rows-page-indicator")).toHaveText("第 3 页");

    await expect(page.getByTestId("dataset-rows-next")).toBeDisabled();
    await expect(page.locator("tbody tr")).toHaveCount(1);
  });

  test("首页「上一页」禁用，不产生额外请求", async ({ page }) => {
    await setupE2E(page, "super_admin");
    const requests = await installPaginationMocks(page, [
      { id: "ds-bill", name: "账单数据集", total: 41 },
    ]);
    await openDataPreview(page, "账单数据集");

    const before = requests.length;
    await expect(page.getByTestId("dataset-rows-prev")).toBeDisabled();
    await page.waitForTimeout(300);
    expect(requests.length).toBe(before);
  });

  test("不展示总条数与总页数", async ({ page }) => {
    await setupE2E(page, "super_admin");
    await installPaginationMocks(page, [{ id: "ds-bill", name: "账单数据集", total: 41 }]);
    await openDataPreview(page, "账单数据集");

    const pagination = page.getByTestId("dataset-rows-pagination");
    await expect(pagination).toContainText("第 1 页");
    await expect(pagination).not.toContainText("共 ");
    await expect(pagination).not.toContainText("总页");
    // 数据集元数据 row_count 不得被当作分页总数展示
    await expect(pagination).not.toContainText("41");
  });

  test("切换数据集时，上一个数据集的迟到响应不得覆盖当前数据", async ({ page }) => {
    await setupE2E(page, "super_admin");
    await installPaginationMocks(page, [
      { id: "ds-bill", name: "账单数据集", total: 41, delayOffset: PAGE_SIZE, delayMs: 1500 },
      { id: "ds-contract", name: "合同数据集", total: 25 },
    ]);
    await openDataPreview(page, "账单数据集");

    // 触发第二页（该响应被延迟 1500ms）
    await page.getByTestId("dataset-rows-next").click();
    // 立即切换到另一个数据集（条件变化 → 页码重置）
    await page.getByRole("button", { name: /合同数据集/ }).first().click();

    // 等到延迟响应到达之后，仍应展示当前数据集的第一页
    await page.waitForTimeout(2000);
    await expect(page.getByTestId("dataset-rows-page-indicator")).toHaveText("第 1 页");
    await expect(page.locator("tbody tr").first()).toContainText("ds-contract#0");
    await expect(page.locator("tbody tr").first()).not.toContainText("ds-bill");
  });
});
