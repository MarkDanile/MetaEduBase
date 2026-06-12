/**
 * `AiChatView` — 首屏输入框布局测试（AC-1）。
 *
 * BUG-003 fix2：根容器 `h-screen` 改为 `h-[100dvh]`（mobile 浏览器
 * 100vh 含地址栏不准），输入区 wrapper `position: sticky; bottom: 0`
 * 固定在视口底部，聊天容器加 `pb-[88px]` 避免最后一条消息被遮挡。
 *
 * jsdom 不真实计算 layout，本测试不断言"元素是否在视口内"，只
 * 锁住 class 名称作为回归锁 — 后续若有人改回 `h-screen` / 移除 sticky /
 * 移除 pb-[88px]`，CI 必断。AC-1 真实截图（1366×768 / 1024×600 /
 * 360×640）由维护者人工验收，本 spec 只锁住 class 层契约。
 *
 * 使用 Vite `?raw` 导入拿模板原文，避免引入 `node:fs` / `node:path` /
 * `__dirname`，从而避免在 typecheck 引入 @types/node 依赖。
 */

import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const template = aiChatViewSource as string;

describe("AiChatView layout — BUG-003 fix2 AC-1", () => {
  it("根容器使用 h-[100dvh] 替代 h-screen（mobile 地址栏兼容）", () => {
    expect(template).toContain("h-[100dvh]");
    expect(template).not.toContain("h-screen");
  });

  it("聊天容器包含底部 pb-[88px] 偏移，避免被 sticky 输入区遮挡", () => {
    expect(template).toContain("pb-[88px]");
  });

  it("输入区 wrapper 含 sticky + bottom-0 + z-10 三件套", () => {
    expect(template).toContain("sticky");
    expect(template).toContain("bottom-0");
    expect(template).toContain("z-10");
  });

  it("输入区 wrapper 有 design token 的 bg-[var(--color-bg)] 避免消息透过", () => {
    expect(template).toContain("bg-[var(--color-bg)]");
  });
});

