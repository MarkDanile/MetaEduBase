/**
 * REQ-060 Slice 4: Playwright e2e 共享 fixtures。
 *
 * - injectAuth: 注入登录态（metaedu_token / metaedu_role / metaedu_tenant_id），
 *   跳过实际登录步骤以避免后端依赖；路由 guard 读 localStorage 直接放行
 * - switchRole: 在 case 内动态切换 role（无需 reload）—— 仅影响导航可见性，
 *   不触发路由变化
 */
import type { Page } from "@playwright/test";

export type Role =
  | "super_admin"
  | "data_admin"
  | "admin"
  | "leader"
  | "teacher"
  | "employee"
  | "student"
  | "unknown_role";

export interface AuthFixture {
  page: Page;
  role: Role;
}

/**
 * 注入登录态到 localStorage，然后 goto /（home）。
 * 注意：必须在 page.goto 之前调用（goto 触发 router.beforeEach 读 localStorage）。
 */
export async function injectAuth(page: Page, role: Role): Promise<void> {
  await page.addInitScript((r: Role) => {
    localStorage.setItem("metaedu_token", "fake-token-for-e2e");
    localStorage.setItem("metaedu_tenant_id", "t-e2e");
    localStorage.setItem("metaedu_role", r);
  }, role);
}

/**
 * 在已加载页面内切换 role（用于测试 sidebar 过滤）：
 * - 重置 token / tenant_id（保持已登录态）
 * - 刷新页面让 router + nav.ts 重新读取 role
 */
export async function switchRole(page: Page, role: Role): Promise<void> {
  await page.evaluate((r: Role) => {
    localStorage.setItem("metaedu_role", r);
  }, role);
  await page.reload();
  await page.waitForLoadState("networkidle");
}