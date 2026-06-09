# Iteration 2026-W23: P1 最终查漏补缺

Status: 🟡 Planned
Dates: 2026-W23
Goal: 关闭阶段一验证期剩余缺口，重点验证轨道 B：检索 / 抽取质量。

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|
| REQ-003 | REQ | 🟢 Done | P1 RAG 质量链路验收与回归测试 | 覆盖 NER、3 通道召回、频次融合、sources 结构；相关测试可复现运行。 |
| REQ-004 | REQ | 🟢 Done | 模板匹配可解释化收口 | 主要代码与测试已由 [PR #77](https://github.com/MarkDanile/MetaEduBase/pull/77) 合并；复核发现的验收证据与质量门禁缺口由 REQ-008 承接。 |
| REQ-005 | REQ | 🟢 Done | 结构化抽取嵌套结构稳定性验收 | 已建 spec/plan；为 `extract_template_prompts` 补 11 条 object / array / table 嵌套回归用例；轨道 B 翻结论；0 业务代码改动。 |
| REQ-006 | REQ | 🟣 Shaping | P1 知识资产处理链路最终演示验收 | 能演示上传、解析、模板抽取、知识图谱、RAG 问答和来源展示的完整闭环；spec / plan 骨架已建，Stage 1 待实施（端到端脚本 + UI 手册）。 |
| REQ-007 | REQ | 🟢 Done | REQ-003 复盘缺口的 RAG 质量链路收口 | 5 AC 全部收口（AC-1 行为级测试 / AC-2 状态同步 / AC-3 过度声明 / AC-4 e2e 死代码 / AC-5 验证声明真实）；[PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) 已合并。 |
| REQ-008 | REQ | 🟢 Done | 收口 REQ-004 验收证据与质量门禁缺口 | ruff 5 项清零（E501/UP035/I001）；4 分支 `template.select layer=...` 日志 caplog 断言；2 条 L3 解析失败 / 空响应用例；1 条生产代码漂移保护；行为不变。[PR #79](https://github.com/MarkDanile/MetaEduBase/pull/79) 已合并。 |

## Out of Scope

- 不在本迭代引入新的向量库、图数据库、搜索引擎或对象存储形态。
- 不把阶段二的召回排序升级、RRF、rerank、多引擎编排提前并入阶段一。
- 不把 Backlog 条目扩写成长 PRD；复杂需求进入 `docs/01-product-planning/05-requirements/*` 或交付层 spec / plan。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| 轨道 B 多项已有代码但缺直接测试和端到端证据 | 不能按完成处理，应按”已实现 / 待验证”追踪 | REQ-003（已由 PR #74 关闭为 Done）；复盘发现的验收缺口由 REQ-007 承接 |
| 模板匹配和嵌套抽取仍依赖真实样例验收 | 阶段一关闭前必须收口为可验证结果 | REQ-004 / REQ-008 / REQ-005 |
| 本次复核后端集成测试无法连接 PostgreSQL | 当前不能证明 P1 后端集成验收通过 | REQ-003 / REQ-006 |
