import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const source = aiChatViewSource as string;

describe("AiChatView S2 layout contract", () => {
  it("保留 100dvh 移动视口高度，不回退 h-screen", () => {
    expect(source).toContain("height: 100dvh");
    expect(source).not.toContain("h-screen");
  });

  it("不再使用固定 pb-[88px] 猜测 Composer 高度", () => {
    expect(source).not.toContain("pb-[88px]");
  });

  it("Composer 处于 normal flow 底部，而非 sticky 覆盖消息", () => {
    expect(source).toContain('class="ai-chat-bottom"');
    expect(source).not.toContain("sticky");
  });

  it("消息滚动容器与 Composer 阅读列分离", () => {
    expect(source).toContain('ref="chatContainer"');
    expect(source).toContain('class="ai-chat-scroll"');
    expect(source).toContain('class="ai-chat-composer-column"');
    expect(source).toContain("@scroll=\"updateScrollState\"");
  });

  it("不在 LayoutView 的 main#main-content 内产生第二个 main landmark", () => {
    // 页面自身不渲染 <main>；消息区使用带可访问名称的 section。
    expect(source).not.toMatch(/<main[\s>]/);
    expect(source).toContain('aria-label="对话消息"');
    expect(source).toMatch(/<section[\s\S]*class="ai-chat-scroll"/);
  });

  it("消息内容容器被传给滚动 composable，用于尺寸变化时重新定位", () => {
    expect(source).toContain('ref="chatContent"');
    expect(source).toContain("useChatScroll(chatContainer, chatContent)");
  });
});
