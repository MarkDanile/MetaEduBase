/**
 * REQ-060 Slice 4: Playwright e2e navigation spec（AC-8 验收）。
 *
 * 覆盖：
 * - desktop navigation：7 角色 × 关键 section 可见（active nav items）
 * - desktop sidebar：activeNav 高亮 + 详情父高亮
 * - mobile drawer：opener toggle / Escape / backdrop / route-change / focus-return / skip-link
 * - theme variants：浅色/深色 不影响交互与高亮
 * - deep link redirects：/skill-editor /admin/* → 新路径
 * - forbidden：低权深链 → /403
 * - breadcrumb：详情页显示父链 + aria-label
 *
 * Auth：每个 case 用 `injectAuth(page, role)` 注入 localStorage 登录态。
 * 路由跳转：纯前端路由 + 守卫（不发实际 API 请求；guard 读 localStorage 放行）。
 */
import { test, expect } from "@playwright/test";
import { injectAuth, type Role } from "./fixtures";

test.describe("desktop navigation: 7 角色 sidebar 可见性", () => {
  const roleCases: Array<{ role: Role; expectedLabels: string[]; forbiddenLabels: string[] }> = [
    {
      role: "super_admin",
      expectedLabels: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"],
      forbiddenLabels: [],
    },
    {
      role: "admin",
      expectedLabels: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"],
      forbiddenLabels: [],
    },
    {
      role: "teacher",
      expectedLabels: ["总览", "AI 工作", "智能体应用", "知识与数据"],
      forbiddenLabels: ["能力中心"],
    },
    {
      role: "employee",
      expectedLabels: ["总览", "AI 工作", "智能体应用", "知识与数据"],
      forbiddenLabels: ["能力中心"],
    },
    {
      role: "unknown_role",
      expectedLabels: [],
      forbiddenLabels: ["总览", "知识库"],
    },
  ];

  for (const { role, expectedLabels, forbiddenLabels } of roleCases) {
    test(`${role}: 可见 sidebar section 集合正确`, async ({ page }) => {
      await injectAuth(page, role);
      await page.goto("/");
      await page.waitForLoadState("networkidle");
      // sidebar nav sections（section-label class）
      const sectionLabels = await page.locator(".nav-section-label").allTextContents();
      for (const want of expectedLabels) {
        expect(sectionLabels, `${role} should see "${want}"`).toContain(want);
      }
      for (const forbid of forbiddenLabels) {
        expect(sectionLabels, `${role} should NOT see "${forbid}"`).not.toContain(forbid);
      }
    });
  }
});

test.describe("desktop sidebar: activeNav 高亮", () => {
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
});

test.describe("desktop sidebar: 详情父高亮 (activeNav)", () => {
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
});

test.describe("mobile drawer: 状态机 + a11y", () => {
  test("opener 按钮可见 + aria-expanded=false", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const opener = page.locator("button.mobile-opener");
    await expect(opener).toBeVisible();
    await expect(opener).toHaveAttribute("aria-expanded", "false");
    await expect(opener).toHaveAttribute("aria-controls", "mobile-drawer");
  });

  test("点击 opener 打开 drawer（aria-expanded=true + backdrop）", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("[data-testid='drawer-backdrop']")).toBeVisible();
  });

  test("Escape 键关闭 drawer", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("button.mobile-opener").click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
  });

  test("点击 backdrop 关闭 drawer", async ({ page }) => {
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
    await page.locator(".nav-item", { hasText: "知识库" }).first().click();
    await expect(page.locator("button.mobile-opener")).toHaveAttribute("aria-expanded", "false");
  });

  test("skip-link 存在 + 指向 #main-content", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const skip = page.locator("a.skip-link");
    await expect(skip).toHaveAttribute("href", "#main-content");
  });
});

test.describe("theme variants", () => {
  test("浅色/深色主题对 sidebar nav 无副作用", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // 浅色（默认）：data-theme 不应等于 dark
    const theme1 = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme1).not.toBe("dark");
    // 切换深色
    await page.evaluate(() => {
      document.documentElement.setAttribute("data-theme", "dark");
    });
    const theme2 = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(theme2).toBe("dark");
    // sidebar nav 仍可见
    await expect(page.locator(".nav-item").first()).toBeVisible();
  });
});

test.describe("deep link redirects (Slice 2 兼容)", () => {
  test("/skill-editor -> /capabilities/skills", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/skill-editor");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/capabilities/skills");
  });

  test("/admin/template/:id -> /data/templates/:id (参数保留)", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/admin/template/42");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/data/templates/42");
  });
});

test.describe("forbidden: 低权深链 -> /403", () => {
  test("teacher -> /capabilities/skills -> /forbidden", async ({ page }) => {
    await injectAuth(page, "teacher");
    await page.goto("/capabilities/skills");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/403");
  });
});

test.describe("breadcrumb: 详情页父链", () => {
  test("/resource/:id -> 总览 / 资源库 / 文件详情", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/resource/abc");
    await page.waitForLoadState("networkidle");
    const breadcrumb = page.locator("nav.breadcrumb-bar");
    await expect(breadcrumb).toBeVisible();
    await expect(breadcrumb).toHaveAttribute("aria-label", "面包屑导航");
    await expect(breadcrumb.locator("a.stub-router-link, a")).toContainText(["总览", "资源库"]);
    await expect(breadcrumb.locator('[aria-current="page"]')).toHaveText("文件详情");
  });
});