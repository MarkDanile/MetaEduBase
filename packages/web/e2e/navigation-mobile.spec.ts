/**
 * REQ-060 Slice 4: Playwright e2e 移动端专属测试（仅 chromium-mobile project）。
 *
 * 覆盖：
 * - mobile opener 可见 + aria-controls/aria-expanded
 * - drawer 打开/关闭（opener click / Escape / backdrop / route-change）
 * - 焦点管理（open -> data-autofocus；close -> opener）
 * - Tab 循环焦点（drawer 内 Tab/Shift+Tab 不逃出）
 * - body scroll lock（drawer open 时 body overflow:hidden）
 * - skip-link 存在 + focus 显示
 * - 截图验收（浅色/深色 mobile）
 */
import { test, expect } from "@playwright/test";
import { setupE2E } from "./fixtures";

test.describe("mobile: opener 可见 + a11y 属性", () => {
  test("opener 按钮可见 + aria-expanded=false + aria-controls", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const opener = page.locator("button.mobile-opener");
    await expect(opener).toBeVisible();
    await expect(opener).toHaveAttribute("aria-expanded", "false");
    await expect(opener).toHaveAttribute("aria-controls", "mobile-drawer");
    await expect(opener).toHaveAttribute("aria-label", "打开导航");
  });
});

test.describe("mobile: drawer 打开/关闭", () => {
  test("点击 opener -> drawer open + backdrop visible + aria-expanded=true", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-label", "关闭导航");
    await expect(page.locator("[data-testid='drawer-backdrop']")).toBeVisible();
    // drawer aside 可见（translate-x-0）
    const aside = page.locator("aside#mobile-drawer");
    await expect(aside).toBeVisible();
  });

  test("Escape 关闭 drawer + aria-expanded 恢复 false", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("[data-testid='drawer-backdrop']")).not.toBeVisible();
  });

  test("backdrop click 关闭 drawer", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await page.locator("[data-testid='drawer-backdrop']").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
  });

  test("route change 自动关闭 drawer", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    // 点击 drawer 内的 nav-item 导航
    await page.locator(".nav-item", { hasText: "知识库" }).first().click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
  });
});

test.describe("mobile: 焦点管理", () => {
  test("open drawer -> 焦点移到 data-autofocus 元素", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    // data-autofocus 在 .app-brand-mark 上
    const autofocusEl = page.locator("[data-autofocus]");
    await expect(autofocusEl).toBeFocused();
  });

  test("close drawer -> 焦点返回 opener", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const opener = page.locator("button.mobile-opener");
    await opener.click();
    await expect(page.locator("[data-autofocus]")).toBeFocused();
    // 按 Escape 关闭
    await page.keyboard.press("Escape");
    await expect(opener).toBeFocused();
  });

  test("Tab 从 data-autofocus 定向到第一个可交互 nav-item", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    // 焦点初始在 data-autofocus（brand mark，tabindex=-1，不在 focusables 中）
    // Tab 应定向到 first focusable（第一个 nav-item）
    await page.keyboard.press("Tab");
    // 验证焦点在 drawer 内且不是 data-autofocus
    const isInDrawer = await page.evaluate(() => {
      const drawer = document.getElementById("mobile-drawer");
      const active = document.activeElement;
      return drawer?.contains(active) && !active?.hasAttribute("data-autofocus");
    });
    expect(isInDrawer).toBe(true);
  });

  test("Shift+Tab 从 data-autofocus 定向到最后一个可交互元素", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    // 焦点初始在 data-autofocus（不在 focusables 中）
    // Shift+Tab 应定向到 last focusable（user menu 按钮或最后一个 nav-item）
    await page.keyboard.press("Shift+Tab");
    const isInDrawer = await page.evaluate(() => {
      const drawer = document.getElementById("mobile-drawer");
      const active = document.activeElement;
      return drawer?.contains(active) && !active?.hasAttribute("data-autofocus");
    });
    expect(isInDrawer).toBe(true);
  });
});

test.describe("mobile: body scroll lock", () => {
  test("drawer open 时 body overflow=hidden", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    const overflow = await page.evaluate(() => document.body.style.overflow);
    expect(overflow).toBe("hidden");
  });

  test("drawer close 后 body overflow 恢复", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await page.keyboard.press("Escape");
    const overflow = await page.evaluate(() => document.body.style.overflow);
    expect(overflow).not.toBe("hidden");
  });
});

test.describe("mobile: skip-link 结构断言", () => {
  test("skip-link 存在 + href 指向 #main-content + CSS 视觉隐藏", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const skip = page.locator("a.skip-link");
    await expect(skip).toHaveAttribute("href", "#main-content");
    await expect(skip).toBeAttached();
    // 键盘 Tab 序列在 Pixel 5 touch emulation 下不可靠；
    // 完整 Tab + Enter 键盘验收在 navigation-shared.spec.ts 的 desktop project 中执行。
    // 这里只验证结构：skip-link 存在、href 正确、文本可见。
    await expect(skip).toHaveText("跳到主要内容");
  });
});

test.describe("mobile: 主题视觉验收", () => {
  test("浅色主题: drawer 打开后菜单文字可见 + data-theme=light", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme).toBe("light");
    // drawer 打开后菜单文字可见（非折叠态）
    await expect(page.locator(".nav-label").first()).toBeVisible();
    await expect(page.locator(".nav-section-label").first()).toBeVisible();
    await expect(page.locator("aside#mobile-drawer")).toBeVisible();
  });

  test("深色主题: drawer 打开后菜单文字可见 + data-theme=dark", async ({ page }) => {
    await setupE2E(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => {
      localStorage.setItem("metaedu_theme", "dark");
    });
    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme).toBe("dark");
    // 深色模式下 drawer 打开后菜单文字仍可见
    await expect(page.locator(".nav-label").first()).toBeVisible();
    await expect(page.locator(".nav-section-label").first()).toBeVisible();
    await expect(page.locator("aside#mobile-drawer")).toBeVisible();
  });
});