# BUG-003 AI Chat 体验与回答质量回归 — Spec

> Bug: `docs/01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-12-bug-003-ai-chat-regression-plan.md`

## Summary

本 spec 收口 AI Chat 在 REQ-012 合并后真实使用中出现的 7 个 AC 体验与质量回归：

- AC-1 桌面首屏看不到输入框（small viewport / DevTools 打开时）。
- AC-2 "Python 的基本数据类型有哪些？" 召回只命中目录 chunk + 空 content knowledge_node，LLM 答 "证据不足"。
- AC-3 回答质量验收必须记录实际 sources / document_sources / 命中通道 / 关键 chunk 摘要。
- AC-4 "你能回答什么问题？" 提交后疑似页面刷新或无有效反馈。
- AC-5 回答正文 `[1] / [2] / [3]` 点击行为不一致（外链新标签 / evidence-ref 原页跳转 / chunk 锚点可能失效）。
- AC-6 底部"参考来源"视觉不像引用区；点击文档可能不可读。
- AC-7 不回退 REQ-012 已完成能力（document_sources / 当前消息 [N] 绑定 / 无归因证据展示）。

本 spec 不重做 RAG 基础；它是 BUG 修复 spec，按 5 个修复合片走独立 PR。

## Current Findings

详见 BUG 文档 `2026-06-12 初步排查记录` 段 + `2026-06-12 复现切片记录` 段。

| 问题 | 当前证据 | 候选真因 |
|------|----------|----------|
| AC-1 输入框被挤出首屏 | `AiChatView.vue:2` `h-screen` + L17 `flex-1 overflow-y-auto`；输入区在 L101-133 独立 `border-t` 块。 | small viewport (高 < 600px) + DevTools 打开时聊天容器 `flex-1` 高度挤压输入区。 |
| AC-2 Python 数据类型答"证据不足" | `pg_chunk_vector_retriever.py:36-39` `get_embedding` 返回空 → 整个 vector chunk 通道空。`pg_chunk_keyword_retriever.py:93` 共享 AsyncSession 并发报错。 | embedding service 不可达 / 跨 session 并发冲突。 |
| AC-3 答案质量缺真实数据 | BUG 文档已记录：本机请求最终 sources 全是 5 条 knowledge_node，2 条空、2 条目录、1 条无关。 | 召回管道问题（见 AC-2）。 |
| AC-4 兜底问题疑似刷新 | quickQuestion 按钮 `type` 缺失；中文 IME Enter 与 `@keydown.enter.exact.prevent` 行为可能冲突。 | 需真实浏览器复现定真因。 |
| AC-5 引用点击行为不一致 | `AiChatView.vue:340-345` `openFile` 整页跳转；marked 渲染的原生 `<a>` 链接 `target="_blank"`。 | 整页跳转丢失 chat 上下文 + 链接行为不一致。 |
| AC-6 参考来源不像引用区 | `DocumentSourceList.vue` 样式 `border` + `bg-warm` 与气泡视觉差异小；`openDocumentSource` 不传 chunkId。 | 视觉层级 + 点击行为。 |

## Goals

- 后端修复合片 1：保证 chunk vector / chunk keyword / full-text 通道稳定返回正文 chunk，fused 不再全是 knowledge_node。
- 前端修复合片 2：AI Chat 首屏输入框在桌面 / mobile / DevTools 打开场景下都可见。
- 前端修复合片 3：参考来源区视觉强化，按钮 `type="button"` 显式化。
- 前端修复合片 4：`openFile` 改新标签 + 保留 `?chunk=` 锚点 + 降级文案；evidence-ref 引用与外链行为对齐。
- 前端修复合片 5：兜底问题"页面刷新"——补中文 IME 兼容 + loading 错误态可视化（**需真实点击复现后定真因**）。
- 每个 PR 单独验证（前端 lint/typecheck/test，后端 pytest），不互相阻塞。
- 全部 PR 合并后 BUG-003 翻 `🟢 完成`。

## Non-Goals

- 不重做 REQ-012 已有能力（document_sources / 当前消息 [N] 绑定 / 无归因证据展示）。
- 不引入 Elasticsearch、Neo4j、Milvus、Qdrant 或 GraphRAG 框架。
- 不重做 RAG 多路召回（TD-046 / TD-047 / TD-050 / REQ-012 已是前置依赖）。
- 不重构 `AIChatService` 编排（保留现有 `_retrieve` / `_safe_retrieve_*` 兜底模式）。
- 不动 embedding service 配置 / 密钥（属于部署环境问题，不是 BUG 修复范围）。

## Acceptance Criteria

- AC-1：AI Chat 在 1366×768 桌面视口下，输入框首屏可见；DevTools 打开时输入框仍可见；mobile 360×640 视口输入框可见。
- AC-2："Python 的基本数据类型有哪些？" 真实请求返回的 `sources` 至少 1 条 `source_type="chunk"` 且 content 包含整数/浮点/字符串/列表/字典/元组/集合等关键字。
- AC-3：每个修复合片 PR 描述必须包含 `sources` 真实数据（条数 / 通道 / 关键 chunk 摘要）。
- AC-4：兜底问题提交后：(a) 页面 URL 不变；(b) 输入框仍聚焦或保持可输入状态；(c) assistant 给出"能力说明 / 可提问范围 / 明确错误"之一反馈。
- AC-5：正文 `[1] / [2] / [3]` 点击后**新标签页**打开文件详情 + chunk 锚点；外链 markdown 链接也走新标签；evidence 缺失时显示降级提示。
- AC-6：底部"参考来源"区在视觉上与上方 markdown 气泡有明显分隔（border-top + 标题 uppercase + 卡片化）；点击文档卡片标题/外链按钮能进可阅读页。
- AC-7：5 个修复合片合并后，REQ-012 已有功能（document_sources 列表 / 当前消息 [N] 绑定 / unattributedSources 区）继续工作，E2E 无回退。

## Risks

- **风险 1**：修复 `PgChunkVectorRetriever` 嵌入空兜底时，可能影响现有依赖"无 embedding 时不报错"的代码路径；需保留 warning 日志不抛异常。
- **风险 2**：`PgChunkKeywordRetriever` 跨 session 并发修复如果走"为每个 retriever 单独开 session"，会引入新连接池消耗；需在测试环境观察并发上限。
- **风险 3**：`openFile` 改 `window.open` 会被浏览器弹窗拦截器拦下；需用 `<a target="_blank" rel="noopener noreferrer">` 替代（用户主动点击不被拦）。
- **风险 4**：前端 layout 修复可能影响其他 AI Chat 类似的"flex flex-col h-screen"页面（已发现 AdminView / KnowledgeBaseView / ResourceView / SkillEditorView 也用 EmptyState）；需在 PR 中明确"只动 AiChatView"。

## Out of Scope

- 重新设计 AI Chat 整体 UI（如改为抽屉式 / 双栏布局）。
- 引入流式输出（streaming response）。
- 接入多模态（图片 / 表格输入）。
- 移动端原生 App 适配。

## References

- BUG 文档：`docs/01-product-planning/05-requirements/BUG-003-ai-chat-ux-and-answer-quality-regression.md`
- 计划：`docs/02-delivery-plans/02-plans/2026-06-12-bug-003-ai-chat-regression-plan.md`
- REQ-012：`docs/01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md`
- REQ-012 Spec：`docs/02-delivery-plans/01-specs/2026-06-12-req-012-rag-retrieval-document-sources.md`
- 工作台：`docs/03-engineering-governance/current-work.md`（BUG-003 卡片）
- 技术债总账：TD-051（document_chunks 元数据治理；与本 BUG 关联但独立任务）
