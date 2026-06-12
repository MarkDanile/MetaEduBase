# BUG-003 AI Chat 体验与回答质量回归 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-12-bug-003-ai-chat-regression.md`
> Bug: `docs/01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md`
> Branch: `fix/bug-003-ai-chat-regression`（docs-only 首切片入口；后续 4-5 个修复合片走 fix/bug-003-ai-chat-regression-fix{N} 之类新分支）

## 总体节奏

本计划对应 5 个修复合片（PR-BUG-003-1 ~ PR-BUG-003-5）+ 1 个 docs-only 入口 PR（本 PR）。5 个修复合片**互相独立、可以串行推**，不建议并行——共享 AiChatView / ai_chat_service 文件会导致高频冲突。每个 PR 单独走完整 Git 闭环。

| 顺序 | 切片 | 类型 | 依赖 | 文件范围 |
|------|------|------|------|----------|
| 1 | PR-BUG-003-0 (本 PR) | docs-only | 无 | `docs/03-engineering-governance/current-work.md` + `docs/01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md` + `docs/02-delivery-plans/01-specs/2026-06-12-bug-003-ai-chat-regression.md` + `docs/02-delivery-plans/02-plans/2026-06-12-bug-003-ai-chat-regression-plan.md` |
| 2 | PR-BUG-003-1 (backend) | fix | 无 | `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py` + `pg_chunk_keyword_retriever.py` + `ai_chat_service.py`（仅 `_safe_retrieve_*` 兜底） |
| 3 | PR-BUG-003-2 (frontend layout) | fix | 无 | `packages/web/src/views/ai-chat/AiChatView.vue`（首屏布局）+ 可选 `packages/web/src/components/EmptyState.vue`（不改） |
| 4 | PR-BUG-003-3 (frontend reference UI) | fix | 无 | `packages/web/src/components/DocumentSourceList.vue`（视觉强化） + `AiChatView.vue`（quickQuestion `type="button"`） |
| 5 | PR-BUG-003-4 (frontend file open) | fix | 无 | `packages/web/src/views/ai-chat/AiChatView.vue`（`openFile` 改新标签 + 锚点 + 降级）+ `packages/web/src/views/resource/FileDetailView.vue`（不动，验证 `?chunk=` 解析） |
| 6 | PR-BUG-003-5 (frontend fallback) | fix | 无 | `packages/web/src/views/ai-chat/AiChatView.vue`（中文 IME 兼容 + loading 错误态） |

---

## 切片 0：入口 PR（docs-only）— 本 PR

**目标**：登记 BUG-003 任务卡片、追加复现切片记录、提交 spec/plan，作为后续 4-5 个修复合片的入口。

**Scope**：
- `docs/03-engineering-governance/current-work.md`：BUG-003 从"下一批候选任务"移入"当前进行中"，状态 `🟡 进行中`。
- `docs/01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md`：在"2026-06-12 初步排查记录"段后追加"2026-06-12 复现切片记录（fix/bug-003-ai-chat-regression 分支）"段，含 4 个子问题真因候选、复现条件、5 个修复合片分组。
- 新增 `docs/02-delivery-plans/01-specs/2026-06-12-bug-003-ai-chat-regression.md`：本文件。
- 新增 `docs/02-delivery-plans/02-plans/2026-06-12-bug-003-ai-chat-regression-plan.md`：本文件。

**Validation**：
- `scripts/check-engineering-docs` 退出码 0。
- `git diff --check` clean。
- 0 业务代码变更；0 测试代码变更；0 脚本变更。
- `git status --short` 只显示本任务相关 4 个文件。

**Risks**：
- BUG 文档追加段落可能触发 L37 / L40 / L44 现有"最近完成"行重写规则的误判（最长 220 字符等），本切片不涉及"最近完成"区段，无影响。
- `current-work.md` L19 的"当前进行中"区段需补一行 BUG-003 卡片；行长度需符合 `check-engineering-docs` 现有规则。

**Out of Scope**：
- 不改业务代码。
- 不动其他事实源（`technical-debt.md` / `work-log.md` / `review-scorecard.md`）。

---

## 切片 1：PR-BUG-003-1 backend evidence pipeline

**目标**：保证 chunk vector / chunk keyword / full-text 通道稳定返回正文 chunk，fused 不再全是 knowledge_node。

**Scope**：
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`：把"embedding 为空时 return []" 改为"embedding 为空时降级到 keyword retriever 同一查询（仍走 `chinese_zh` tsvector）"；如果 keyword 也无结果才 return []。日志保留 `empty embedding` 警告。
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_keyword_retriever.py`：在 retrieve 入口新增 `session_factory` 参数（如未传则用 `session`），但本切片**最小改动**是不动这块，把跨 session 冲突解决放到 `ai_chat_service._retrieve` 阶段。
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`：
  - `_retrieve` L288-290 的 `asyncio.gather` 改为串行执行（`await chunk_coro; await graph_coro`），避免共享 AsyncSession 并发；
  - 或：把 `chunk_retriever` + `graph_retriever` 调用都包在独立 `async with self.session_factory()` 里（这需要改 `chat()` 签名，新增 `session_factory`，工作量大）。
  - 推荐最小改动：先尝试串行；如性能下降明显，下一迭代再改 session_factory。
- 新增 pytest：`tests/contexts/knowledge/application/test_ai_chat_service_retrieve_serial.py`——验证 `chunk_retriever` 失败时 `graph_retriever` 仍能返回，且最终 fused 至少有 1 条 `source_type="chunk"`。
- 新增 pytest：`tests/contexts/knowledge/infrastructure/retrievers/test_pg_chunk_vector_embedding_fallback.py`——验证 embedding 空时降级到 keyword。

**Validation**：
- `cd packages/server-python && make test`（或 pytest 等价命令）— 验证新测试通过 + 零回归。
- `make lint` — 0 警告。
- 真实 PG 库上 `curl -X POST /api/v1/ai/chat/evidence -d '{"message": "Python 的基本数据类型有哪些？", "context_window": 5}'` — 记录返回的 `sources` / `document_sources` 摘要到 PR 描述。

**Risks**：
- 串行 `asyncio.gather` 改写可能延长端到端 latency（chunk + graph 各 ~200ms → 总 ~400ms），但因为之前本机 chunk 通道直接 fail，串行更稳。
- embedding 降级到 keyword 可能在某些 embed-only 库（如纯图片描述）上退化，但本 BUG 关注的是 Python 文本操作指南，文本库 keyword 通道可用。
- 串行改动可能影响 RAG e2e 测试的 latency 断言；需 review `tests/e2e/` 是否有相关断言。

**Out of Scope**：
- 不动 embedding service 配置 / 密钥（属部署环境）。
- 不重构 `AIChatService` 编排。
- 不重做 `PgGraphRetriever` 内部 vector + keyword channel 的并发（这个属于另一层并发；本切片优先解决 service 层并发，graph 内部并发在 graph_retriever 自己的 TD 里处理）。

---

## 切片 2：PR-BUG-003-2 frontend layout

**目标**：AI Chat 首屏输入框在 1366×768 / 1024×600 / 360×640 视口下都可见。

**Scope**：
- `packages/web/src/views/ai-chat/AiChatView.vue`：
  - 根容器 `h-screen` 改为 `h-[100dvh]`（mobile 浏览器 100vh 含地址栏不准，100dvh 是动态视口）；
  - 或：在输入区 `border-t` 容器加 `position: sticky; bottom: 0; z-index: 10` + `background-color: var(--color-bg)`，确保滚动聊天容器时输入区始终固定可见；
  - 推荐**最小改动**：把根容器加 `min-h-[100dvh] overflow-hidden`，聊天容器加 `pb-[80px]` 避免最后一条消息被输入区遮挡，输入区 `position: sticky; bottom: 0`。
- 新增或扩展 vitest 组件测试：`packages/web/src/views/ai-chat/__tests__/AiChatView.layout.spec.ts`——使用 `@vue/test-utils` mount 组件，断言：
  - 桌面 1280×720：textarea 在视口内可见；
  - mobile 360×640：textarea 在视口内可见；
  - DevTools 模拟 small height (1280×400)：textarea 仍可见。

**Validation**：
- `pnpm --filter @metaedu/web lint` 0 警告。
- `pnpm --filter @metaedu/web typecheck` 退出码 0。
- `pnpm --filter @metaedu/web test` 新增测试通过。
- 浏览器手动验收 3 个视口：截图保留到 PR 描述（"AC-1 验收：1366×768 / 1024×600 / 360×640 截图"）。

**Risks**：
- `position: sticky` 在某些 flex 子元素上失效，需确认根容器是 `flex flex-col` 不带 `overflow-hidden`。
- `100dvh` 在 Safari 15.4 以下不支持，但本项目 desktop 浏览器应已满足。
- 修改 layout 可能影响其他 view（已发现 AdminView / KnowledgeBaseView / ResourceView / SkillEditorView 也用 EmptyState + flex-col 模式）；本切片**只动 AiChatView**，其他 view 各自 owner 后续接力。

**Out of Scope**：
- 不动 EmptyState 组件。
- 不重做 AI Chat 整体 UI。

---

## 切片 3：PR-BUG-003-3 frontend reference UI

**目标**：底部"参考来源"区视觉强化，按钮 `type="button"` 显式化。

**Scope**：
- `packages/web/src/components/DocumentSourceList.vue`：
  - 外层容器加 `border-l-2 border-[var(--color-accent)] pl-3`（左侧色条视觉强调）；
  - 标题区加 `text-[var(--text-micro)] text-[var(--color-ink-tertiary)] uppercase tracking-wider`（已有，验证即可）；
  - 卡片加 `hover:shadow-sm` 增强交互感；
  - chunk 列表加 `data-testid="document-source-chunk"` 便于测试定位。
- `packages/web/src/views/ai-chat/AiChatView.vue`：
  - L25-32 三个 quickQuestion 按钮加 `type="button"`；
  - L46 `<div :class="[..., '...markdown-body']">` 容器下，"参考来源"标题区加 `text-[var(--text-micro)] text-[var(--color-accent)]` 视觉层级（与 L68 现有的 `text-ink-tertiary` 区分）。
- 新增 vitest：`packages/web/src/views/ai-chat/__tests__/AiChatView.quickQuestionType.spec.ts` — 断言 quickQuestion 按钮是 `type="button"`。
- 新增 vitest：`packages/web/src/components/__tests__/DocumentSourceList.aria.spec.ts` — 断言外链按钮有 `aria-label="查看文档"`、chunk 按钮有 `aria-label="定位到该 chunk"`。

**Validation**：
- `pnpm --filter @metaedu/web lint` + `typecheck` + `test` 全过。
- 浏览器手动验收：截图保留到 PR 描述。

**Risks**：
- 视觉改动可能与现有 design system token 不一致；按 `coding-style.md` 用 CSS 变量，不写死 hex。

**Out of Scope**：
- 不重做 DocumentSourceList 的 props/emit 契约。

---

## 切片 4：PR-BUG-003-4 frontend file open

**目标**：`openFile` 改新标签 + 保留 `?chunk=` 锚点 + 降级文案；evidence-ref 引用与外链行为对齐。

**Scope**：
- `packages/web/src/views/ai-chat/AiChatView.vue`：
  - `openFile` (L340-345) 改为：构造一个隐藏 `<a>` 元素，`target="_blank" rel="noopener noreferrer"`，`click()` 后销毁；或者直接 `window.open(url, "_blank", "noopener,noreferrer")`；
  - 增加降级：若 `evidence.file_id` 缺失（unattributedSources），`openEvidenceFile` 不再 `window.location.href` 到无意义 URL，改为 toast 提示"该证据暂未关联文件"；
  - `marked` renderer (L206-211) 的 link 处理：保持 `target="_blank"`，**改为与 evidence-ref 同样的 chunk 锚点解析**——即若 `href` 命中 `/resource/files/:id` 形式，附加 `?chunk=` query；
  - `openDocumentSourceChunk` 已传 chunkId，验证 chunk 锚点解析是否生效（FileDetailView L128-134 已实现）。
- 新增 vitest：`packages/web/src/views/ai-chat/__tests__/openFile.behavior.spec.ts` — 断言 `openFile(fileId, chunkId)` 构造的 URL 是 `/resource/files/{fileId}?chunk={chunkId}`，且使用 `window.open` / 隐藏 `<a>` 路径（mock `window.open` 验证）。

**Validation**：
- `pnpm --filter @metaedu/web lint` + `typecheck` + `test` 全过。
- 浏览器手动验收：
  - 点击 `[1]` / `[2]` / `[3]` → 新标签打开文件详情 + 滚到 chunk。
  - 点击底部"参考来源"卡片标题 → 新标签打开文件详情。
  - 点击底部"参考来源"片段 → 新标签打开文件详情 + 滚到 chunk。
  - 截图保留到 PR 描述。

**Risks**：
- 浏览器弹窗拦截器可能拦 `window.open`（若不是用户主动点击）；用隐藏 `<a>.click()` 替代是稳妥方案。
- `marked` renderer 改 link 处理可能影响外部 URL（http://...）行为；需要保留 `isSafeLink` 校验。

**Out of Scope**：
- 不动 FileDetailView。
- 不重做文件详情页 chunk 锚点高亮。

---

## 切片 5：PR-BUG-003-5 frontend fallback（**真因待真实点击复现**）

**目标**：兜底问题"页面刷新"——补中文 IME 兼容 + loading 错误态可视化。

**Scope**：
- `packages/web/src/views/ai-chat/AiChatView.vue`：
  - `<textarea>` 改 `@keydown.enter.exact` 为自定义 IME 状态探测：监听 `compositionstart` / `compositionend` 事件，在 IME 输入中（`composing=true`）放过 Enter，仅在非 IME 状态拦截 Enter；或使用 `keydown` 事件检查 `event.isComposing` / `event.keyCode === 229`。
  - `sendMessage` 失败 catch 块 (L312-328) 改：不再 push 一条 assistant 消息，改为把错误 toast 出来 + 在 UI 上显示"网络错误，请重试"占位条。
  - input 区域加 `data-testid="chat-input"` 便于手动验证。
- 新增 vitest：`packages/web/src/views/ai-chat/__tests__/sendMessage.ime.spec.ts` — 模拟 IME composing 状态，断言 Enter 不会触发 `sendMessage`。

**Validation**：
- `pnpm --filter @metaedu/web lint` + `typecheck` + `test` 全过。
- 真实浏览器验收：
  - 中文输入法打"你能回答什么问题？"过程中按 Enter 选词 → 不触发 sendMessage；
  - 选完词后再按 Enter → 触发 sendMessage；
  - loading 状态下快速点击 Send 按钮 → 不重复提交；
  - `/api/v1/ai/chat/evidence` 503 → toast 提示 + 输入框仍可编辑。

**Risks**：
- IME 兼容在 macOS / Windows / iOS 浏览器表现不同，需多平台验证。
- 错误态改动可能与现有 toast 组件冲突；需 review `useToast` composable 行为。

**Out of Scope**：
- 不重做 AI Chat 错误处理机制（保留现有 try/catch 模式）。

---

## 完成判定

5 个修复合片（PR-BUG-003-1 ~ PR-BUG-003-5）**全部**合 main 后：

1. `gh pr view <每个 PR> --json state` state 全部为 MERGED。
2. 工作台 BUG-003 卡片从"当前进行中"移入"最近完成"。
3. BUG 文档 7 个 AC 全部打勾（AC-1 ~ AC-7）。
4. work-log 索引追加一行。
5. 翻 `🟢 完成`。

任意一个 PR 未合 main，BUG-003 保持 `🟡 进行中` 或 `🟣 待验证`，不得翻 `🟢 完成`（见 `workbench.md#状态同步规则`）。

---

## 验证矩阵（首切片入口 PR）

| 验证项 | 命令 | 预期 |
|--------|------|------|
| 文档门禁 | `scripts/check-engineering-docs` | 退出码 0 |
| 范围 | `git diff --name-status` | 仅 4 个文档文件 |
| 状态 | `git status --short --branch` | 干净，仅 staged 文件 |
| 静态 | `git diff --check` | clean |
| 业务代码 | 0 变更 | 0 业务代码 / 0 测试代码 / 0 脚本 |
