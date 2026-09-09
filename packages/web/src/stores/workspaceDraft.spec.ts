/**
 * REQ-042 WS-S1: workspaceDraft store 测试。
 *
 * 覆盖：tenant+owner 隔离的 key 派生、set/get/clear 持久化、空文本清 key、
 * 跨 owner 不串读（含响应式镜像）、未登录静默降级。
 */
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useWorkspaceDraftStore, workspaceScope } from "./workspaceDraft";

function token(subject: string): string {
  const payload = btoa(JSON.stringify({ sub: subject }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${payload}.signature`;
}

function loginAs(subject: string, tenant: string): void {
  localStorage.setItem("metaedu_token", token(subject));
  localStorage.setItem("metaedu_tenant_id", tenant);
}

describe("workspaceDraft store (REQ-042 WS-S1)", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("派生 tenant+owner scope，不同 owner/tenant 不同 key", () => {
    expect(workspaceScope(token("user-a"), "tenant-a")).toBe("tenant-a.user-a");
    expect(workspaceScope(token("user-b"), "tenant-a")).toBe("tenant-a.user-b");
    expect(workspaceScope(token("user-a"), "tenant-b")).toBe("tenant-b.user-a");
    expect(workspaceScope(null, "tenant-a")).toBeNull();
    expect(workspaceScope(token("user-a"), null)).toBeNull();
  });

  it("setDraft 写入 scoped key，getDraft 读回；clearDraft 清除", () => {
    loginAs("user-a", "tenant-a");
    const store = useWorkspaceDraftStore();

    store.setDraft("conv-1", "草稿内容");
    expect(store.getDraft("conv-1")).toBe("草稿内容");
    expect(
      localStorage.getItem("metaedu.workspace.tenant-a.user-a.draft.conv-1"),
    ).toBe("草稿内容");

    store.clearDraft("conv-1");
    expect(store.getDraft("conv-1")).toBe("");
    expect(
      localStorage.getItem("metaedu.workspace.tenant-a.user-a.draft.conv-1"),
    ).toBeNull();
  });

  it("空文本写入 -> 移除 key（不留空串）", () => {
    loginAs("user-a", "tenant-a");
    const store = useWorkspaceDraftStore();

    store.setDraft("conv-1", "abc");
    store.setDraft("conv-1", "");
    expect(
      localStorage.getItem("metaedu.workspace.tenant-a.user-a.draft.conv-1"),
    ).toBeNull();
    expect(store.getDraft("conv-1")).toBe("");
  });

  it("跨 owner 不串读：user-a 草稿对 user-b 不可见（含镜像缓存）", () => {
    loginAs("user-a", "tenant-a");
    let store = useWorkspaceDraftStore();
    store.setDraft("conv-1", "user-a 的草稿");

    // 同一 Pinia 实例、同一 storage，切换到 user-b
    loginAs("user-b", "tenant-a");
    store = useWorkspaceDraftStore();
    expect(store.getDraft("conv-1")).toBe("");

    // user-b 写自己的草稿，互不影响
    store.setDraft("conv-1", "user-b 的草稿");
    expect(localStorage.getItem("metaedu.workspace.tenant-a.user-a.draft.conv-1")).toBe(
      "user-a 的草稿",
    );
    expect(localStorage.getItem("metaedu.workspace.tenant-a.user-b.draft.conv-1")).toBe(
      "user-b 的草稿",
    );
  });

  it("未登录（无 token/tenant）-> 读写静默降级为空，不 throw", () => {
    const store = useWorkspaceDraftStore();
    expect(() => {
      store.setDraft("conv-1", "x");
      store.clearDraft("conv-1");
    }).not.toThrow();
    expect(store.getDraft("conv-1")).toBe("");
    expect(localStorage.length).toBe(0);
  });

  it(" malformed token -> scope null，静默降级", () => {
    localStorage.setItem("metaedu_token", "not-a-jwt");
    localStorage.setItem("metaedu_tenant_id", "tenant-a");
    const store = useWorkspaceDraftStore();
    expect(store.getDraft("conv-1")).toBe("");
    expect(() => store.setDraft("conv-1", "x")).not.toThrow();
  });
});
