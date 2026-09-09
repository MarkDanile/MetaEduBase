/**
 * REQ-042 WS-S1: AgentWorkspaceView 三栏 shell smoke。
 *
 * 覆盖：
 * 1. 桌面宽度渲染三栏（会话列表 / 消息时间线 / 运行详情）；
 * 2. 挂载即拉取会话列表并渲染；
 * 3. 无 query 时中栏诚实空态「选择一个会话」；
 * 4. query ?c=<id> 触发选中（getConversation + listMessages），渲染标题与消息；
 * 5. composer 发送按钮禁用（明确非提交状态，无虚假发送路径）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const { pushMock, routeQuery } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  routeQuery: { c: undefined as string | undefined },
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ query: routeQuery }),
}));

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

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import AgentWorkspaceView from "./AgentWorkspaceView.vue";
import {
  getConversation,
  listConversations,
  listMessages,
  type ConversationDTO,
  type MessageDTO,
} from "@/services/agentWorkspace";

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
    parts: [
      {
        id: "p-1",
        part_seq: 1,
        type: "text",
        text: "你好，Workspace",
        format: null,
        resource_id: null,
        media_type: null,
        display_name: null,
        classification: "internal",
      },
    ],
    ...over,
  };
}

let currentWrapper: ReturnType<typeof mount> | undefined;

async function mountView() {
  setActivePinia(createPinia());
  const w = mount(AgentWorkspaceView);
  currentWrapper = w;
  await flushPromises();
  return w;
}

describe("AgentWorkspaceView.vue (REQ-042 WS-S1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeQuery.c = undefined;
    vi.mocked(listConversations).mockResolvedValue({
      items: [makeConv({ id: "c-1", title: "会话一" }), makeConv({ id: "c-2", title: "会话二" })],
      next_cursor: null,
    });
  });

  afterEach(() => {
    currentWrapper?.unmount();
    currentWrapper = undefined;
    localStorage.clear();
  });

  it("桌面宽度渲染三栏骨架 + 挂载即拉取并渲染会话列表", async () => {
    const wrapper = await mountView();

    expect(listConversations).toHaveBeenCalled();
    expect(wrapper.find('[data-testid="agent-workspace"]').exists()).toBe(true);
    // 三个面板均挂载（桌面 v-show 全 true）
    expect(wrapper.find('[data-testid="ws-conv-c-1"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="ws-conv-c-2"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("会话一");
    expect(wrapper.text()).toContain("会话二");
  });

  it("无 query 时中栏显示「选择一个会话」诚实空态", async () => {
    const wrapper = await mountView();
    expect(wrapper.text()).toContain("选择一个会话");
    expect(getConversation).not.toHaveBeenCalled();
  });

  it("query ?c=<id> 触发选中并渲染标题与消息", async () => {
    routeQuery.c = "c-1";
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1", title: "会话一" }));
    vi.mocked(listMessages).mockResolvedValue({ items: [makeMsg({ seq: 1 })], has_more: false });

    const wrapper = await mountView();

    expect(getConversation).toHaveBeenCalledWith("c-1");
    expect(listMessages).toHaveBeenCalledWith("c-1", { limit: 50 });
    expect(wrapper.find('[data-testid="ws-conv-heading"]').text()).toBe("会话一");
    expect(wrapper.find('[data-testid="ws-msg-1"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("你好，Workspace");
  });

  it("composer 发送按钮禁用（明确非提交，无发送路径）", async () => {
    routeQuery.c = "c-1";
    vi.mocked(getConversation).mockResolvedValue(makeConv({ id: "c-1" }));
    vi.mocked(listMessages).mockResolvedValue({ items: [], has_more: false });

    const wrapper = await mountView();

    const sendBtn = wrapper.find('[data-testid="ws-send-btn"]');
    expect(sendBtn.exists()).toBe(true);
    expect(sendBtn.attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="ws-composer-input"]').exists()).toBe(true);
  });
});
