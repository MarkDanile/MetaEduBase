# BUG-003: AI Chat 体验与回答质量回归

Status: 🔵 Ready
Priority: P1
Milestone: P1
Source: 用户真实 AI Chat 使用反馈 / REQ-012 合并后复核

## 背景

REQ-012 已完成 RAG 多路召回、文档级参考来源和引用点击的第一轮收口，但真实页面使用仍出现明显回归：

- AI Chat 页面第一屏默认看不到底部输入框，用户进入页面后不能立即提问。
- 针对“python 的基本数据类型”这类文档中存在原文的问题，回答仍主要引用目录片段，并给出“未找到足够参考来源”的结论。
- 询问“你能回答什么问题？”时页面直接刷新或无有效反馈。
- 回答中的 `[1]` / `[2]` / `[3]` 和底部参考文档链接点开后不可阅读；底部“参考来源”视觉上也不像可用引用来源。

## 复现路径

1. 打开 AI Chat 页面。
2. 观察第一屏是否能直接看到输入框。
3. 输入“python 的基本数据类型”或“Python 的基本数据类型有哪些？”。
4. 检查回答是否命中文档正文中的基础类型内容，而不是只命中目录。
5. 点击回答正文中的 `[1]` / `[2]` / `[3]`。
6. 点击底部参考文档链接或参考来源卡片。
7. 输入“你能回答什么问题？”并提交。

## 期望行为

- 第一屏可直接看到输入框；输入区应固定在可见区域底部或通过布局保证无需滚动即可提问。
- Python 基本数据类型类问题应优先命中文档正文 chunk，并给出有来源支撑的清晰答案。
- 兜底类问题不能刷新页面；应返回能力说明、可提问范围或明确错误反馈。
- 回答正文引用编号可点击并定位到当前回答对应证据。
- 底部参考来源按文档展示，视觉上像引用区；点击文档后能进入可阅读页面，点击片段后能定位到对应 chunk 或给出清晰降级。

## 初步怀疑点

- Frontend：
  - `packages/web/src/views/ai-chat/AiChatView.vue` 页面高度、滚动容器和输入区布局可能导致输入框被第一屏挤出。
  - 表单提交或按钮类型可能导致“你能回答什么问题？”触发页面刷新。
  - `openFile(...)` 当前使用 `window.location.href = /resource/files/:fileId`，可能与实际路由或新标签阅读预期不一致。
  - `DocumentSourceList.vue` 的参考来源交互可能缺少清晰的引用 UI 和可读性反馈。
- Backend / Retrieval：
  - evidence 召回可能仍偏向目录 chunk，正文 chunk 排序不足。
  - prompt context 可能没有把与“基本数据类型”最相关的正文 chunk 给到 LLM。
  - 需要用真实问题记录 evidence、document_sources、prompt 摘要和回答质量，不能只依赖单元测试。

## 2026-06-12 初步排查记录

针对“Python 的基本数据类型有哪些？”在本机 `metaedu` 库做了两类只读探针：

1. 直接查 `document_chunks`，确认库里存在可回答该问题的正文 chunk：
   - `Python教程-廖雪峰-2025-06-16.pdf` chunk 51 “数据类型和变量”：包含 `Python还提供了列表、字典等多种数据类型...变量不仅可以是数字，还可以是任意数据类型`。
   - chunk 52 “数据类型和变量”：包含 `a = 123 # a是整数`、`a = 'ABC' # a变为字符串`、动态语言说明。
   - chunk 56 “数据类型和变量”：包含 `Python支持多种数据类型...整数没有大小限制...`。
   - 也存在目录 chunk 0，包含 `5.1. 数据类型和变量`、`5.2. 字符串和编码`、`5.3. 使用list和tuple`、`5.7. 使用dict和set`。

2. 拦截 `AIChatService.chat()` 调 LLM 前的 `user_content`，发现真实给大模型的 evidence 主要是 `knowledge_node` 和目录 chunk：
   - `PgChunkVectorRetriever` 打印 `empty embedding`，说明当前环境未拿到 embedding，向量 chunk 通道为空。
   - `PgChunkKeywordRetriever` 报错 `This session is provisioning a new connection; concurrent operations are not permitted`，说明 chunk keyword 与 graph 并发共享同一个 SQLAlchemy `AsyncSession` 时失败，导致正文 chunk keyword 召回没有进入 fusion。
   - 最终 sources 为 5 条，全部是 `knowledge_node`；其中 2 条没有正文内容，2 条回源到 Python 教程目录 chunk，1 条误入“导数 / Python 梯度下降”教学材料。
   - prompt 中的参考证据包含目录和无内容知识节点，没有包含 chunk 51 / 52 / 56 的正文解释，所以模型只能根据目录保守回答“证据不足”。

初步结论：

- 当前主要问题不是 LLM “不聪明”，而是 evidence pipeline 给到 LLM 的上下文不足且偏离正文。
- REQ-012 接入了 chunk keyword retriever，但真实链路存在并发 session 失败，导致该通道在本机请求中没有生效。
- `context_window: 5`、`snippet=content[:200]` 和严格 system prompt 叠加，会进一步放大“证据不足”的倾向。
- 修复优先级应先保证 chunk keyword / full-text 通道稳定返回正文 chunk，再调整 prompt context 打包和“证据不足”策略。

## 2026-06-12 复现切片记录（fix/bug-003-ai-chat-regression 分支）

本节是按 BUG 文档「后续执行建议」30 分钟复现切片的代码审阅+已知证据汇总，分支：`fix/bug-003-ai-chat-regression`。本切片**只新增文档证据，不改业务代码**，完整 4-5 个修复合片按对应 spec/plan 走独立 PR。

### 复现 1：AC-1 输入框第一屏

- 模板根容器 `packages/web/src/views/ai-chat/AiChatView.vue:2` `class="flex flex-col h-screen"`，聊天容器 `:17` `ref="chatContainer" class="flex-1 overflow-y-auto ..."`，输入区 `:101-133` 是独立 `border-t` + `<form @submit.prevent="sendMessage">`。
- 真因候选：聊天容器与输入区都是 `flex-col` 直接子节点；**桌面视口 ≥ 768px** 时 `h-screen` 通常足够，输入区不会跑出首屏；但当浏览器缩放、DevTools 打开或 small height（< 600px）时，**`EmptyState` (L18-35) 的 grid + hint + 标题在聊天容器内独立滚动，输入区在 flex-col 末端被遮**，视觉上输入框消失。复现条件：viewport 高 < 600px + 加载 AI Chat 路由。
- 真实浏览器验证：本切片未跑浏览器，仅代码审阅 + BUG 文档历史现象。修复合片需补 playwright/手动截图验收。

### 复现 2：AC-4 兜底问题"页面直接刷新"

- 真因候选 1：`<form @submit.prevent="sendMessage">` (L102) 已拦截隐式 submit；`<textarea @keydown.enter.exact.prevent="sendMessage">` (L111) 已拦 Enter；quickQuestions 按钮 (L25-32) **未显式 `type="button"`**——在 `<form>` 内 `<button>` 默认 `type="submit"`，但因为 `@submit.prevent`，点击只会触发 `sendMessage` 而不会真刷新；不过这违反了"按钮必须显式 type"的工程规范，需顺手修。
- 真因候选 2：**中文 IME 输入兼容**。用户用中文输入法打"你能回答什么问题？" 时，候选词阶段按 Enter 是 IME 确认字符，但 `@keydown.enter.exact.prevent` 不会区分 IME 状态，可能在某些输入状态下把 IME Enter 当作 sendMessage 触发，触发 loading → `/ai/chat/evidence` 后端 503/网络错 → "请求失败" 走 L321-327 → 视觉上看似"刷新"。
- 真因候选 3：**输入空字符串 + Send 按钮 disabled 校验绕过**。L127 `:disabled="!inputText.trim()"` 拦了空文本，但 `sendMessage` L276-277 又做了一次 `if (!text || loading.value) return`——属于重复校验，符合现状。
- **结论**：30 分钟切片阶段不在此分支敲定真因，需要真实浏览器点击 + 中文 IME 测试；本切片**只记录真因候选**，交修复合片覆盖。

### 复现 3：AC-5 / AC-6 引用可读性 + 参考来源 UI

- AC-5 真因已锁定：`packages/web/src/views/ai-chat/AiChatView.vue:340-345` `openFile` 使用 `window.location.href = /resource/files/:fileId` —— **整页跳转而非新标签**，且 `chunk=` 参数通过 URLSearchParams 拼上但目标文件详情页 `FileDetailView.vue:128-134` 监听 `route.query.chunk` 滚到 chunk 锚点这一路径**确实存在**；用户体感"链接打不开"的最大可能：(a) 整页跳丢失 chat 上下文，且 (b) `?chunk=` 路由参数在新版可能因 query 序列化差异失效、(c) 文件详情页 `chunk` 锚点跳转后高亮 3s 清除前未持久化。
- AC-6 真因已锁定：`openDocumentSource` (L354-356) 跳文件详情页不传 chunkId；`DocumentSourceList.vue` 模板里**外链按钮 (:50-53) 和标题按钮 (:23-29) 都 emit `open-document`**，而 quickQuestions 区 3 个按钮在 EmptyState slot 内不属于 form，所以不刷页——但视觉上"参考来源"区域是 `border` + `bg-warm` 的 `ui-panel`，与上方 markdown 气泡视觉差异不明显，BUG 文档说的"视觉上不像引用来源"成立。
- 复现补充：`<a>` 链接通过 marked 渲染时 (L206-211) **不会**走 `.evidence-ref` 后处理；正文内若有原生 markdown `\[label\](http://...)` 链接，会按 `target="_blank"` 打开——这与 `.evidence-ref` 的"原页跳转"行为不一致。属于"用户体感链接行为不一致"。

### 复现 4：AC-2 / AC-3 答案质量（已 100% 锁定真因）

- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py:36-39` `get_embedding(query)` 返回空 → logger.warning `empty embedding` → 直接 `return []`。本机环境未拿到 embedding（推测：embedding service 不可达 / 密钥未配 / 限流），导致 vector chunk 通道空。
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_keyword_retriever.py:93` `await session.execute(...)` 在 chunk + graph **共享同一个 AsyncSession** 时，SQLAlchemy 2.x async 引擎报 `This session is provisioning a new connection; concurrent operations are not permitted`。`ai_chat_service.py:288-290` `asyncio.gather(chunk_coro, graph_coro)` 并发触发该错误（已经在 `_safe_retrieve_*` 兜底了）——但 BUG 文档 2026-06-12 排查记录中"报错 ... 共享同一个 SQLAlchemy AsyncSession 时失败" 提示**这条报错实际是发生在 graph 端**（`PgGraphRetriever` 内部又用同一个 session 跑 vector + keyword 两个 channel），导致 keyword channel 失败。
- 复现汇总：`get_embedding` 空 + 内部 keyword channel 共享 session 失败 → 最终 fused 全是 `knowledge_node` (5 条) → 2 条空 content、2 条目录 chunk、1 条无关文档 → prompt 证据只含目录/空内容 → LLM 给"证据不足" 兜底。
- **结论**：AC-2/AC-3 真因已 100% 锁定，可直接进入修复合片。

### 30 分钟复现切片结论

- 4 个子问题中，AC-2/AC-3 (backend evidence pipeline) 真因已 100% 锁定，可直接修；
- AC-1 / AC-5 / AC-6 真因已**强候选锁定**（前端布局 + 整页跳转 + 引用 UI）；
- AC-4 真因**未锁定**（中文 IME 兼容 + 空 input 兜底需要真实浏览器点击验证）；
- 建议 5 个修复合片分组：
  1. **PR-BUG-003-1 (backend)**：修复 `PgChunkVectorRetriever` 空 embedding 兜底 + `PgChunkKeywordRetriever` 跨 session 并发（拆 session / 串行 / 加 connect），保证 chunk keyword 通道返回正文 chunk。
  2. **PR-BUG-003-2 (frontend layout)**：AI Chat 首屏输入框固定可见（mobile/small viewport 兼容）。
  3. **PR-BUG-003-3 (frontend reference UI)**：参考来源区视觉强化（标题/计数/分块/缩略图），按钮 `type="button"` 显式化。
  4. **PR-BUG-003-4 (frontend file open)**：`openFile` 改新标签 (`window.open`) + 保留 `?chunk=` 锚点 + 补充降级文案。
  5. **PR-BUG-003-5 (frontend fallback)**：兜底问题"页面刷新"——补中文 IME 兼容 + loading 错误态可视化（属于"待真实点击复现后定真因"）。
- 每个 PR 单独验证（前端 lint/typecheck/test，后端 pytest），合 main 后翻 BUG-003 为 `🟢 完成`。

## 验收标准

- AC-1：AI Chat 页面在常见桌面视口首屏可见输入框，输入区不被页面内容挤出；补前端布局测试或截图验收记录。
- AC-2：“Python 的基本数据类型有哪些？”在现有 Python 操作指南数据下能命中正文 chunk，并回答整数、浮点数、字符串、布尔值、列表、元组、字典、集合等相关内容；若文档实际口径不同，以文档原文为准。
- AC-3：回答质量验收必须记录实际返回的 `sources` / `document_sources` / 命中通道 / 关键 chunk 摘要。
- AC-4：“你能回答什么问题？”提交后页面不刷新；有明确 assistant 反馈或错误态。
- AC-5：正文 `[N]` 引用点击不越界、不错位，并能打开或定位到对应证据；无法定位时有明确降级提示。
- AC-6：底部参考来源一级为文档引用区，样式上能被识别为“参考来源”；点击文档能进入可阅读页面，点击片段能定位 chunk 或明确说明暂不支持精确定位。
- AC-7：修复不回退 REQ-012 已完成能力：`document_sources`、当前消息 `[N]` 绑定、无归因证据展示仍保持可用。

## 验证建议

- Frontend：
  - `pnpm --filter @metaedu/web test`
  - `pnpm --filter @metaedu/web lint`
  - `pnpm --filter @metaedu/web typecheck`
  - 使用浏览器或截图验证 AI Chat 首屏输入框和参考来源交互。
- Backend / E2E：
  - 针对 Python 操作指南样例运行 `/api/v1/ai/chat/evidence` 真实请求，记录 evidence 结果。
  - 根据修改范围运行知识检索、AI Chat service 和 P1 RAG e2e 相关测试。
- Docs：
  - `scripts/check-engineering-docs`
  - `git diff --check`

## 后续执行建议

此 BUG 可以直接进入实现，但建议先做 30 分钟复现切片：

1. 页面布局和刷新问题先修，属于可见体验回归。
2. 引用链接可读性次之，优先保证文档级来源能打开。
3. 回答质量需要抓取真实 evidence，再判断是召回、排序、chunk、prompt 还是数据初始化问题。
