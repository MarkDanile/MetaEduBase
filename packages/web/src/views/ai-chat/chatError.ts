/**
 * BUG-011 — AI Chat 错误信息归因。
 *
 * 旧实现：catch 块直接 `请求失败: ${err.response?.data?.detail ?? "网络错误"}`。
 * 问题：前端 axios 全局 timeout=30s < 后端 `_call_llm` 60s + 检索 ~10s；慢
 * LLM/provider 抖动（30-70s）触发前端先超时，此时 `err.response` 缺失 →
 * 回退「网络错误」，把超时误报为网络错误，误导用户。
 *
 * `describeChatError` 纯函数：按 axios 错误形态区分
 * - 超时（`code === "ECONNABORTED"` 且无 response）→ 「请求超时，请稍后重试」
 * - 后端返回 detail → 「请求失败: {detail}」
 * - 真网络错误（无 response、非超时）→ 「网络连接失败，请检查网络后重试」
 *
 * vitest 锁住三类映射作为回归锁；用户中止（CanceledError/AbortError）仍由
 * AiChatView 调用方单独处理，不进本函数。
 */
export interface ChatErrorShape {
  code?: string;
  message?: string;
  response?: {
    status?: number;
    data?: { detail?: string | { code?: string; message?: string } };
  };
}

const DURABLE_PENDING_CODES = new Set([
  "direct_rag_turn_pending",
  "direct_rag_execution_pending",
  "direct_rag_output_pending",
]);

export function shouldPreserveRequestIdentity(err: ChatErrorShape): boolean {
  if (!err.response) return true;
  const detail = err.response.data?.detail;
  return Boolean(
    detail
    && typeof detail === "object"
    && detail.code
    && DURABLE_PENDING_CODES.has(detail.code),
  );
}

export function describeChatError(err: ChatErrorShape): string {
  // axios 超时：code=ECONNABORTED，无 response（请求未拿到任何响应）
  if (err.code === "ECONNABORTED" && !err.response) {
    return "请求超时，请稍后重试";
  }
  const detail = err.response?.data?.detail;
  if (typeof detail === "string" && detail) {
    return `请求失败: ${detail}`;
  }
  if (detail && typeof detail === "object") {
    const message = detail.message || detail.code;
    if (message) return `请求失败: ${message}`;
  }
  // 有响应但无 detail（如 502/网关），或无响应且非超时（连接拒绝/DNS/CORS）
  return "网络连接失败，请检查网络后重试";
}
