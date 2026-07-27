/**
 * REQ-060 Slice 4: Playwright e2e 共享 fixtures。
 *
 * - injectAuth: 注入登录态（metaedu_token / metaedu_role / metaedu_tenant_id），
 *   跳过实际登录步骤以避免后端依赖
 * - installApiMocks: 拦截 `/api/v1/*` 请求返回确定性 mock，防 ECONNREFUSED
 *   导致页面组件回退到列表页或错误状态
 */
import type { Page, Route } from "@playwright/test";

export type Role =
  | "super_admin"
  | "data_admin"
  | "admin"
  | "leader"
  | "teacher"
  | "employee"
  | "student";

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
 * 安装 API route mocks：拦截所有 `/api/v1/*` 请求返回确定性响应。
 *
 * 导航测试只验证路由跳转、sidebar 高亮、drawer 行为，不验证后端数据。
 * 没有 mock 时页面组件因 ECONNREFUSED 会回退或报错，改变 URL 和 DOM。
 *
 * mock 策略：
 * - GET list 端点 -> 空列表 / { results: [], total: 0 }
 * - GET detail 端点 -> 最小对象（含 id 字段）
 * - POST/PUT/DELETE -> { ok: true }
 * - 其它 -> {}
 */
export async function installApiMocks(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route: Route) => {
    const method = route.request().method();
    const url = route.request().url();
    const path = new URL(url).pathname;

    // 列表端点：返回空列表
    if (method === "GET") {
      // 知识节点
      if (path.includes("/knowledge/nodes")) {
        await route.fulfill({ json: { results: [], total: 0 } });
        return;
      }
      // 资源
      if (path.includes("/resources")) {
        await route.fulfill({ json: { results: [], total: 0 } });
        return;
      }
      // 模板列表 / lookup
      if (path.match(/\/templates(\/|$|\?)/) && !path.match(/\/templates\/[^/]+$/)) {
        await route.fulfill({ json: [] });
        return;
      }
      if (path.includes("/templates/lookup")) {
        await route.fulfill({ json: [] });
        return;
      }
      // 模板详情
      if (path.match(/\/templates\/[^/]+$/)) {
        const id = path.split("/").pop() ?? "1";
        await route.fulfill({
          json: {
            id,
            name: "测试模板",
            doc_types: [],
            fields: [],
            ai_prompt: null,
            ai_context: null,
            source_file_id: null,
            created_at: "2026-01-01T00:00:00",
            updated_at: "2026-01-01T00:00:00",
            schema_version: 1,
            is_deprecated: false,
            deprecated_at: null,
            deprecated_reason: null,
          },
        });
        return;
      }
      // 数据集
      if (path.includes("/datasets")) {
        await route.fulfill({ json: [] });
        return;
      }
      // catalog
      if (path.includes("/catalogs")) {
        await route.fulfill({ json: [] });
        return;
      }
      // AI 应用
      if (path.includes("/ai-apps")) {
        await route.fulfill({ json: [] });
        return;
      }
      // skills
      if (path.includes("/skills")) {
        await route.fulfill({ json: [] });
        return;
      }
      // mcp servers
      if (path.includes("/mcp")) {
        await route.fulfill({ json: [] });
        return;
      }
      // 文件详情
      if (path.includes("/files/")) {
        await route.fulfill({ json: { id: "abc", title: "测试文件" } });
        return;
      }
    }

    // 默认：GET -> {}，POST/PUT/DELETE -> { ok: true }
    if (method === "GET") {
      await route.fulfill({ json: {} });
    } else {
      await route.fulfill({ json: { ok: true } });
    }
  });
}

/**
 * 一站式 setup：注入登录态 + 安装 API mocks。
 * 每个 e2e case 应在 page.goto 之前调用此函数。
 */
export async function setupE2E(page: Page, role: Role): Promise<void> {
  await injectAuth(page, role);
  await installApiMocks(page);
}