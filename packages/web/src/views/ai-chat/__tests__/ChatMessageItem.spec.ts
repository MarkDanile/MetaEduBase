import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ChatMessageItem from "../ChatMessageItem.vue";
import type { ChatMessage } from "../chatMessage";
import type { EvidenceItem } from "@/types/evidence";

const evidence: EvidenceItem = {
  evidence_id: "chunk:file-1:chunk-1",
  source_type: "chunk",
  file_id: "file-1",
  chunk_id: "chunk-1",
  title: "课程标准",
  content: "内容",
  snippet: "摘要",
  channels: ["vector"],
};

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "回答",
    document_sources_view: [],
    ...overrides,
  };
}

describe("ChatMessageItem (DB-03)", () => {
  it("用户消息使用独立纯文本气泡，不经过 Markdown", () => {
    const wrapper = mount(ChatMessageItem, {
      props: { message: message({ id: "user-1", role: "user", content: "**不加粗**" }) },
    });
    expect(wrapper.find(".chat-message-user").exists()).toBe(true);
    expect(wrapper.find("strong").exists()).toBe(false);
    expect(wrapper.text()).toContain("**不加粗**");
  });

  it("助手长回答保留代码、表格和消息内证据引用", () => {
    const wrapper = mount(ChatMessageItem, {
      props: {
        message: message({
          content: "依据 [1]\n\n```python\nprint('ok')\n```\n\n| 课程 | 学时 |\n| --- | --- |\n| 电路 | 64 |",
          sources: [evidence],
        }),
      },
    });
    expect(wrapper.find("pre code.language-python").exists()).toBe(true);
    expect(wrapper.find("table").text()).toContain("电路");
    const reference = wrapper.find("a.evidence-ref");
    expect(reference.attributes("data-ref")).toBe("1");
    expect(reference.attributes("data-message-id")).toBe("assistant-1");
  });

  it("无证据提示保留，原始 HTML 不作为节点注入", () => {
    const wrapper = mount(ChatMessageItem, {
      props: { message: message({ content: "<img src=x onerror=alert(1)>" }) },
    });
    expect(wrapper.find(".chat-sources-empty").text()).toContain("参考资料不足");
    expect(wrapper.find("img").exists()).toBe(false);
  });

  it("错误与停止使用本地展示语气，不删除消息文本", () => {
    const error = mount(ChatMessageItem, {
      props: { message: message({ content: "请求失败", tone: "error" }) },
    });
    const stopped = mount(ChatMessageItem, {
      props: { message: message({ content: "（已停止生成）", tone: "stopped" }) },
    });
    expect(error.find(".chat-message-error").text()).toContain("请求失败");
    expect(stopped.find(".chat-message-stopped").text()).toContain("（已停止生成）");
  });
});
