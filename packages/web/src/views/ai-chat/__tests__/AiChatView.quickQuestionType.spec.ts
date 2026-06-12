/**
 * `AiChatView` — quickQuestion 按钮 type 显式化回归锁。
 *
 * BUG-003 fix3 (AC-4 真因候选之一)：quickQuestion 按钮在 `<form>` 内
 * 不显式声明 `type="button"`，HTML 规范默认 `<button>` 是 `type="submit"`，
 * 配合 @submit.prevent 不会真刷新但属于规范违例。fix3 显式 type="button"
 * 化，避免隐式 submit 风险。
 *
 * 真实按钮的浏览器行为需人工点击验证，本 spec 锁住 template class
 * 字符串作为回归锁——后续若有人改回无 type 显式声明的 button，CI 必断。
 */
import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const template = aiChatViewSource as string;

describe("AiChatView quickQuestion buttons — BUG-003 fix3 AC-4", () => {
  it("quickQuestion 按钮必须有 type=button 显式声明", () => {
    // quickQuestion 区在 v-for 块内，按钮 class 包含 ui-panel。
    // 找 @click=sendQuick 前后 200 字符内必须含 type="button"。
    const idx = template.indexOf('sendQuick(q)');
    expect(idx).toBeGreaterThan(-1);
    const window = template.slice(Math.max(0, idx - 200), idx + 200);
    expect(window).toMatch(/type=["']button["']/);
  });
});
