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

// ---------------------------------------------------------------------------
// REQ-042 WS-S1: Workspace 只读三栏 shell e2e fixtures（mock 仅用于 UI 验证，
// 不作为生产能力证据；DTO 形状镜像后端 agent_workspace / agent_execution 契约）。
// ---------------------------------------------------------------------------

const WS_TS = "2026-09-09T10:00:00Z";

const WS_CONV_1 = {
  id: "conv-1",
  title: "产品方案讨论",
  title_source: "user",
  state: "active",
  parent_conversation_id: null,
  forked_from_message_id: null,
  last_activity_at: WS_TS,
  pinned_at: null,
  revision: 1,
  created_at: "2026-09-09T09:00:00Z",
  updated_at: WS_TS,
};

const WS_CONV_2 = {
  id: "conv-2",
  title: "数据分析问题",
  title_source: "auto",
  state: "active",
  parent_conversation_id: null,
  forked_from_message_id: null,
  last_activity_at: "2026-09-08T10:00:00Z",
  pinned_at: "2026-09-08T11:00:00Z",
  revision: 2,
  created_at: "2026-09-08T09:00:00Z",
  updated_at: "2026-09-08T10:00:00Z",
};

const WS_CONVERSATIONS = { items: [WS_CONV_1, WS_CONV_2], next_cursor: null };

const WS_MESSAGES = {
  items: [
    {
      id: "m-1",
      seq: 1,
      kind: "user_input",
      author_type: "user",
      author_id: "u-1",
      requested_run_id: "run-1",
      requested_run_queue_seq: 1,
      dispatch_state: null,
      origin_run_id: null,
      output_ordinal: null,
      reply_to_message_id: null,
      content_state: "visible",
      created_at: WS_TS,
      parts: [
        {
          id: "p-1",
          part_seq: 1,
          type: "text",
          text: "帮我分析这份数据",
          format: null,
          resource_id: null,
          media_type: null,
          display_name: null,
          classification: "internal",
        },
      ],
    },
    {
      id: "m-2",
      seq: 2,
      kind: "assistant_output",
      author_type: "agent",
      author_id: null,
      requested_run_id: null,
      requested_run_queue_seq: null,
      dispatch_state: null,
      origin_run_id: "run-1",
      output_ordinal: 1,
      reply_to_message_id: null,
      content_state: "visible",
      created_at: "2026-09-09T10:00:05Z",
      parts: [
        {
          id: "p-2",
          part_seq: 1,
          type: "text",
          text: "这是分析结果。",
          format: null,
          resource_id: null,
          media_type: null,
          display_name: null,
          classification: "internal",
        },
      ],
    },
  ],
  has_more: false,
};

const WS_RUN = {
  id: "run-1",
  conversation_id: "conv-1",
  queue_seq: 1,
  root_input_message_id: "m-1",
  parent_run_id: null,
  agent_definition_version_id: "adv-1",
  runtime_profile_id: "rp-1",
  runtime_binding_id: null,
  status: "completed",
  status_revision: 3,
  first_available_event_seq: 1,
  last_event_seq: 5,
  event_log_complete: true,
  queued_at: WS_TS,
  started_at: "2026-09-09T10:00:01Z",
  ended_at: "2026-09-09T10:00:05Z",
  terminal_code: "ok",
  terminal_reason: null,
  terminal_result_digest: null,
  terminal_output_digest: null,
  terminal_output_size: null,
  terminal_output_media_type: null,
  terminal_output_classification: null,
  terminal_message_id: "m-2",
  output_publish_state: "published",
  usage: { input_tokens: 120, output_tokens: 340 },
  pending_input_request_count: 0,
  pending_approval_count: 0,
  created_at: WS_TS,
  updated_at: "2026-09-09T10:00:05Z",
};

/**
 * 安装 Workspace 专属 mocks（在 installApiMocks 之后注册，特定路径优先于通配符）。
 */
export async function installWorkspaceMocks(page: Page): Promise<void> {
  await page.route("**/api/v1/agent-workspace/**", async (route: Route) => {
    const method = route.request().method();
    const path = new URL(route.request().url()).pathname;
    if (method === "GET" && /\/conversations\/[^/]+\/messages$/.test(path)) {
      await route.fulfill({ json: WS_MESSAGES });
      return;
    }
    if (method === "GET" && /\/conversations\/[^/]+$/.test(path)) {
      await route.fulfill({ json: WS_CONV_1 });
      return;
    }
    if (method === "GET" && /\/conversations$/.test(path)) {
      await route.fulfill({ json: WS_CONVERSATIONS });
      return;
    }
    if (method === "POST" && /\/conversations$/.test(path)) {
      await route.fulfill({ json: { ...WS_CONV_1, id: "conv-new", title: null, title_source: "none" } });
      return;
    }
    // 其它写操作（rename/pin/archive/restore/delete）-> 回话单对象
    await route.fulfill({ json: WS_CONV_1 });
  });
  await page.route("**/api/v1/agent-runs/**", async (route: Route) => {
    await route.fulfill({ json: WS_RUN });
  });
}

/**
 * Workspace 一站式 setup：登录态 + agent_workspace feature flag 开启 + 通用 mocks + Workspace mocks。
 * （flag 默认 fail-closed，必须显式开启才能通过路由 guard。）
 */
export async function setupWorkspaceE2E(page: Page, role: Role): Promise<void> {
  await injectAuth(page, role);
  await page.addInitScript(() => {
    localStorage.setItem("metaedu_feature_agent_workspace", "true");
  });
  await installApiMocks(page);
  await installWorkspaceMocks(page);
}