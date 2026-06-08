# Iteration 2026-W23: P1 最终查漏补缺

Status: Planned
Dates: 2026-W23
Goal: 关闭阶段一验证期剩余缺口，重点验证轨道 B：检索 / 抽取质量。

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|
| REQ-003 | REQ | Done | P1 RAG 质量链路验收与回归测试 | 覆盖 NER、3 通道召回、频次融合、sources 结构；相关测试可复现运行。 |
| REQ-004 | REQ | Candidate | 模板匹配可解释化收口 | doc_type、文件名、AI 置信度三层匹配具备可观测日志和至少一组真实业务文档验收记录。 |
| REQ-005 | REQ | Candidate | 结构化抽取嵌套结构稳定性验收 | object / array / table 抽取结果按模板结构落盘，并有样例回归锁定。 |
| REQ-006 | REQ | Candidate | P1 知识资产处理链路最终演示验收 | 能演示上传、解析、模板抽取、知识图谱、RAG 问答和来源展示的完整闭环。 |
| REQ-007 | REQ | Doing | REQ-003 复盘缺口的 RAG 质量链路收口 | 5 个 AC：AC-1 补 3 通道 fake rows 行为级测试；AC-2 修正 P1 / 迭代 / Backlog / current-work 状态矛盾；AC-3 修正 P1 轨道 B 过度验证声明；AC-4 清理 `test_ai_chat_rag_e2e.py` 死代码；AC-5 全量验证命令可复现。 |

## Out of Scope

- 不在本迭代引入新的向量库、图数据库、搜索引擎或对象存储形态。
- 不把阶段二的召回排序升级、RRF、rerank、多引擎编排提前并入阶段一。
- 不把 Backlog 条目扩写成长 PRD；复杂需求进入 `docs/01-product-planning/05-requirements/*` 或交付层 spec / plan。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| 轨道 B 多项已有代码但缺直接测试和端到端证据 | 不能按完成处理，应按”已实现 / 待验证”追踪 | REQ-003（已由 PR #74 关闭为 Done）；复盘发现的验收缺口由 REQ-007 承接 |
| 模板匹配和嵌套抽取仍依赖真实样例验收 | 阶段一关闭前必须收口为可验证结果 | REQ-004 / REQ-005 |
| 本次复核后端集成测试无法连接 PostgreSQL | 当前不能证明 P1 后端集成验收通过 | REQ-003 / REQ-006 |
