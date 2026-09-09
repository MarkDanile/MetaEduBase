/**
 * REQ-042 WS-S1: Workspace 移动端 e2e（仅 chromium-mobile project，Pixel 5）。
 *
 * 覆盖（REQ-042 窄屏 Tab 约定）：
 * - 面板切换条可见，默认会话面板
 * - 选中会话 -> 自动切到消息面板（默认派生运行不顶到运行页）
 * - composer 发送禁用
 * - 显式点击「运行详情」-> 切到运行面板
 */
import { test, expect } from "@playwright/test";
import { setupWorkspaceE2E } from "./fixtures";

test.describe("mobile: workspace 单面板 + Tab 切换", () => {
  test("默认会话面板 + 面板切换条可见", async ({ page }) => {
    await setupWorkspaceE2E(page, "teacher");
    await page.goto("/agent-workspace");
    await page.waitForLoadState("networkidle");
    // 面板切换条三个 tab 可见
    await expect(page.locator('[data-testid="ws-mobile-tab-conversations"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-mobile-tab-messages"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-mobile-tab-run"]')).toBeVisible();
    // 默认会话面板：列表可见，中栏空态不出现（未选中）
    await expect(page.locator('[data-testid="ws-conv-conv-1"]')).toBeVisible();
  });

  test("选中会话 -> 切到消息面板；发送禁用；显式点运行 -> 切运行面板", async ({ page }) => {
    await setupWorkspaceE2E(page, "teacher");
    await page.goto("/agent-workspace");
    await page.waitForLoadState("networkidle");

    // 选中会话 -> 切到消息面板
    await page.locator('[data-testid="ws-conv-conv-1"]').click();
    await expect(page.locator('[data-testid="ws-msg-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-msg-1"]')).toContainText("帮我分析这份数据");
    // 发送按钮禁用
    await expect(page.locator('[data-testid="ws-send-btn"]')).toBeDisabled();
    // 消息面板为当前激活 tab（未被默认派生运行顶到运行页）
    await expect(page.locator('[data-testid="ws-mobile-tab-messages"]')).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // 显式点击「运行详情」-> 切到运行面板
    await page.locator('[data-testid="ws-run-link-2"]').click();
    await expect(page.locator('[data-testid="ws-run-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-run-status"]')).toHaveText("已完成");
    await expect(page.locator('[data-testid="ws-mobile-tab-run"]')).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
