/**
 * REQ-042 WS-S1: Workspace store（只读三栏 shell 的状态编排）。
 *
 * 职责：当前 tenant/owner 下的会话选择、loading/empty/error/404/权限态、
 * 会话切换后的历史刷新、Conversation keyset cursor 与 Message before_seq 分页。
 *
 * 边界（WS-S1）：只读。不开放 submit-turn、不接 SSE/cancel、不触碰 extended contracts。
 * 读错误写入 error ref 供 pane 渲染诚实状态；写操作（rename/pin/archive/restore/delete）
 * 抛回 view 由 toast 反馈，并以响应 DTO 整体替换 store 条目（不本地手 bump revision）。
 *
 * 选中会话经 query `?c=<id>` 承载（LayoutView 以 route.path 作为 RouterView key，
 * query 变化不触发 remount，切换流畅且可深链/刷新恢复）。
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  archiveConversation,
  createConversation,
  deleteConversation,
  getConversation,
  getRun,
  listConversations,
  listMessages,
  parseApiError,
  pinConversation,
  renameConversation,
  restoreConversation,
  unpinConversation,
  type AgentRunDTO,
  type ConversationDTO,
  type MessageDTO,
} from "@/services/agentWorkspace";

const MESSAGE_PAGE_SIZE = 50;

export const useWorkspaceStore = defineStore("workspace", () => {
  // --- 会话列表（左栏）---
  const conversations = ref<ConversationDTO[]>([]);
  const conversationsLoading = ref(false);
  const conversationsError = ref<string | null>(null);
  const conversationsNextCursor = ref<string | null>(null);
  const listState = ref<"active" | "archived">("active");
  const searchQuery = ref("");

  const conversationsEmpty = computed(
    () =>
      !conversationsLoading.value &&
      !conversationsError.value &&
      conversations.value.length === 0,
  );
  const conversationsHasMore = computed(() => conversationsNextCursor.value !== null);

  // --- 选中会话（中栏）---
  const selectedId = ref<string | null>(null);
  const selectedConversation = ref<ConversationDTO | null>(null);
  const selectedNotFound = ref(false);

  // --- 消息历史（中栏）---
  const messages = ref<MessageDTO[]>([]);
  const messagesLoading = ref(false);
  const messagesLoadingOlder = ref(false);
  const messagesError = ref<string | null>(null);
  const messagesHasMoreOlder = ref(false);
  const messagesEmpty = computed(
    () => !messagesLoading.value && !messagesError.value && messages.value.length === 0,
  );

  // --- 运行详情（右栏，只读）---
  const selectedRunId = ref<string | null>(null);
  const run = ref<AgentRunDTO | null>(null);
  const runLoading = ref(false);
  const runUnavailable = ref(false); // 404 not_found / 403 / 410 event_history_expired / 409 tombstone → 诚实空态
  const runError = ref<string | null>(null);

  // --- 写操作 in-flight 标记（防双击/快速重复提交；不掩盖 409 revision_conflict）---
  const archiveInFlight = ref(false);
  const restoreInFlight = ref(false);
  const renameInFlight = ref(false);
  const deleteInFlight = ref(false);

  // --- 会话列表加载 ---

  async function loadConversations(reset = false): Promise<void> {
    if (reset) {
      conversations.value = [];
      conversationsNextCursor.value = null;
    }
    conversationsLoading.value = true;
    conversationsError.value = null;
    try {
      const q = searchQuery.value.trim();
      const res = await listConversations({
        state: listState.value,
        // 后端 q 至少 2 个归一化字符；不足时按无搜索处理（不发 q，避免 422）。
        ...(q.length >= 2 ? { q } : {}),
        ...(conversationsNextCursor.value
          ? { cursor: conversationsNextCursor.value }
          : {}),
      });
      conversations.value = reset ? res.items : [...conversations.value, ...res.items];
      conversationsNextCursor.value = res.next_cursor;
    } catch (e) {
      conversationsError.value = parseApiError(e, "加载会话列表失败").message;
      if (reset) conversations.value = [];
    } finally {
      conversationsLoading.value = false;
    }
  }

  async function loadMoreConversations(): Promise<void> {
    if (!conversationsNextCursor.value || conversationsLoading.value) return;
    await loadConversations(false);
  }

  async function setListState(state: "active" | "archived"): Promise<void> {
    if (listState.value === state) return;
    listState.value = state;
    await loadConversations(true);
  }

  async function setSearch(query: string): Promise<void> {
    searchQuery.value = query;
    await loadConversations(true);
  }

  // --- 选中会话 + 消息 ---

  async function selectConversation(id: string): Promise<void> {
    // 不做同 id 短路：view 的 query watcher 仅在 id 变化时触发，pane 点击同项已拦截，
    // 保留可重入以支持错误态重试（重跑 detail + messages）。
    selectedId.value = id;
    clearRun();
    messages.value = [];
    messagesError.value = null;
    messagesHasMoreOlder.value = false;
    // 重置旧会话的 in-flight 标记：避免 load-older guard 误拒新会话的合法加载，
    // 同时避免派生 run 的 selectedRunId 跨会话串留。
    messagesLoadingOlder.value = false;
    selectedConversation.value = null;
    selectedNotFound.value = false;
    await Promise.all([loadSelectedConversation(id), loadMessages(id)]);
    deriveDefaultRun();
  }

  async function loadSelectedConversation(id: string): Promise<void> {
    try {
      const result = await getConversation(id);
      // GUARD：切换到其它会话后丢弃迟到的 A 响应，避免覆盖 B 的 selectedConversation。
      if (selectedId.value !== id) return;
      selectedConversation.value = result;
    } catch {
      if (selectedId.value !== id) return;
      // 不存在 / 跨 owner / 已删除：一律诚实 not-found（不区分，防存在性泄露）。
      selectedConversation.value = null;
      selectedNotFound.value = true;
    }
  }

  async function loadMessages(conversationId: string): Promise<void> {
    messagesLoading.value = true;
    messagesError.value = null;
    try {
      const res = await listMessages(conversationId, { limit: MESSAGE_PAGE_SIZE });
      // GUARD：切换后丢弃迟到的旧会话消息（防 A 响应覆盖 B 的 messages 列表）。
      if (selectedId.value !== conversationId) return;
      messages.value = res.items; // 响应恒按 seq 升序
      messagesHasMoreOlder.value = res.has_more;
    } catch (e) {
      if (selectedId.value !== conversationId) return;
      messagesError.value = parseApiError(e, "加载消息失败").message;
      messages.value = [];
      messagesHasMoreOlder.value = false;
    } finally {
      if (selectedId.value === conversationId) {
        messagesLoading.value = false;
      }
    }
  }

  async function loadOlderMessages(): Promise<void> {
    const id = selectedId.value;
    if (!id || messages.value.length === 0 || !messagesHasMoreOlder.value) return;
    if (messagesLoadingOlder.value) return;
    const minSeq = messages.value[0].seq;
    messagesLoadingOlder.value = true;
    try {
      const res = await listMessages(id, {
        before_seq: minSeq,
        limit: MESSAGE_PAGE_SIZE,
      });
      // GUARD：切换后丢弃迟到的旧会话 load-older（防 A 响应污染 B 的 messages）。
      if (selectedId.value !== id) return;
      const existing = new Set(messages.value.map((m) => m.seq));
      const older = res.items.filter((m) => !existing.has(m.seq));
      messages.value = [...older, ...messages.value];
      messagesHasMoreOlder.value = res.has_more;
    } catch (e) {
      if (selectedId.value !== id) return;
      messagesError.value = parseApiError(e, "加载更早消息失败").message;
    } finally {
      if (selectedId.value === id) {
        messagesLoadingOlder.value = false;
      }
    }
  }

  function clearSelection(): void {
    selectedId.value = null;
    selectedConversation.value = null;
    selectedNotFound.value = false;
    messages.value = [];
    messagesError.value = null;
    messagesHasMoreOlder.value = false;
    clearRun();
  }

  // --- 运行详情（右栏）---

  function clearRun(): void {
    selectedRunId.value = null;
    run.value = null;
    runLoading.value = false;
    runUnavailable.value = false;
    runError.value = null;
  }

  async function selectRun(runId: string): Promise<void> {
    selectedRunId.value = runId;
    run.value = null;
    runUnavailable.value = false;
    runError.value = null;
    runLoading.value = true;
    try {
      const result = await getRun(runId);
      // GUARD：切换到其它 run 后丢弃迟到的旧 run 响应。
      if (selectedRunId.value !== runId) return;
      run.value = result;
    } catch (e) {
      if (selectedRunId.value !== runId) return;
      const info = parseApiError(e, "加载运行详情失败");
      run.value = null;
      // 不存在 / 跨 owner / tombstone（actor 匿名化）/ 事件历史保留期过期：诚实空态。
      // 410 event_history_expired 不显示为普通未知错误——保留期过期是确定的非错误状态。
      if (
        info.status === 404 ||
        info.status === 403 ||
        info.status === 410 ||
        info.code === "not_found" ||
        info.code === "run_conflict" ||
        info.code === "event_history_expired"
      ) {
        runUnavailable.value = true;
      } else {
        runError.value = info.message;
      }
    } finally {
      if (selectedRunId.value === runId) {
        runLoading.value = false;
      }
    }
  }

  /** 会话载入后默认选中最新一条带运行引用的消息对应的 run（右栏默认有用）。 */
  function deriveDefaultRun(): void {
    if (selectedRunId.value) return;
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      const rid = m.origin_run_id ?? m.requested_run_id;
      if (rid) {
        // 默认派生：仅填充右栏数据。移动端是否切到运行面板由 pane 的 show-run 显式事件驱动，
        // 此处不触发切换（避免选中会话后被顶到运行页）。
        void selectRun(rid);
        return;
      }
    }
  }

  // --- 会话写操作（抛回 view toast；以响应 DTO 整体替换，不本地手 bump revision）---

  async function createNewConversation(title?: string): Promise<ConversationDTO> {
    const created = await createConversation(title ? { title } : {});
    await loadConversations(true);
    return created;
  }

  async function renameSelected(newTitle: string): Promise<void> {
    // in-flight guard：双击/快速提交防重复发请求；不掩盖后端 409 revision_conflict。
    if (renameInFlight.value) return;
    const conv = selectedConversation.value;
    if (!conv) return;
    renameInFlight.value = true;
    try {
      const updated = await renameConversation(conv.id, newTitle, conv.revision);
      applyConversationUpdate(updated);
    } finally {
      renameInFlight.value = false;
    }
  }

  async function togglePin(conv: ConversationDTO): Promise<void> {
    const updated = conv.pinned_at
      ? await unpinConversation(conv.id)
      : await pinConversation(conv.id);
    applyConversationUpdate(updated);
    // pinned_at 是列表排序键，重拉以保证顺序与服务端一致。
    await loadConversations(true);
  }

  async function archiveSelected(): Promise<void> {
    // in-flight guard：双击"归档"防并发请求导致 409 revision_conflict 错误 toast 误报。
    if (archiveInFlight.value) return;
    const conv = selectedConversation.value;
    if (!conv) return;
    archiveInFlight.value = true;
    try {
      const updated = await archiveConversation(conv.id, conv.revision);
      applyConversationUpdate(updated);
      await loadConversations(true);
    } finally {
      archiveInFlight.value = false;
    }
  }

  async function restoreConversationById(conv: ConversationDTO): Promise<void> {
    // in-flight guard：双击"恢复"防并发请求。
    if (restoreInFlight.value) return;
    restoreInFlight.value = true;
    try {
      const updated = await restoreConversation(conv.id, conv.revision);
      applyConversationUpdate(updated);
      await loadConversations(true);
    } finally {
      restoreInFlight.value = false;
    }
  }

  async function deleteSelected(): Promise<void> {
    // in-flight guard：双击"删除"防并发请求。
    if (deleteInFlight.value) return;
    const conv = selectedConversation.value;
    if (!conv) return;
    const id = conv.id;
    deleteInFlight.value = true;
    try {
      await deleteConversation(id, conv.revision);
      await loadConversations(true);
      if (selectedId.value === id) {
        clearSelection();
      }
    } finally {
      deleteInFlight.value = false;
    }
  }

  function applyConversationUpdate(updated: ConversationDTO): void {
    const idx = conversations.value.findIndex((c) => c.id === updated.id);
    if (idx >= 0) conversations.value[idx] = updated;
    if (selectedConversation.value?.id === updated.id) {
      selectedConversation.value = updated;
    }
  }

  return {
    // 列表
    conversations,
    conversationsLoading,
    conversationsError,
    conversationsNextCursor,
    conversationsEmpty,
    conversationsHasMore,
    listState,
    searchQuery,
    loadConversations,
    loadMoreConversations,
    setListState,
    setSearch,
    // 选中 + 消息
    selectedId,
    selectedConversation,
    selectedNotFound,
    messages,
    messagesLoading,
    messagesLoadingOlder,
    messagesError,
    messagesHasMoreOlder,
    messagesEmpty,
    selectConversation,
    loadOlderMessages,
    clearSelection,
    // 运行
    selectedRunId,
    run,
    runLoading,
    runUnavailable,
    runError,
    selectRun,
    clearRun,
    // 写
    createNewConversation,
    renameSelected,
    togglePin,
    archiveSelected,
    restoreConversationById,
    deleteSelected,
    // 写操作 in-flight 标记（view 绑定 :disabled 防双击/快速重复提交）
    archiveInFlight,
    restoreInFlight,
    renameInFlight,
    deleteInFlight,
  };
});
