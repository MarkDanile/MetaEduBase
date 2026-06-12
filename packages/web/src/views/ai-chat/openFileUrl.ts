/**
 * BUG-003 fix4 — `openFile` 行为抽取。
 *
 * 旧实现：`window.location.href = /resource/files/:fileId` —— 整页跳转，
 * 丢失 AI Chat 上下文，与 FileDetailView `?chunk=` chunk 锚点解析耦合。
 *
 * 新实现：
 * - `buildFileOpenUrl(fileId, chunkId?)` 纯函数：构造 `/resource/files/{id}`
 *   URL，chunkId 非空时附加 `?chunk={id}` 查询参数。
 * - `openInNewTab(url)` DOM helper：构造隐藏 `<a target="_blank"
 *   rel="noopener noreferrer">.click()`，避免弹窗拦截器（用户主动
 *   点击 / 调用由 click() 触发不被拦）；不调用 `window.open`。
 *
 * AC-5 真实行为由维护者人工点击验证；本模块 vitest 锁住 URL 构造 +
 * 隐藏 a 元素契约作为回归锁。
 */
export function buildFileOpenUrl(fileId: string, chunkId?: string | null): string {
  if (!fileId) {
    throw new Error("buildFileOpenUrl: fileId is required");
  }
  const base = `/resource/files/${fileId}`;
  if (!chunkId) {
    return base;
  }
  const params = new URLSearchParams();
  params.set("chunk", chunkId);
  return `${base}?${params.toString()}`;
}

export function openInNewTab(url: string): void {
  // 使用隐藏 <a> 触发而非 window.open：
  // - 用户主动上下文（点击 / 链接跳转）不会被浏览器弹窗拦截器拦下；
  // - `rel="noopener noreferrer"` 防止新页能 window.opener 反控旧页。
  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  // 隐藏但不 display:none —— display:none 在某些浏览器会被忽略 click。
  a.style.position = "absolute";
  a.style.left = "-9999px";
  a.style.width = "1px";
  a.style.height = "1px";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
