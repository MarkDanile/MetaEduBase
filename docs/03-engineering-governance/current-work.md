# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

### REQ-046: 企业 360 背调工作台与 MCP / Skill 集成闭环

状态：🟡 进行中
类型：新业务能力（产品需求开发）
领域：AI Workspace / Data Platform / MCP / Skill / 产业园区
当前执行模式：product planning -> spec/plan 驱动开发（Slice 0 塑形）
最近接手工具：Claude Code
分支：feat/req-046-due-diligence

需求来源：
- Requirement: docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md
- Spec: docs/02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md
- Plan: docs/02-delivery-plans/02-plans/2026-07-03-req-046-enterprise-360-due-diligence-workbench-plan.md
- 架构约束: docs/03-engineering-governance/01-rules/architecture.md

当前进展：开工三连完成，已建任务分支并登记工作台；Slice 0（盘点企查查 MCP 工具 + 确认样例企业与内部 MCP mock/真实）待用户决策后启动。
下一步：用户确认 Slice 0 决策点（样例企业授权、内部 MCP mock vs 真实、企查查 Skill 导入方式、报告导出形态），再启动 Slice 1 主体锚定 + QCC MCP Adapter。
验证状态：未运行（塑形阶段）。
交接备注：REQ-046 V0 保持 adapter 边界，不写死企查查/内部系统；依赖 REQ-044（MCP registry）/ REQ-045（Skill registry）/ REQ-052（智能问数）。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P0（并行） | REQ-044 MCP 注册、管理与调用能力 | ⚫ Candidate | 随 REQ-046 的 QCC / 内部 MCP 真实接入塑形最小 registry，优先启停、权限、凭证引用、审计与调用 trace | [Backlog](../01-product-planning/04-backlog.md) / [Applications](../01-product-planning/06-ai-applications/README.md#产品基座能力候选) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-07-20 | REQ-057 Catalog Adapter 路由与 entity_type 契约收口 | 🟢 完成 | adapter registry 3 类型路由 + MCP 抛 CapabilityUnavailableError（QueryService 捕获写审计 ok=False）+ 两 Catalog 同 entity_type 隔离测试（AC-5）+ REQ-054 AC 按真实验证层级修正 + entity_type 动态发现文档统一。226 backend tests pass / ruff 0 | [REQ-057](../01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md) |
| 2026-07-17 | TD-075 knowledge_nodes backfill 移除 OFFSET 防跳行 | 🟢 完成 | 移除 force=False OFFSET（每轮重查 WHERE embedding IS NULL LIMIT）+ BackfillResult + attempted_ids 防重复 + 单行失败不阻塞 + remaining count 非零退出。6 单测 pass | [Tech Debt](technical-debt.md#td-075-knowledge_nodes-embedding-backfill-使用-mutable-predicate--offset-导致跳行) / [PR #432](https://github.com/MarkDanile/MetaEduBase/pull/432) (`f30c1760`) |
| 2026-07-17 | DOC-077 跨事实源任务编号唯一性与历史碰撞收口 | 🟢 完成 | 重命名 BUG-011 -> BUG-016 (alias) / BUG-013 -> BUG-014 (alias)；新增 `scripts/engineering/checks/unique_task_ids.py` 同 ID 异义门禁；40/40 engineering tests pass | [Review](04-retrospectives/2026-07-15-recent-completion-code-review.md#p1-bug-编号已发生两次碰撞) / [PR #429](https://github.com/MarkDanile/MetaEduBase/pull/429) (`60045b1f`) |
| 2026-07-17 | BUG-015 QueryPanel 移除冗余 input + 查询背景改可选 | 🟢 完成 | 移除 "企业全称" 输入 + business_purpose 改 Optional + migration 020 audit_log.business_purpose nullable + entity_type 空提示含上传指引。803 backend + 16 frontend tests pass | [BUG-015](../01-product-planning/05-requirements/BUG-015-querypanel-ux-redundant-inputs.md) / [PR #430](https://github.com/MarkDanile/MetaEduBase/pull/430) (`d69684ae`) |
| 2026-07-16 | REQ-056 智能问数真实执行闭环与 AI Chat 生产接线 | 🟢 完成 | 4 Task 完成 + `tests/real_world/req056_business_samples.py` 10/10 真实业务样例绿；ImportedDataset 真实过滤、AI Chat request-bound QueryService + catalog 双键路由、审计 fail-closed 全闭环；REQ-052 重新关闭 | [REQ-056](../01-product-planning/05-requirements/REQ-056-intelligent-data-query-production-closure.md) / [REQ-052](../01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md) |
| 2026-07-15 | DOC-078 近期完成任务 Code Review | 🟢 完成 | 8 个批次评分与 4 个 follow-up 已入账；REQ-052 重新打开；候选区优先 REQ-056 / DOC-077 / TD-075 | [Review](04-retrospectives/2026-07-15-recent-completion-code-review.md) / [PR #425](https://github.com/MarkDanile/MetaEduBase/pull/425) |
| 2026-07-08 | REQ-054 Catalog 主体实现 | 🟢 完成 | Catalog 主体能力有条件关闭；adapter 可达性与 entity_type 契约由 REQ-057 接力 | [REQ-054](../01-product-planning/05-requirements/REQ-054-platform-database-catalog.md) / [REQ-057](../01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md) |
| 2026-07-07 | BUG-014 资源库 / 数据库 DB 不可用返回 503 | 🟢 完成 | 数据库连接故障统一返回 503 和恢复提示（历史编号 BUG-013，DOC-077 收口） | [Bug](../01-product-planning/05-requirements/BUG-014-resource-database-500-endpoints.md) / [PR #418](https://github.com/MarkDanile/MetaEduBase/pull/418) |
| 2026-06-30 | TD-073 离线 keypoint embedding 预计算落盘 | 🟢 完成 | 落盘缓存消除重复 embedding HTTP，RAG 验收性能进入可控范围 | [Plan](../02-delivery-plans/02-plans/2026-06-30-td-073-offline-keypoint-embedding-plan.md) / [PR #402](https://github.com/MarkDanile/MetaEduBase/pull/402) |
| 2026-06-30 | TD-074 batch embedding 路由测试补强 | 🟢 完成 | 补齐 batch / per-text、缓存、超时和降级路由回归 | [PR #400](https://github.com/MarkDanile/MetaEduBase/pull/400) |
| 2026-06-30 | DOC-076 最近完成批量归档 | 🟢 完成 | 最近完成窗口从 18 行压回 12 行，长期索引保留在 work-log | [PR #397](https://github.com/MarkDanile/MetaEduBase/pull/397) |
| 2026-06-30 | `_EMB_SEMAPHORE` 并发 spike | 🟢 完成 | cache warm 场景提高并发无收益，结论为保持现状 | [Report](../02-delivery-plans/01-specs/2026-07-02-candidate3-semaphore-upgrade-spike-report.md) / [PR #411](https://github.com/MarkDanile/MetaEduBase/pull/411) |
| 2026-06-24 | DOC-075 当前进行中污染门禁 | 🟢 完成 | 无活跃任务时强制当前进行中区只保留一句话 | [PR #394](https://github.com/MarkDanile/MetaEduBase/pull/394) |
| 2026-06-24 | BUG-016 AI Chat 超时误报网络错误 | 🟢 完成 | 单请求超时调整为 120 秒并区分超时、网络和 HTTP 错误（历史编号 BUG-011，DOC-077 收口） | [Bug](../01-product-planning/05-requirements/BUG-016-ai-chat-timeout-shorter-than-backend-llm.md) / [PR #388](https://github.com/MarkDanile/MetaEduBase/pull/388) |
