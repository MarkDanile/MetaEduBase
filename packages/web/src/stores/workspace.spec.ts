/**
 * REQ-042 WS-S1: workspace store 测试。
 *
 * mock `@/services/agentWorkspace` 的请求函数（保留真实 parseApiError / TERMINAL_RUN_STATUSES），
 * 覆盖：会话列表 keyset 分页/搜索/错误、选中+消息载入、before_seq 历史分页去重、
 * run 读取的三态（成功 / 404-409 诚实空态 / 其他错误）、写操作的 If-Match 与 selection 维护。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises } from "@vue/test-utils";

vi.mock("@/services/agentWorkspace", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/services/agentWorkspace")>();
  return {
    ...actual,
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    renameConversation: vi.fn(),
    pinConversation: vi.fn(),
    unpinConversation: vi.fn(),
    archiveConversation: vi.fn(),
    restoreConversation: vi.fn(),
    deleteConversation: vi.fn(),
    listMessages: vi.fn(),
    getRun: vi.fn(),
  };
});

import {
  archiveConversation,
  createConversation,
  deleteConversation,
  getConversation,
  getRun,
  listConversations,
  listMessages,
  pinConversation,
  renameConversation,
  restoreConversation,
  unpinConversation,
  type AgentRunDTO,
  type ConversationDTO,
  type MessageDTO,
} from "@/services/agentWorkspace";
import { useWorkspaceStore } from "./workspace";

function makeConv(over: Partial<ConversationDTO> = {}): ConversationDTO {
  return {
    id: "c-1",
    title: "会话一",
    title_source: "user",
    state: "active",
    parent_conversation_id: null,
    forked_from_message_id: null,
    last_activity_at: "2026-09-09T10:00:00Z",
    pinned_at: null,
    revision: 1,
    created_at: "2026-09-09T09:00:00Z",
    updated_at: "2026-09-09T10:00:00Z",
    ...over,
  };
}

function makeMsg(over: Partial<MessageDTO> = {}): MessageDTO {
  return {
    id: "m-1",
    seq: 1,
    kind: "user_input",
    author_type: "user",
    author_id: "u-1",
    requested_run_id: null,
    requested_run_queue_seq: null,
    dispatch_state: null,
    origin_run_id: null,
    output_ordinal: null,
    reply_to_message_id: null,
    content_state: "visible",
    created_at: "2026-09-09T10:00:00Z",
    parts: [],
    ...over,
  };
}

function makeRun(over: Partial<AgentRunDTO> = {}): AgentRunDTO {
  return {
    id: "r-1",
    conversation_id: "c-1",
    queue_seq: 1,
    root_input_message_id: "m-1",
    parent_run_id: null,
    agent_definition_version_id: "adv-1",
    runtime_profile_id: "rp-1",
    runtime_binding_id: null,
    status: "completed",
    status_revision: 1,
    first_available_event_seq: 1,
    last_event_seq: 5,
    event_log_complete: true,
    queued_at: "2026-09-09T10:00:00Z",
    started_at: "2026-09-09T10:00:01Z",
    ended_at: "2026-09-09T10:00:05Z",
    terminal_code: null,
    terminal_reason: null,
    terminal_result_digest: null,
    terminal_output_digest: null,
    terminal_output_size: null,
    terminal_output_media_type: null,
    terminal_output_classification: null,
    terminal_message_id: null,
    output_publish_state: "published",
    usage: { input_tokens: 10, output_tokens: 20 },
    pending_input_request_count: 0,
    pending_approval_count: 0,
    created_at: "2026-09-09T10:00:00Z",
    updated_at: "2026-09-09T10:00:05Z",
    ...over,
  };
}

function apiError(status: number, code: string, message: string) {
  return { response: { status, data: { detail: { code, message } } } };
}

describe("workspace store (REQ-042 WS-S1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  // --- 列表分页 / 搜索 / 错误 ---

  it("loadConversations 首屏 + loadMore 累积 cursor", async () => {
    vi.mocked(listConversations)
      .mockResolvedValueOnce({
        items: [makeConv({ id: "c-1" }), makeConv({ id: "c-2" })],
        next_cursor: "cur-2",
      })
      .mockResolvedValueOnce({ items: [makeConv({ id: "c-3" })], next_cursor: null });
    const store = useWorkspaceStore();

    await store.loadConversations(true);
    expect(store.conversations.map((c) => c.id)).toEqual(["c-1", "c-2"]);
    expect(store.conversationsHasMore).toBe(true);
    expect(listConversations).toHaveBeenLastCalledWith({ state: "active" });

    await store.loadMoreConversations();
    expect(store.conversations.map((c) => c.id)).toEqual(["c-1", "c-2", "c-3"]);
    expect(store.conversationsHasMore).toBe(false);
    expect(listConversations).toHaveBeenLastCalledWith({ state: "active", cursor: "cur-2" });
  });

  it("搜索 q 少于 2 字不上送，>=2 字上送", async () => {
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.setSearch("报");
    expect(listConversations).toHaveBeenLastCalledWith({ state: "active" });

    await store.setSearch("报告");
    expect(listConversations).toHaveBeenLastCalledWith({ state: "active", q: "报告" });
  });

  it("setListState 切换 tab 重置并重新拉取", async () => {
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();
    await store.setListState("archived");
    expect(store.listState).toBe("archived");
    expect(listConversations).toHaveBeenLastCalledWith({ state: "archived" });
  });

  it("loadConversations 失败写入 error 并清空列表", async () => {
    vi.mocked(listConversations).mockRejectedValue(apiError(500, "x", "服务器错误"));
    const store = useWorkspaceStore();
    await store.loadConversations(true);
    expect(store.conversationsError).toBe("服务器错误");
    expect(store.conversations).toEqual([]);
  });

  // --- 选中 + 消息 ---

  it("selectConversation 载入 detail+messages 并默认选中最新带运行的消息", async () => {
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1" }));
    vi.mocked(listMessages).mockResolvedValue({
      items: [makeMsg({ id: "m-1", seq: 1 }), makeMsg({ id: "m-2", seq: 2, origin_run_id: "r-2" })],
      has_more: false,
    });
    vi.mocked(getRun).mockResolvedValue(makeRun({ id: "r-2" }));
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");
    await flushPromises();

    expect(store.selectedConversation?.id).toBe("c-1");
    expect(store.messages.map((m) => m.seq)).toEqual([1, 2]);
    expect(getRun).toHaveBeenCalledWith("r-2");
    expect(store.run?.id).toBe("r-2");
  });

  it("selectConversation detail 404 -> selectedNotFound", async () => {
    vi.mocked(getConversation).mockRejectedValue(apiError(404, "not_found", "不存在"));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    const store = useWorkspaceStore();

    await store.selectConversation("c-x");
    expect(store.selectedConversation).toBeNull();
    expect(store.selectedNotFound).toBe(true);
  });

  it("loadOlderMessages 用最小 seq 作 before_seq 前置并去重", async () => {
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1" }));
    vi.mocked(listMessages)
      .mockResolvedValueOnce({
        items: [makeMsg({ id: "m-3", seq: 3 }), makeMsg({ id: "m-4", seq: 4 })],
        has_more: true,
      })
      .mockResolvedValueOnce({
        items: [makeMsg({ id: "m-1", seq: 1 }), makeMsg({ id: "m-2", seq: 2 })],
        has_more: false,
      });
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");
    expect(store.messages.map((m) => m.seq)).toEqual([3, 4]);

    await store.loadOlderMessages();
    expect(listMessages).toHaveBeenLastCalledWith("c-1", { before_seq: 3, limit: 50 });
    expect(store.messages.map((m) => m.seq)).toEqual([1, 2, 3, 4]);
    expect(store.messagesHasMoreOlder).toBe(false);
  });

  // --- run 读取三态 ---

  it("selectRun 成功载入", async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ id: "r-1" }));
    const store = useWorkspaceStore();
    await store.selectRun("r-1");
    expect(store.run?.id).toBe("r-1");
    expect(store.runUnavailable).toBe(false);
    expect(store.runError).toBeNull();
  });

  it("selectRun 404 not_found -> runUnavailable 诚实空态", async () => {
    vi.mocked(getRun).mockRejectedValue(apiError(404, "not_found", "x"));
    const store = useWorkspaceStore();
    await store.selectRun("r-x");
    expect(store.run).toBeNull();
    expect(store.runUnavailable).toBe(true);
    expect(store.runError).toBeNull();
  });

  it("selectRun 409 run_conflict(tombstone) -> runUnavailable", async () => {
    vi.mocked(getRun).mockRejectedValue(apiError(409, "run_conflict", "x"));
    const store = useWorkspaceStore();
    await store.selectRun("r-x");
    expect(store.runUnavailable).toBe(true);
  });

  it("selectRun 其他错误 -> runError", async () => {
    vi.mocked(getRun).mockRejectedValue(apiError(500, "x", "服务器错误"));
    const store = useWorkspaceStore();
    await store.selectRun("r-x");
    expect(store.runError).toBe("服务器错误");
    expect(store.runUnavailable).toBe(false);
  });

  // --- 写操作 ---

  it("createNewConversation 创建后重拉列表并返回 DTO", async () => {
    const created = makeConv({ id: "c-new" });
    vi.mocked(createConversation).mockResolvedValue(created);
    vi.mocked(listConversations).mockResolvedValue({ items: [created], next_cursor: null });
    const store = useWorkspaceStore();

    const result = await store.createNewConversation();
    expect(createConversation).toHaveBeenCalledWith({});
    expect(result.id).toBe("c-new");
    expect(listConversations).toHaveBeenCalled();
  });

  it("renameSelected 用当前 revision 调用并应用响应 DTO", async () => {
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1", revision: 3, title: "旧" }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(renameConversation).mockResolvedValue(makeConv({ id: "c-1", revision: 4, title: "新" }));
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");
    await store.renameSelected("新");

    expect(renameConversation).toHaveBeenCalledWith("c-1", "新", 3);
    expect(store.selectedConversation?.title).toBe("新");
    expect(store.selectedConversation?.revision).toBe(4);
  });

  it("togglePin 未置顶 -> pinConversation 并重拉列表", async () => {
    vi.mocked(pinConversation).mockResolvedValue(makeConv({ id: "c-1", pinned_at: "2026-09-09T11:00:00Z" }));
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.togglePin(makeConv({ id: "c-1", pinned_at: null }));
    expect(pinConversation).toHaveBeenCalledWith("c-1");
    expect(listConversations).toHaveBeenCalled();
  });

  it("togglePin 已置顶 -> unpinConversation", async () => {
    vi.mocked(unpinConversation).mockResolvedValue(makeConv({ id: "c-1", pinned_at: null }));
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.togglePin(makeConv({ id: "c-1", pinned_at: "2026-09-09T11:00:00Z" }));
    expect(unpinConversation).toHaveBeenCalledWith("c-1");
  });

  it("archiveSelected 用当前 revision 归档并重拉", async () => {
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1", revision: 2, state: "active" }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(archiveConversation).mockResolvedValue(makeConv({ id: "c-1", state: "archived", revision: 3 }));
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");
    await store.archiveSelected();

    expect(archiveConversation).toHaveBeenCalledWith("c-1", 2);
    expect(listConversations).toHaveBeenCalled();
  });

  it("deleteSelected 删除当前选中会话 -> 清空选中", async () => {
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1", revision: 2 }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(deleteConversation).mockResolvedValue(makeConv({ id: "c-1", state: "deleted" }));
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");
    await store.deleteSelected();

    expect(deleteConversation).toHaveBeenCalledWith("c-1", 2);
    expect(store.selectedId).toBeNull();
    expect(store.selectedConversation).toBeNull();
  });

  // --- 修复轮 P1/P2 复审新增 ---

  it("selectRun 410 event_history_expired -> runUnavailable 诚实空态（不显示为普通错误）", async () => {
    // 事件历史保留期过期是确定的非错误状态（数据已 purge），不应弹"加载失败"错误。
    vi.mocked(getRun).mockRejectedValue(
      apiError(410, "event_history_expired", "事件历史已过期"),
    );
    const store = useWorkspaceStore();
    await store.selectRun("r-expired");
    expect(store.run).toBeNull();
    expect(store.runUnavailable).toBe(true);
    expect(store.runError).toBeNull();
    expect(store.runLoading).toBe(false);
  });

  it("selectRun 切到其它 run 后，旧 run 的迟到响应被丢弃（防跨 run 数据串读）", async () => {
    // 模拟快速 selectRun(A) → selectRun(B)：A 的响应延迟到达，必须不覆盖 B 的 state。
    let resolveA: (v: AgentRunDTO) => void;
    const aPromise = new Promise<AgentRunDTO>((r) => {
      resolveA = r;
    });
    vi.mocked(getRun).mockImplementation(async (id) => {
      if (id === "r-A") return aPromise;
      return makeRun({ id: "r-B", conversation_id: "c-2" });
    });
    const store = useWorkspaceStore();

    // 触发 selectRun(r-A)（不 await，让其挂起）
    const selectA = store.selectRun("r-A");
    // 同步切换到 r-B；r-B 的 mock 立即 resolve。
    const selectB = store.selectRun("r-B");
    await flushPromises();

    // 现在 A 的延迟 promise resolve——必须被 GUARD 丢弃。
    resolveA!(makeRun({ id: "r-A" }));
    await selectA;
    await selectB;

    expect(store.selectedRunId).toBe("r-B");
    expect(store.run?.id).toBe("r-B");
    expect(store.runLoading).toBe(false);
  });

  it("切换会话时重置 messagesLoadingOlder：旧会话 load-older in-flight 不阻塞新会话 load-older", async () => {
    // 旧会话 A 触发 load-older 进入 in-flight（messagesLoadingOlder=true），
    // 然后切换到 B（selectConversation 应重置该 flag），
    // B 的 load-older 必须可立即执行（不被 guard 误拒）。
    // listMessages 调用顺序：A 首屏 → A load-older(deferred) → B 首屏 → B load-older。
    let resolveOlderA: (v: { items: MessageDTO[]; has_more: boolean }) => void;
    const olderAPromise = new Promise<{ items: MessageDTO[]; has_more: boolean }>((r) => {
      resolveOlderA = r;
    });
    vi.mocked(listMessages)
      .mockResolvedValueOnce({
        // [1] A 首屏
        items: [makeMsg({ id: "m-A1", seq: 1 })],
        has_more: true,
      })
      .mockReturnValueOnce(olderAPromise) // [2] A load-older（deferred）
      .mockResolvedValueOnce({
        // [3] B 首屏
        items: [makeMsg({ id: "m-B1", seq: 1 })],
        has_more: true,
      })
      .mockResolvedValueOnce({
        // [4] B load-older
        items: [],
        has_more: false,
      });
    vi.mocked(getConversation).mockImplementation(async (id) => makeConv({ id }));
    const store = useWorkspaceStore();
    await store.selectConversation("c-A");

    // 启动 A 的 load-older 但不 await（模拟延迟响应）。
    const olderA = store.loadOlderMessages();
    expect(store.messagesLoadingOlder).toBe(true);

    // 切换到 B——应重置 messagesLoadingOlder=false。
    await store.selectConversation("c-B");
    expect(store.selectedId).toBe("c-B");
    expect(store.messagesLoadingOlder).toBe(false);

    // B 的 load-older 必须可立即执行（不被 guard 误拒）。
    await store.loadOlderMessages();
    expect(store.messagesLoadingOlder).toBe(false);
    expect(store.messages.map((m) => m.id)).toEqual(["m-B1"]);

    // 清理 A 的延迟响应——GUARD 应丢弃其结果，不污染 B 的 messages。
    resolveOlderA!({ items: [], has_more: false });
    await olderA;
    // A 的迟到响应不影响 B 的 state（messages 仍是 B 的 m-B1）。
    expect(store.selectedId).toBe("c-B");
    expect(store.messages.map((m) => m.id)).toEqual(["m-B1"]);
  });

  it("archiveSelected 双击/快速重复提交：第二次调用被 in-flight guard 拒绝", async () => {
    // store 层 guard：防 view 层即使漏掉 disabled 也能阻止并发请求。
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1", revision: 2, state: "active" }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    let resolveArchive: (v: ConversationDTO) => void;
    const archivePromise = new Promise<ConversationDTO>((r) => {
      resolveArchive = r;
    });
    vi.mocked(archiveConversation).mockReturnValueOnce(archivePromise);
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();

    await store.selectConversation("c-1");

    // 第一次 archiveSelected 进入 in-flight。
    const first = store.archiveSelected();
    expect(store.archiveInFlight).toBe(true);

    // 第二次立即调用——必须被 guard 拒绝（archiveConversation 仍只调用 1 次）。
    const second = store.archiveSelected();
    expect(store.archiveInFlight).toBe(true);

    // 第一次完成。
    resolveArchive!(makeConv({ id: "c-1", state: "archived", revision: 3 }));
    await Promise.all([first, second]);

    expect(archiveConversation).toHaveBeenCalledTimes(1);
    expect(store.archiveInFlight).toBe(false);
  });

  // --- 覆盖补强（增量复审）---

  it("selectConversation A→B race：deferred getConversation A 不覆盖 B 的 selectedConversation", async () => {
    // 真实 deferred race：延迟 A 的 getConversation，模拟服务端慢响应；
    // 切到 B 后 resolve A，验证 GUARD 丢弃 A 的迟到响应不污染 B 的 selectedConversation
    // 及 messages / error / loading 状态。
    let resolveA: (v: ConversationDTO) => void;
    const aPromise = new Promise<ConversationDTO>((r) => {
      resolveA = r;
    });
    vi.mocked(getConversation).mockImplementation(async (id) => {
      if (id === "c-A") return aPromise;
      return makeConv({ id: "c-B", title: "B", revision: 1, state: "active" });
    });
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    const store = useWorkspaceStore();

    // 触发 selectConversation("c-A")（不 await，让其挂起）
    const selectA = store.selectConversation("c-A");
    // 同步切到 c-B；mock 立即 resolve
    await store.selectConversation("c-B");

    // 此时 selectedConversation 应为 B（B 的 detail 已落地）
    expect(store.selectedConversation?.id).toBe("c-B");

    // resolve A 的迟到 selectedConversation 响应——必须被 GUARD 丢弃
    resolveA!(
      makeConv({ id: "c-A", title: "A", revision: 1, state: "active" }),
    );
    await selectA;

    // A 的迟到响应不覆盖 B 的 selectedConversation / messages / loading / error
    expect(store.selectedId).toBe("c-B");
    expect(store.selectedConversation?.id).toBe("c-B");
    expect(store.selectedConversation?.title).toBe("B");
    expect(store.messages).toEqual([]);
    expect(store.messagesError).toBeNull();
    expect(store.messagesLoading).toBe(false);
  });

  it("selectConversation A→B race：deferred 首屏 listMessages A 不覆盖 B 的 messages", async () => {
    // 真实 deferred race：延迟 A 的首屏 listMessages；切到 B 后 resolve A，
    // 验证 GUARD 丢弃 A 的迟到 messages 不污染 B 的 messages 列表。
    let resolveAMsgs: (v: { items: MessageDTO[]; has_more: boolean }) => void;
    const aMsgsPromise = new Promise<{ items: MessageDTO[]; has_more: boolean }>(
      (r) => {
        resolveAMsgs = r;
      },
    );
    vi.mocked(listMessages)
      .mockReturnValueOnce(aMsgsPromise) // [1] A 首屏（deferred）
      .mockResolvedValueOnce({
        // [2] B 首屏
        items: [
          makeMsg({ id: "m-B1", seq: 1 }),
          makeMsg({ id: "m-B2", seq: 2 }),
        ],
        has_more: false,
      });
    vi.mocked(getConversation).mockImplementation(async (id) =>
      makeConv({ id, revision: 1, state: "active" }),
    );
    const store = useWorkspaceStore();

    // select A 不 await（listMessages(A) deferred）
    const selectA = store.selectConversation("c-A");
    // 切到 B 并完成加载（B 的 listMessages 立即 resolve）
    await store.selectConversation("c-B");

    // 此时 messages 应为 B 的 m-B1 + m-B2
    expect(store.messages.map((m) => m.id)).toEqual(["m-B1", "m-B2"]);

    // resolve A 的迟到 messages——必须被 GUARD 丢弃
    resolveAMsgs!({
      items: [makeMsg({ id: "m-A1", seq: 1 })],
      has_more: false,
    });
    await selectA;

    // A 的迟到响应不污染 B 的 messages
    expect(store.selectedId).toBe("c-B");
    expect(store.messages.map((m) => m.id)).toEqual(["m-B1", "m-B2"]);
    expect(store.messagesError).toBeNull();
    expect(store.messagesLoading).toBe(false);
  });

  it("restoreConversationById 双击 guard：两次快速调用只产生一个 API 请求 + finally 复位", async () => {
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 1, state: "archived" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    let resolveRestore: (v: ConversationDTO) => void;
    const restorePromise = new Promise<ConversationDTO>((r) => {
      resolveRestore = r;
    });
    vi.mocked(restoreConversation).mockReturnValueOnce(restorePromise);
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");
    const archivedConv = store.selectedConversation!;

    // 第一次 restoreConversationById 进入 in-flight。
    const first = store.restoreConversationById(archivedConv);
    expect(store.restoreInFlight).toBe(true);

    // 第二次立即调用——必须被 guard 拒绝（restoreConversation 仍只调用 1 次）。
    const second = store.restoreConversationById(archivedConv);
    expect(store.restoreInFlight).toBe(true);

    // 第一次完成。
    resolveRestore!(makeConv({ id: "c-1", state: "active", revision: 2 }));
    await Promise.all([first, second]);

    expect(restoreConversation).toHaveBeenCalledTimes(1);
    expect(store.restoreInFlight).toBe(false);
  });

  it("renameSelected 双击 guard：两次快速调用只产生一个 API 请求 + finally 复位", async () => {
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 3, title: "旧标题", state: "active" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    let resolveRename: (v: ConversationDTO) => void;
    const renamePromise = new Promise<ConversationDTO>((r) => {
      resolveRename = r;
    });
    vi.mocked(renameConversation).mockReturnValueOnce(renamePromise);
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");

    // 第一次 renameSelected 进入 in-flight。
    const first = store.renameSelected("新标题 A");
    expect(store.renameInFlight).toBe(true);

    // 第二次立即调用——必须被 guard 拒绝（renameConversation 仍只调用 1 次）。
    const second = store.renameSelected("新标题 B");
    expect(store.renameInFlight).toBe(true);

    // 第一次完成。
    resolveRename!(
      makeConv({ id: "c-1", title: "新标题 A", revision: 4, state: "active" }),
    );
    await Promise.all([first, second]);

    expect(renameConversation).toHaveBeenCalledTimes(1);
    expect(renameConversation).toHaveBeenCalledWith("c-1", "新标题 A", 3);
    expect(store.renameInFlight).toBe(false);
  });

  it("deleteSelected 双击 guard：两次快速调用只产生一个 API 请求 + finally 复位", async () => {
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 2, state: "active" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    let resolveDelete: (v: ConversationDTO) => void;
    const deletePromise = new Promise<ConversationDTO>((r) => {
      resolveDelete = r;
    });
    vi.mocked(deleteConversation).mockReturnValueOnce(deletePromise);
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");

    // 第一次 deleteSelected 进入 in-flight。
    const first = store.deleteSelected();
    expect(store.deleteInFlight).toBe(true);

    // 第二次立即调用——必须被 guard 拒绝（deleteConversation 仍只调用 1 次）。
    const second = store.deleteSelected();
    expect(store.deleteInFlight).toBe(true);

    // 第一次完成。
    resolveDelete!(makeConv({ id: "c-1", state: "deleted", revision: 3 }));
    await Promise.all([first, second]);

    expect(deleteConversation).toHaveBeenCalledTimes(1);
    expect(deleteConversation).toHaveBeenCalledWith("c-1", 2);
    expect(store.deleteInFlight).toBe(false);
  });

  it("restoreConversationById 409 revision_conflict 透明抛出 + finally 复位 + 后续可发起", async () => {
    // 证明：409 错误不被 guard 吞掉；finally 仍执行复位 ref；后续调用可重新发起。
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 1, state: "archived" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(restoreConversation)
      .mockRejectedValueOnce(
        apiError(409, "revision_conflict", "已被其他人修改"),
      )
      .mockResolvedValueOnce(
        makeConv({ id: "c-1", state: "active", revision: 2 }),
      );
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");
    const conv = store.selectedConversation!;

    // 第一次调用应 throw（409 透明上抛，不被 finally 吞掉）
    await expect(store.restoreConversationById(conv)).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: "revision_conflict" } } },
    });

    // finally 已复位
    expect(store.restoreInFlight).toBe(false);

    // 第二次调用可重新发起（ref 已复位，guard 不阻塞）
    await store.restoreConversationById(conv);
    expect(restoreConversation).toHaveBeenCalledTimes(2);
    expect(store.restoreInFlight).toBe(false);
  });

  it("renameSelected 409 revision_conflict 透明抛出 + finally 复位 + 后续可发起", async () => {
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 3, title: "旧", state: "active" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(renameConversation)
      .mockRejectedValueOnce(apiError(409, "revision_conflict", "已被其他人修改"))
      .mockResolvedValueOnce(makeConv({ id: "c-1", title: "新", revision: 4 }));
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");

    await expect(store.renameSelected("新")).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: "revision_conflict" } } },
    });
    expect(store.renameInFlight).toBe(false);

    await store.renameSelected("新");
    expect(renameConversation).toHaveBeenCalledTimes(2);
    expect(store.renameInFlight).toBe(false);
  });

  it("deleteSelected 409 revision_conflict 透明抛出 + finally 复位 + 后续可发起", async () => {
    vi.mocked(getConversation).mockResolvedValue(
      makeConv({ id: "c-1", revision: 2, state: "active" }),
    );
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });
    vi.mocked(deleteConversation)
      .mockRejectedValueOnce(apiError(409, "revision_conflict", "已被其他人修改"))
      .mockResolvedValueOnce(makeConv({ id: "c-1", state: "deleted", revision: 3 }));
    vi.mocked(listConversations).mockResolvedValue({ items: [], next_cursor: null });
    const store = useWorkspaceStore();
    await store.selectConversation("c-1");

    await expect(store.deleteSelected()).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: "revision_conflict" } } },
    });
    expect(store.deleteInFlight).toBe(false);

    // selectedConversation 仍存在（第一次 delete 在 409 后未到 clearSelection 路径）
    // 后续调用可发起，deleteConversation 被调用第二次
    await store.deleteSelected();
    expect(deleteConversation).toHaveBeenCalledTimes(2);
    expect(store.deleteInFlight).toBe(false);
  });
});
