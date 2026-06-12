/**
 * `openFileUrl` — BUG-003 fix4 AC-5 行为锁。
 *
 * - buildFileOpenUrl: URL 构造 + chunk 锚点 + 空 fileId 报错。
 * - openInNewTab: 隐藏 <a target="_blank" rel="noopener noreferrer">.click()
 *   替代 window.open / window.location.href，避免弹窗拦截 + 整页跳转。
 *
 * AC-5 真实点击验证由维护者人工验收；本 spec 锁住 URL 构造 + DOM
 * helper 契约作为回归锁。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildFileOpenUrl, openInNewTab } from "../openFileUrl";

describe("buildFileOpenUrl — BUG-003 fix4 AC-5", () => {
  it("无 chunkId 时 URL 不带 query", () => {
    expect(buildFileOpenUrl("file-abc")).toBe("/resource/files/file-abc");
  });

  it("有 chunkId 时附加 ?chunk={id} 查询参数", () => {
    expect(buildFileOpenUrl("file-abc", "chunk-xyz")).toBe(
      "/resource/files/file-abc?chunk=chunk-xyz"
    );
  });

  it("chunkId 为空字符串时视作无 chunk", () => {
    expect(buildFileOpenUrl("file-abc", "")).toBe("/resource/files/file-abc");
  });

  it("chunkId 为 null 时视作无 chunk", () => {
    expect(buildFileOpenUrl("file-abc", null)).toBe("/resource/files/file-abc");
  });

  it("fileId 为空字符串时抛错", () => {
    expect(() => buildFileOpenUrl("")).toThrow(/fileId is required/);
  });
});

describe("openInNewTab — BUG-003 fix4 AC-5", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("构造隐藏 <a target=_blank rel=noopener noreferrer> 并 click()", () => {
    // 通过 spy 拦截 click 实现：拦截瞬间元素还在 body 上；
    // 之后 openInNewTab 才会 removeChild。
    // 关键：用闭包变量捕获元素，避免 this-alias lint 规则。
    let captured: HTMLAnchorElement | null = null;
    const origAppend = document.body.appendChild.bind(document.body);
    const appendSpy = vi
      .spyOn(document.body, "appendChild")
      .mockImplementation((node: Node) => {
        // 拦截 appendChild 期间记录当前 a；click 还没发生。
        if (node instanceof HTMLAnchorElement) {
          captured = node;
        }
        return origAppend(node);
      });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click");
    openInNewTab("/resource/files/file-abc?chunk=chunk-xyz");

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(captured).not.toBeNull();
    const a = captured as unknown as HTMLAnchorElement;
    expect(a.target).toBe("_blank");
    expect(a.rel).toBe("noopener noreferrer");
    expect(a.href).toContain("/resource/files/file-abc");
    expect(a.href).toContain("chunk=chunk-xyz");

    // 隐藏 a 在 click 后应被移除，避免 document.body 累积
    expect(document.body.contains(a)).toBe(false);
    appendSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it("不调用 window.open，避免弹窗拦截器", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    openInNewTab("/resource/files/file-abc");
    expect(openSpy).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });
});
