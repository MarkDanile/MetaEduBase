# BUG-011 — AI Chat 偶发「请求失败: 网络错误」

> Status: 🟡 进行中
> Priority: P1
> Area: 前端 / P2 AI Chat
> Created: 2026-06-23

## 现象

用户在 AI Chat 输入「Python 的基本数据类型」，助手回复显示 `请求失败: 网络错误`，检索结果不可用。

## 复现与根因（2026-06-23 排查）

直连 `AIChatService.chat` 单测 9.88s 正常返回；HTTP `/api/v1/ai/chat/evidence` 实测：

- 首两次 curl（60s / 15s 超时）→ HTTP 000（无响应，超时）。
- 后续 curl → HTTP 200，耗时 10.8 / 18.6 / 21.1s（变量大）。
- `pg_stat_activity` 4 条连接均 `idle`（非 `idle in transaction`、无锁等待）→ DB 非瓶颈。

根因链：

1. 后端 `_call_llm` httpx 超时 = 60s（`ai_router.py:225`），检索 ~10s，端点合理耗时上限 ~70s。
2. 前端 axios 全局 `timeout = 30000`（`api.ts:5`）；AiChatView chat 调用仅传 `signal`，未覆盖单请求超时。
3. **30s < 60s**：任何耗时 30-70s 的 LLM/provider 抖动 → axios 30s 先超时 → `err.response` 缺失 → 回退 `?? "网络错误"`（`AiChatView.vue:342`）。

两处缺陷：(a) 前端超时短于后端自身 LLM 超时；(b) 「网络错误」误标超时。

## 完成标准

- AC-1：chat 请求单请求超时 ≥ 后端 LLM 60s + 检索余量（取 120s，与 `template.ts:111` 既有 120000 一致）。
- AC-2：超时与网络错误区分——超时显示「请求超时，请稍后重试」，不再误报「网络错误」。
- AC-3：`describeChatError` 抽为纯函数 + vitest 锁住 超时/网络/HTTP detail 三类映射。
- AC-4：`pnpm test` / `typecheck` / `lint` 通过；无回归。

## 非目标

- 不改后端 LLM/embedding 超时或 provider（外部抖动不在本 BUG 范围）。
- 不引入流式（SSE）输出（更大改动，登记 follow-up）。
- 不改检索/NER 行为。

## 验证方式

- vitest 单测覆盖 `describeChatError`。
- 手动 curl `/api/v1/ai/chat/evidence` 确认 200（已实证 10-21s）。
