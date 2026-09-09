/**
 * REQ-042 WS-S1: Workspace 桌面端 e2e（仅 chromium-desktop project，1280×800）。
 *
 * 覆盖：
 * - 三栏同屏（会话列表 / 消息时间线 / 运行详情）
 * - 深链 ?c=conv-1 durable read：标题 + 真实 Message + 自动派生运行终态
 * - activeNav 高亮「工作区」
 * - 无横向溢出（三栏 grid + minmax(0,1fr)）
 */
import { test, expect } from "@playwright/test";
import { setupWorkspaceE2E } from "./fixtures";

test.describe("desktop: workspace 三栏布局", () => {
  test("深链 ?c=conv-1 -> 三栏同屏 + durable read + 运行终态", async ({ page }) => {
    await setupWorkspaceE2E(page, "admin");
    await page.goto("/agent-workspace?c=conv-1");
    await page.waitForLoadState("networkidle");

    // 左栏：会话列表
    await expect(page.locator('[data-testid="ws-conv-conv-1"]')).toBeVisible();
    // 中栏：标题 + 真实消息
    await expect(page.locator('[data-testid="ws-conv-heading"]')).toHaveText("产品方案讨论");
    await expect(page.locator('[data-testid="ws-msg-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-msg-2"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-msg-1"]')).toContainText("帮我分析这份数据");
    // 右栏：自动派生最新运行 -> 终态事实
    await expect(page.locator('[data-testid="ws-run-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-run-status"]')).toHaveText("已完成");
    await expect(page.locator('[data-testid="ws-run-id"]')).toHaveText("run-1");
    // composer 发送禁用（明确非提交）
    await expect(page.locator('[data-testid="ws-send-btn"]')).toBeDisabled();
  });

  test("三栏 grid 无横向溢出", async ({ page }) => {
    await setupWorkspaceE2E(page, "admin");
    await page.goto("/agent-workspace?c=conv-1");
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("/agent-workspace activeNav 高亮「工作区」", async ({ page }) => {
    await setupWorkspaceE2E(page, "admin");
    await page.goto("/agent-workspace");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("工作区");
  });
});
