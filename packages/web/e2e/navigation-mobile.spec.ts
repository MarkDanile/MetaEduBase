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
import { injectAuth } from "./fixtures";

test.describe("mobile: opener 可见 + a11y 属性", () => {
  test("opener 按钮可见 + aria-expanded=false + aria-controls", async ({ page }) => {
    await injectAuth(page, "admin");
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
    await injectAuth(page, "admin");
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
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("[data-testid='drawer-backdrop']")).not.toBeVisible();
  });

  test("backdrop click 关闭 drawer", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await page.locator("[data-testid='drawer-backdrop']").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
  });

  test("route change 自动关闭 drawer", async ({ page }) => {
    await injectAuth(page, "admin");
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
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    // data-autofocus 在 .app-brand-mark 上
    const autofocusEl = page.locator("[data-autofocus]");
    await expect(autofocusEl).toBeFocused();
  });

  test("close drawer -> 焦点返回 opener", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const opener = page.locator("button.mobile-opener");
    await opener.click();
    await expect(page.locator("[data-autofocus]")).toBeFocused();
    // 按 Escape 关闭
    await page.keyboard.press("Escape");
    await expect(opener).toBeFocused();
  });

  test("Tab 循环焦点不逃出 drawer", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    // 焦点初始在 data-autofocus（brand mark）
    // 按 Tab 多次，焦点应始终在 drawer 内
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
    }
    const isInDrawer = await page.evaluate(() => {
      const drawer = document.getElementById("mobile-drawer");
      const active = document.activeElement;
      return drawer?.contains(active);
    });
    expect(isInDrawer).toBe(true);
  });

  test("Shift+Tab 循环焦点不逃出 drawer", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Shift+Tab");
    }
    const isInDrawer = await page.evaluate(() => {
      const drawer = document.getElementById("mobile-drawer");
      const active = document.activeElement;
      return drawer?.contains(active);
    });
    expect(isInDrawer).toBe(true);
  });
});

test.describe("mobile: body scroll lock", () => {
  test("drawer open 时 body overflow=hidden", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    const overflow = await page.evaluate(() => document.body.style.overflow);
    expect(overflow).toBe("hidden");
  });

  test("drawer close 后 body overflow 恢复", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await page.keyboard.press("Escape");
    const overflow = await page.evaluate(() => document.body.style.overflow);
    expect(overflow).not.toBe("hidden");
  });
});

test.describe("mobile: skip-link", () => {
  test("skip-link 存在 + Tab focus 时显示", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const skip = page.locator("a.skip-link");
    await expect(skip).toHaveAttribute("href", "#main-content");
    // Tab 到 skip-link（它是 DOM 第一个可聚焦元素）
    await page.keyboard.press("Tab");
    await expect(skip).toBeFocused();
  });
});

test.describe("mobile: 截图验收", () => {
  test("浅色主题 mobile drawer", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page).toHaveScreenshot("mobile-light-drawer.png", {
      maxDiffPixelRatio: 0.01,
      clip: { x: 0, y: 0, width: 288, height: 600 },
    });
  });

  test("深色主题 mobile drawer", async ({ page }) => {
    await injectAuth(page, "admin");
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
    await expect(page).toHaveScreenshot("mobile-dark-drawer.png", {
      maxDiffPixelRatio: 0.01,
      clip: { x: 0, y: 0, width: 288, height: 600 },
    });
  });
});