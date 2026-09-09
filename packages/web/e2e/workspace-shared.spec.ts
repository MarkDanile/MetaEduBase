/**
 * REQ-042 WS-S1: Workspace 共享 e2e（desktop + mobile 都跑）。
 *
 * 覆盖：
 * - feature flag 关闭 -> /agent-workspace 深链 fail-closed 到 /403
 * - feature flag 开启 -> 三栏 shell 挂载、会话列表渲染（mock 仅用于 UI 验证）
 */
import { test, expect } from "@playwright/test";
import { setupE2E, setupWorkspaceE2E } from "./fixtures";

test.describe("shared: workspace feature flag 门控", () => {
  test("flag 关闭 -> /agent-workspace -> /403", async ({ page }) => {
    // setupE2E 不设 agent_workspace flag（fail-closed）
    await setupE2E(page, "admin");
    await page.goto("/agent-workspace");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/403");
  });

  test("flag 开启 -> shell 挂载并渲染会话列表", async ({ page }) => {
    await setupWorkspaceE2E(page, "teacher");
    await page.goto("/agent-workspace");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/agent-workspace");
    await expect(page.locator('[data-testid="agent-workspace"]')).toBeVisible();
    // 会话列表渲染（移动端默认 conversations 面板可见；桌面左栏可见）
    await expect(page.locator('[data-testid="ws-conv-conv-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="ws-conv-conv-2"]')).toBeVisible();
  });
});
