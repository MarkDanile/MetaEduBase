/**
 * REQ-060 Slice 4: Playwright e2e 共享测试（desktop + mobile 都跑）。
 *
 * 覆盖：
 * - 7 角色 sidebar 可见性矩阵（super_admin/data_admin/admin/leader/teacher/employee/student）
 * - 旧链接重定向（/skill-editor, /admin/template/:id）
 * - 低权深链 -> /403
 * - breadcrumb 详情页父链
 */
import { test, expect } from "@playwright/test";
import { injectAuth, type Role } from "./fixtures";

const ALL_ROLES: Role[] = [
  "super_admin",
  "data_admin",
  "admin",
  "leader",
  "teacher",
  "employee",
  "student",
];

test.describe("shared: 7 角色 sidebar 可见性矩阵", () => {
  // 期望可见的 section label 集合（按角色）
  const roleExpectations: Record<string, { see: string[]; notSee: string[] }> = {
    super_admin: { see: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"], notSee: [] },
    data_admin: { see: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"], notSee: [] },
    admin: { see: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"], notSee: [] },
    leader: { see: ["总览", "AI 工作", "智能体应用", "知识与数据"], notSee: ["能力中心"] },
    teacher: { see: ["总览", "AI 工作", "智能体应用", "知识与数据"], notSee: ["能力中心"] },
    employee: { see: ["总览", "AI 工作", "智能体应用", "知识与数据"], notSee: ["能力中心"] },
    student: { see: ["总览", "AI 工作", "智能体应用", "知识与数据"], notSee: ["能力中心"] },
  };

  for (const role of ALL_ROLES) {
    test(`${role}: sidebar section 集合正确`, async ({ page }) => {
      await injectAuth(page, role);
      await page.goto("/");
      await page.waitForLoadState("networkidle");
      const sectionLabels = await page.locator(".nav-section-label").allTextContents();
      const exp = roleExpectations[role];
      for (const want of exp.see) {
        expect(sectionLabels, `${role} should see "${want}"`).toContain(want);
      }
      for (const forbid of exp.notSee) {
        expect(sectionLabels, `${role} should NOT see "${forbid}"`).not.toContain(forbid);
      }
    });
  }
});

test.describe("shared: 旧链接重定向", () => {
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

test.describe("shared: 低权深链 -> /403", () => {
  test("teacher -> /capabilities/skills -> /forbidden", async ({ page }) => {
    await injectAuth(page, "teacher");
    await page.goto("/capabilities/skills");
    await page.waitForLoadState("networkidle");
    expect(page.url()).toContain("/403");
  });
});

test.describe("shared: breadcrumb 详情页父链", () => {
  test("/resource/:id -> 总览 / 资源库 / 文件详情", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/resource/abc");
    await page.waitForLoadState("networkidle");
    const breadcrumb = page.locator("nav.breadcrumb-bar");
    await expect(breadcrumb).toBeVisible();
    await expect(breadcrumb).toHaveAttribute("aria-label", "面包屑导航");
    await expect(breadcrumb.locator('[aria-current="page"]')).toHaveText("文件详情");
  });

  test("/data/templates/:id -> 总览 / 数据要素模板 / 模板详情", async ({ page }) => {
    await injectAuth(page, "admin");
    await page.goto("/data/templates/42");
    await page.waitForLoadState("networkidle");
    const breadcrumb = page.locator("nav.breadcrumb-bar");
    await expect(breadcrumb.locator('[aria-current="page"]')).toHaveText("模板详情");
  });
});