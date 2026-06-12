/**
 * `AiChatView` — 中文 IME 兼容 + loading 错误态行为契约回归锁（AC-4）。
 *
 * BUG-003 fix5：
 * - <textarea> 加 @compositionstart / @compositionend 追踪 IME composing 状态；
 * - @keydown.enter 改调 onEnterKey 包装，composing=true 时不触发 sendMessage；
 * - chat-input 加 data-testid 便于测试 / 维护者定位。
 *
 * 真实中文输入法点击验证由维护者人工验收；本 spec 锁住 source 字符串契约
 * 作为回归锁——后续若有人改回无 IME 兼容的 @keydown.enter.exact.prevent=
  "sendMessage"，CI 必断。
 */
import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const source = aiChatViewSource as string;

describe("AiChatView IME compatibility — BUG-003 fix5 AC-4", () => {
  it("textarea 必须有 @compositionstart 监听 IME composing 开始", () => {
    expect(source).toMatch(/@compositionstart\s*=\s*"isComposing\s*=\s*true"/);
  });

  it("textarea 必须有 @compositionend 监听 IME composing 结束", () => {
    expect(source).toMatch(/@compositionend\s*=\s*"isComposing\s*=\s*false"/);
  });

  it("@keydown.enter 必须调 onEnterKey 包装（不再是直接 sendMessage）", () => {
    expect(source).toMatch(/@keydown\.enter\.exact\.prevent\s*=\s*"onEnterKey"/);
    // 旧直接绑定 sendMessage 必须在 textarea 块附近不再出现。
    const textareaIdx = source.indexOf("<textarea");
    const textareaEnd = source.indexOf("</textarea>");
    const textareaBlock = source.slice(textareaIdx, textareaEnd);
    expect(textareaBlock).not.toMatch(/@keydown\.enter\.exact\.prevent\s*=\s*"sendMessage"/);
  });

  it("onEnterKey 函数必须检查 isComposing=true 时 return（不 sendMessage）", () => {
    expect(source).toMatch(/function\s+onEnterKey\s*\(/);
    const fnStart = source.indexOf("function onEnterKey(");
    const fnEnd = source.indexOf("\n}", fnStart);
    const fnBody = source.slice(fnStart, fnEnd + 2);
    expect(fnBody).toMatch(/isComposing\.value/);
    expect(fnBody).toMatch(/return\s*;/);
  });

  it("isComposing 必须在 setup 顶层 ref 声明", () => {
    expect(source).toMatch(/const\s+isComposing\s*=\s*ref\(false\)/);
  });

  it("textarea 加 data-testid=chat-input 便于测试定位", () => {
    expect(source).toMatch(/data-testid=["']chat-input["']/);
  });
});
