/**
 * REQ-060 Slice 4: Playwright e2e 桌面端专属测试（仅 chromium-desktop project）。
 *
 * 覆盖：
 * - activeNav 高亮（home / knowledge / ai-chat）
 * - 详情父高亮（/resource/:id / /data/templates/:id / /ai-apps/:code）
 * - 桌面 sidebar 折叠/展开
 * - 主题切换（浅色/深色）via user menu toggle
 * - 截图验收（浅色/深色）
 */
import { test, expect } from "@playwright/test";
import { injectAuth } from "./fixtures";

test.describe("desktop: activeNav 高亮", () => {
  test("/ 总览高亮", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("总览");
  });

  test("/knowledge 知识库高亮", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/knowledge");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("知识库");
  });

  test("/ai-chat AI 问答高亮", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/ai-chat");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("AI 问答");
  });
});

test.describe("desktop: 详情父高亮 (activeNav)", () => {
  test("/resource/:id 高亮父 资源库", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/resource/abc");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("资源库");
  });

  test("/data/templates/:id 高亮父 数据要素模板", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/data/templates/42");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("数据要素模板");
  });

  test("/ai-apps/:code 高亮父 AI 应用广场", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/ai-apps/sample-app");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("AI 应用广场");
  });

  test("/database/:catalogCode 高亮父 数据库", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/database/electronics_info");
    await page.waitForLoadState("networkidle");
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active.first()).toContainText("数据库");
  });
});

test.describe("desktop: sidebar 折叠/展开", () => {
  test("点击折叠按钮 -> sidebar 变窄 + nav-label 隐藏", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // 初始展开
    await expect(page.locator(".nav-label").first()).toBeVisible();
    // 点击折叠
    await page.locator(".desktop-collapse-toggle").click();
    // nav-label 隐藏
    await expect(page.locator(".nav-label").first()).not.toBeVisible();
    // nav-item-collapsed class 生效
    await expect(page.locator(".nav-item-collapsed").first()).toBeVisible();
  });

  test("折叠态: aria-current 仍正确", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator(".desktop-collapse-toggle").click();
    const active = page.locator(".nav-item-active");
    await expect(active).toHaveCount(1);
    await expect(active).toHaveAttribute("aria-current", "page");
  });
});

test.describe("desktop: 主题切换", () => {
  test("通过 user menu 切换深色 -> 浅色", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // 默认浅色
    const theme1 = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme1).toBe("light");
    // 打开 user menu + 点击切换深色
    await page.locator('button[aria-label="管理员"]').click();
    await page.locator("text=切换深色").click();
    const theme2 = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme2).toBe("dark");
    // 再切回浅色
    await page.locator('button[aria-label="管理员"]').click();
    await page.locator("text=切换浅色").click();
    const theme3 = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme3).toBe("light");
  });
});

test.describe("desktop: 截图验收", () => {
  test("浅色主题 sidebar", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("desktop-light-sidebar.png", {
      maxDiffPixelRatio: 0.01,
      clip: { x: 0, y: 0, width: 200, height: 800 },
    });
  });

  test("深色主题 sidebar", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // 切换深色
    await page.evaluate(() => {
      localStorage.setItem("metaedu_theme", "dark");
    });
    await page.reload();
    await page.waitForLoadState("networkidle");
    const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme).toBe("dark");
    await expect(page).toHaveScreenshot("desktop-dark-sidebar.png", {
      maxDiffPixelRatio: 0.01,
      clip: { x: 0, y: 0, width: 200, height: 800 },
    });
  });
});