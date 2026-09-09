/**
 * REQ-042 WS-S1: Workspace 共享 e2e（desktop + mobile 都跑）。
 *
 * 覆盖：
 * - feature flag 关闭 -> /agent-workspace 深链 fail-closed 到 /403
 * - feature flag 开启 -> 三栏 shell 挂载、会话列表渲染（mock 仅用于 UI 验证）
 * - restore 失败 mock UI contract：409 + conversation_restore_not_allowed -> 错误透传 + 不冒充成功
 *
 * ⚠ restore mock E2E 仅验证前端 UI/store 契约，**不是真实 PG restore 正向路径验证**。
 *   - 后端真实 fail-closed 由 packages/server-python/tests/.../test_restore_recovery.py
 *     （260/275/305/333：ConversationRestoreNotAllowedError 反例）覆盖；
 *   - 真实正向 restore 需要完整六-owner baseline fence（由 agent_erasure_backfill 准备），
 *     该 fixture 准备不属于 WS-S1（本 Slice 仅含 UI/API wiring）。
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

test.describe("shared: restore mock UI contract（非真实 PG 正向路径）", () => {
  /**
   * 后端 restore 真实 PG 行为：fail-closed 当 fence ledger 不完整（缺少任何 owner 的 active fence）。
   * 真实正向 restore 需先经 agent_erasure_backfill 建立完整六-owner baseline fence。
   * 本测试只验证前端契约：
   *  1. 点击「恢复」发出 POST /conversations/{id}/restore 并带 If-Match header
   *  2. 后端 409 + conversation_restore_not_allowed 错误透传到 toast
   *  3. 不显示"已恢复"成功 toast（不冒充成功）
   *  4. 按钮 in-flight 状态复位（再次可点）
   *  5. 不触发 submit-turn / SSE / /ai/chat/evidence 请求
   *
   * 真实浏览器手动验收中"新建会话 → archive → restore 返回 409"是预期 fail-closed，
   * 不是前端缺陷。完整正向路径验证需先准备 backfill fixture（不在 WS-S1 scope）。
   */
  test("restore 失败 (409 fence ledger incomplete) -> 真实错误展示 + 不显示成功", async ({ page }) => {
    await setupWorkspaceE2E(page, "admin");

    // 监听所有可疑请求：submit-turn / SSE / /ai/chat/evidence
    const suspiciousRequests: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (
        url.includes("/turns") ||
        url.includes("/ai/chat") ||
        url.includes("/ai/chat/evidence") ||
        url.includes("/events") ||
        url.includes("event-stream")
      ) {
        suspiciousRequests.push(`${req.method()} ${url}`);
      }
    });

    // 等待 restore 请求 promise（必须在 click 之前注册，否则可能错过）
    const restoreRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "POST" &&
        /\/api\/v1\/agent-workspace\/conversations\/[^/]+\/restore$/.test(req.url()),
      { timeout: 10_000 },
    );

    // 覆盖：archived conversation + restore 409 mock
    //   - 后注册的 handler 优先匹配；其它路径 fallback 到 setupWorkspaceE2E 的 workspace mock。
    await page.route("**/api/v1/agent-workspace/**", async (route) => {
      const method = route.request().method();
      const path = new URL(route.request().url()).pathname;

      // POST /conversations/{id}/restore -> 409 fail-closed（模拟缺五 owner fence）
      if (method === "POST" && /\/conversations\/[^/]+\/restore$/.test(path)) {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            detail: {
              code: "conversation_restore_not_allowed",
              message:
                "conversation erasure fence ledger is incomplete; missing owners: " +
                "['execution.core.v1', 'execution.transport.v1', 'external.payload.v1', " +
                "'runtime.private.v1', 'workspace.transport.v1']",
            },
          }),
        });
        return;
      }

      // GET /conversations/{id} -> archived（让恢复按钮 v-if 显示）
      if (method === "GET" && /\/conversations\/[^/]+$/.test(path)) {
        await route.fulfill({
          json: {
            id: "conv-1",
            title: "产品方案讨论",
            title_source: "user",
            state: "archived",
            parent_conversation_id: null,
            forked_from_message_id: null,
            last_activity_at: "2026-09-09T10:00:00Z",
            pinned_at: null,
            revision: 5,
            created_at: "2026-09-09T09:00:00Z",
            updated_at: "2026-09-09T10:00:00Z",
          },
        });
        return;
      }

      // GET /conversations (list) -> archived single（避免 active 默认派生 run）
      if (method === "GET" && /\/conversations$/.test(path)) {
        await route.fulfill({
          json: {
            items: [
              {
                id: "conv-1",
                title: "产品方案讨论",
                title_source: "user",
                state: "archived",
                parent_conversation_id: null,
                forked_from_message_id: null,
                last_activity_at: "2026-09-09T10:00:00Z",
                pinned_at: null,
                revision: 5,
                created_at: "2026-09-09T09:00:00Z",
                updated_at: "2026-09-09T10:00:00Z",
              },
            ],
            next_cursor: null,
          },
        });
        return;
      }

      // 其它路径 -> 让原 workspace mock 处理
      await route.fallback();
    });

    await page.goto("/agent-workspace?c=conv-1");
    await page.waitForLoadState("networkidle");

    // 移动端：selectedId watcher 触发时 isMobile 仍为 false（handleResize 在 onMounted 后
    // 才设 isMobile），不会自动切到消息面板。显式点击消息 tab（桌面端 md:hidden，
    // isVisible()=false，no-op）。
    const messagesTab = page.locator('[data-testid="ws-mobile-tab-messages"]');
    if (await messagesTab.isVisible()) {
      await messagesTab.click();
    }

    // 恢复按钮可见（v-if state==='archived'）
    const restoreBtn = page.locator('[data-testid="ws-restore-btn"]');
    await expect(restoreBtn).toBeVisible();

    // 点击恢复
    await restoreBtn.click();

    // 1) 校验请求：endpoint + method + If-Match
    const restoreReq = await restoreRequestPromise;
    expect(restoreReq.method()).toBe("POST");
    expect(restoreReq.url()).toMatch(/\/conversations\/conv-1\/restore$/);
    expect(restoreReq.headers()["if-match"]).toBeTruthy();

    // 2) toast 显示后端真实错误（不冒充成功）
    const errorToast = page.locator(".toast-item.toast-error");
    await expect(errorToast).toBeVisible({ timeout: 5_000 });
    await expect(errorToast).toContainText("conversation erasure fence ledger is incomplete");

    // 3) 不显示"已恢复"成功 toast
    const successTexts = await page.locator(".toast-item.toast-success").allInnerTexts();
    expect(successTexts.find((t) => t.includes("已恢复"))).toBeUndefined();

    // 4) 按钮 in-flight 复位（不再 disabled）
    await expect(restoreBtn).toBeEnabled();

    // 5) 不触发 submit-turn / SSE / /ai/chat/evidence 请求
    expect(suspiciousRequests).toEqual([]);
  });
});
