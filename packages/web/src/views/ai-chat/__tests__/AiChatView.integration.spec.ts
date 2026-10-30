import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import AiChatView from "../AiChatView.vue";
import type { EvidenceChatResponse, EvidenceItem } from "@/types/evidence";

const { postMock, openInNewTabMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  openInNewTabMock: vi.fn(),
}));

vi.mock("@/services/api", () => ({ default: { post: postMock } }));
vi.mock("@/utils/aiChatSessionStorage", () => ({
  aiChatStorageKeys: () => ({
    conversation: "test.ai-chat.conversation",
    pendingRequest: "test.ai-chat.pending",
  }),
}));
vi.mock("../openFileUrl", async () => {
  const actual = await vi.importActual<typeof import("../openFileUrl")>("../openFileUrl");
  return { ...actual, openInNewTab: openInNewTabMock };
});

const evidence: EvidenceItem = {
  evidence_id: "chunk:file-1:chunk-1",
  source_type: "chunk",
  file_id: "file-1",
  chunk_id: "chunk-1",
  title: "电路课程标准",
  content: "课程内容",
  snippet: "课程摘要",
  channels: ["vector"],
};

function chatResponse(overrides: Partial<EvidenceChatResponse> = {}) {
  return {
    data: {
      reply: "回答完成",
      sources: [],
      conversation_id: "conversation-from-server",
      user_message_id: "user-message-1",
      run_id: "run-1",
      assistant_message_id: "assistant-message-1",
      ...overrides,
    } satisfies EvidenceChatResponse,
  };
}

let wrapper: VueWrapper | undefined;

function mountChat() {
  wrapper = mount(AiChatView);
  return wrapper;
}

async function submit(text: string) {
  const input = wrapper!.find('[data-testid="chat-input"]');
  await input.setValue(text);
  await input.trigger("keydown", { key: "Enter" });
}

beforeEach(() => {
  postMock.mockReset();
  openInNewTabMock.mockReset();
  sessionStorage.clear();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
});

describe("AiChatView S2 integration", () => {
  it("发送后保留用户/助手排列，并渲染长回答、代码、表格和可导航引用", async () => {
    let resolveResponse!: (value: ReturnType<typeof chatResponse>) => void;
    postMock.mockImplementation(() => new Promise((resolve) => {
      resolveResponse = resolve;
    }));
    const chat = mountChat();
    await submit("电路基础课程包含哪些知识点？");

    expect(chat.find(".ui-composer-busy").exists()).toBe(true);
    expect(chat.find("textarea").attributes("disabled")).toBeDefined();
    resolveResponse(chatResponse({
      reply: "依据 [1]，课程包含实践环节。\n\n```python\nprint('ok')\n```\n\n| 课程 | 学时 |\n| --- | --- |\n| 电路基础 | 64 |",
      sources: [evidence],
    }));
    await flushPromises();

    expect(postMock).toHaveBeenCalledWith(
      "/ai/chat/evidence",
      expect.objectContaining({
        message: "电路基础课程包含哪些知识点？",
        context_window: 5,
        conversation_id: expect.any(String),
        client_message_id: expect.any(String),
      }),
      expect.objectContaining({ timeout: 120000, signal: expect.any(AbortSignal) }),
    );
    expect(chat.find(".chat-message-user").text()).toContain("电路基础课程");
    expect(chat.find(".chat-message-assistant pre code.language-python").exists()).toBe(true);
    expect(chat.find(".chat-message-assistant table").text()).toContain("电路基础");

    await chat.find("a.evidence-ref").trigger("click");
    expect(openInNewTabMock).toHaveBeenCalledOnce();
    const openedUrl = openInNewTabMock.mock.calls[0][0] as string;
    expect(openedUrl).toContain("file-1");
    expect(openedUrl).toContain("chunk-1");
  });

  it("busy 停止沿用 HTTP abort，恢复草稿且不允许重复提交", async () => {
    postMock.mockImplementation((...args: unknown[]) => {
      const config = args[2] as { signal: AbortSignal };
      return new Promise((_resolve, reject) => {
        config.signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "CanceledError";
          reject(error);
        }, { once: true });
      });
    });
    const chat = mountChat();
    await submit("需要停止的问题");
    await chat.find(".ui-composer-stop").trigger("click");
    await flushPromises();

    expect(postMock).toHaveBeenCalledOnce();
    expect(chat.find(".chat-message-stopped").text()).toContain("（已停止生成）");
    expect((chat.find("textarea").element as HTMLTextAreaElement).value).toBe("需要停止的问题");
    expect(chat.find(".ui-composer-stop").exists()).toBe(false);
    expect(chat.text()).not.toContain("后台任务已取消");
  });

  it("错误展示保留既有说明，并用同一 request identity 重试", async () => {
    postMock
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            detail: {
              code: "direct_rag_turn_pending",
              message: "上一条回答仍在生成",
            },
          },
        },
      })
      .mockResolvedValueOnce(chatResponse());
    const chat = mountChat();
    await submit("需要重试的问题");
    await flushPromises();

    expect(chat.find(".chat-message-error").text()).toContain("上一条回答仍在生成");
    expect((chat.find("textarea").element as HTMLTextAreaElement).value).toBe("需要重试的问题");
    await chat.find("textarea").trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(postMock).toHaveBeenCalledTimes(2);
    const firstBody = postMock.mock.calls[0][1] as { client_message_id: string };
    const retryBody = postMock.mock.calls[1][1] as { client_message_id: string };
    expect(retryBody.client_message_id).toBe(firstBody.client_message_id);
  });

  it("建议问题保持原点击即发送语义，按钮不触发表单重复提交", async () => {
    postMock.mockResolvedValue(chatResponse());
    const chat = mountChat();
    const suggestion = chat.find("button.ai-chat-suggestion");
    expect(suggestion.attributes("type")).toBe("button");
    await suggestion.trigger("click");
    await flushPromises();

    expect(postMock).toHaveBeenCalledOnce();
    expect(postMock.mock.calls[0][1]).toEqual(expect.objectContaining({
      message: "电子信息工程专业有哪些核心课程？",
    }));
    expect(chat.find(".ai-chat-empty").exists()).toBe(false);
  });

  it("Composer 在滚动区外正常占位，空白输入不发送", async () => {
    const chat = mountChat();
    expect(chat.find(".ai-chat-scroll .ai-chat-composer").exists()).toBe(false);
    expect(chat.find(".ai-chat-bottom .ai-chat-composer").exists()).toBe(true);
    await submit("   ");
    expect(postMock).not.toHaveBeenCalled();
    expect(chat.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
  });

  it("页面不产生嵌套 main landmark，消息区保留可访问名称", () => {
    const chat = mountChat();
    expect(chat.find("main").exists()).toBe(false);
    expect(chat.find('section[aria-label="对话消息"]').exists()).toBe(true);
  });
});
