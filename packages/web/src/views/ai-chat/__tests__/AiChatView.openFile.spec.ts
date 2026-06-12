/**
 * `AiChatView` — openFile 行为契约回归锁（AC-5）。
 *
 * BUG-003 fix4：`openFile` 改用隐藏 <a target="_blank">.click() 替代
 * 整页跳转；`openEvidenceFile` 在 evidence 无 file_id 时降级（不拼无
 * 意义 URL）。
 *
 * 真实点击 / 新标签打开 / chunk 锚点解析由维护者人工验收 + FileDetailView
 * `?chunk=` 监听负责；本 spec 锁住 source 字符串契约作为回归锁。
 */
import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const source = aiChatViewSource as string;

describe("AiChatView openFile behavior — BUG-003 fix4 AC-5", () => {
  it("不再用 window.location.href 整页跳转（必须删除）", () => {
    expect(source).not.toMatch(/window\.location\.href\s*=\s*`?\/resource\/files/);
  });

  it("openEvidenceFile 缺 file_id 时降级（必须有 console.warn 静默）", () => {
    // 防御性降级，避免 evidence.file_id 缺失时拼无意义 URL。
    expect(source).toMatch(/evidence\.file_id/);
    expect(source).toMatch(/console\.warn.*evidence has no file_id/s);
  });

  it("导入 openFileUrl helper（必须 import buildFileOpenUrl / openInNewTab）", () => {
    expect(source).toMatch(/import\s*\{[^}]*buildFileOpenUrl[^}]*\}\s*from\s*["']\.\/openFileUrl["']/);
    expect(source).toMatch(/import\s*\{[^}]*openInNewTab[^}]*\}\s*from\s*["']\.\/openFileUrl["']/);
  });
});
