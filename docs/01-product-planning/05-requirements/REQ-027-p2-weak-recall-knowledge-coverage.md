# REQ-027: P2 弱召回知识覆盖与样例多样性

Status: 🟡 部分收口（机制+样例多样性+报告结构 收口；质量层 AC-4 未达成，由 REQ-028 接力）
Priority: P0
Milestone: P2
Source: REQ-026 follow-up
Related: REQ-016 / REQ-017 / REQ-018 / REQ-024 / REQ-025 / REQ-026 / TD-068

## 背景

REQ-026 P2 弱召回样例集（5 条）已落地并完成真 PG + `--allow-llm` 真实 LLM 验收，但质量层结论是 `1/5` 样例达成 P2 完整链路相对 baseline 覆盖度提升 ≥30% 的目标。REQ-026 AC-1（≥3/5）未达成。

具体观察：

1. 5 条样例集中在 Python 教程 + 课程标准 + 人才培养方案，未覆盖跨课程先导关系、复合 schema、跨文件关联等 P2 能力重点场景。
2. `Q4_prerequisite_knowledge_for_course`（训练方案类）出现 `-0.60` 退化，P2 完整链路在训练方案类弱召回问题上反而降低覆盖度。
3. `Q5_course_target_summary`（总结型问法）4 个 scenario 覆盖度都 ≤ 0.40，P2 链路在跨章节总结型问法上无稳定增益。
4. `Q2/Q3` 在 `+QU` scenario 覆盖度反而低于 baseline（`-0.40` / `+0.20`），说明扩展词对回答覆盖度的影响不稳定。

REQ-026 报告登记的 follow-up：扩展 P2 弱召回样例多样性与知识覆盖。

## 目标

- 把 REQ-026 的 5 条弱召回样例扩展到 ≥10 条，覆盖：Python 高级特性 / 跨课程先导 / 复合 schema / 跨文件关联 / 训练方案总结型问法 / 自然问法扩展词稳定性。
- 为新增样例设计更精准的 `expected_keypoints`（基于 dev DB 已上传文件真实内容校准，避免空泛关键词）。
- 复用 REQ-026 脚本与三层结论报告生成第二轮报告，验证 P2 完整链路在扩展样例集上的真实质量增益。
- 不在 REQ-027 修复 vector fallback（TD-068 已独立跟踪）；通过 `vector_fallback_count` 字段显式记录，禁止把 vector 通道增益归功于 P2 能力。

## 非目标

- 不引入 Neo4j / Elasticsearch / Milvus / reranker / cross-encoder。
- 不重写 RRF / ContextPacker / AIChatService 主链路。
- 不在 REQ-027 调 graph_edge 权重（REQ-017 已承接配置化）。
- 不在 REQ-027 修复 TD-068（vector embedding 为空）。
- 不替换 REQ-026 的 5 条样例，只扩展。

## 验收标准

1. 样例集从 5 条扩展到 ≥10 条；新增样例的 `category` 至少覆盖：python_advanced / cross_course_prerequisite / training_program_summary / template_nested_schema / cross_file_relationship。
2. 每条新增样例的 `expected_keypoints` 必须在 dev DB 已上传文件真实内容中出现（校准步骤），不允许"凭空写关键词"。
3. 在真实 PG + 真实 LLM provider 下，第二轮报告的 P2 完整链路相对 baseline 覆盖度提升 ≥30% 的样例比例 ≥ 40%（≥4/10）。
4. 第二轮报告中 `vector_fallback_count` 大于 0 的样例必须显式标记，禁止把 vector 通道增益归功于 P2 能力。
5. 若第二轮报告仍无法达成 AC-3，必须明确登记独立 `REQ-028` / `TD` 接力数据回填，不在本任务内强行造数据。
6. 报告章节与字段结构与 REQ-026 对齐（机制层 / prompt 层 / 质量层 + 数据缺口）。

## 建议执行顺序

1. 先在 dev DB 中用 SQL 抽样当前已上传 PDF/课程文件 / `knowledge_nodes` / `knowledge_edges` 真实内容。
2. 基于抽样结果写 ≥5 条新增样例，每条配套 `expected_keypoints` 校准记录。
3. 扩展 `validate_real_pg_rag_req027_weak_recall_v2.example.json`（或更新原文件但保留 v1 在 git 历史中）。
4. 复用 `validate_req024_p2_real_validation.py`（已支持 REQ-026），跑真 PG dry-run + `--allow-llm`。
5. 对比第一轮与第二轮报告，更新 Backlog / P2 milestone / Iteration / current-work / work-log。

## 事实源

- REQ-026 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md`
- REQ-026 requirement: `docs/01-product-planning/05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md`
- REQ-026 样例集: `scripts/validate_real_pg_rag_req026_weak_recall.example.json`
- REQ-026 脚本: `scripts/validate_req024_p2_real_validation.py`
- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-18 | Shaping 完成 | 分支 `feat/req-027-weak-recall-knowledge-coverage`；requirement + spec + plan 落地 |
| 2026-06-18 | Slice 1-4 完成 | 5 条 v2 样例 `validate_real_pg_rag_req027_weak_recall_v2.example.json` (基于 dev DB 513 knowledge_edges 真实关系校准)；wrapper 脚本 `run_req027_validation.py` 串联 v1 + v1+v2 两轮；真 PG dry-run + `--allow-llm` real LLM 报告均生成 (v1 复跑 1/5 与第一轮一致；v2 1/10 AC-4 未达成) |
| 2026-06-18 | 验收结果 | 机制层 10/10 ✅；prompt 层 5/10 ✅；质量层 1/10 ❌ (AC-4 未达成)；问题诊断：Q8 baseline 已 0.80 → 数据其实够；问题在自动覆盖度口径（子串匹配 + 真实 LLM 长答案同义改写导致覆盖度低） |
| 2026-06-18 | 后续分流 | REQ-028 (⚫ Candidate)：自动质量比较口径改造 — 语义匹配 / 关键事实分项权重 / LLM-as-judge 兜底 |
