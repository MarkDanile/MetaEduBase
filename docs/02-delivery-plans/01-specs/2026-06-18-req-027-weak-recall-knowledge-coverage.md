# REQ-027 Spec: P2 弱召回知识覆盖与样例多样性

> Status: 🟣 Shaping
> Created: 2026-06-18
> Source: REQ-026 follow-up
> Requirement: `docs/01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-18-req-027-weak-recall-knowledge-coverage-plan.md`

## 1. Problem Statement

REQ-026 真 PG + `--allow-llm` 报告（5 样例）的质量层结论是 `1/5` (20%)，未达成 AC-1 ≥3/5 (60%)。从 5 条样例的 per-sample delta 看：

- 退化 1 条（`Q4_prerequisite_knowledge_for_course` delta=-0.60，training_program 类问法）
- 中性 3 条（`Q2/Q3/Q5`）
- 正向 1 条（`Q1_decorator_concept` delta=+0.80）

仅 1 条样例证明 P2 完整链路相对 baseline 有真实质量增益，**样例多样性和数据覆盖不足是主要瓶颈**。

## 2. Goal

- 把弱召回样例集从 5 条扩展到 ≥10 条，覆盖 P2 能力的关键场景。
- 在扩展样例上跑真 PG + `--allow-llm` 第二轮报告，验证 P2 完整链路在更大样本上的真实质量增益比例。

## 3. Non-Goals

- 不重写 RRF / ContextPacker / AIChatService 主链路。
- 不修复 TD-068（vector embedding 为空）。
- 不调整 graph_edge 权重（REQ-017 范围）。
- 不引入 Neo4j / Elasticsearch / Milvus / reranker。
- 不替换 REQ-026 已落地的 5 条样例；只新增，不修改原文件。

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 样例数 ≥10，新增 ≥5 条 | JSON 解析 `questions[]` 长度 |
| AC-2 | 新增样例 `category` 至少覆盖 5 类：python_advanced / cross_course_prerequisite / training_program_summary / template_nested_schema / cross_file_relationship | 报告章节分类 |
| AC-3 | 新增样例 `expected_keypoints` 在 dev DB 已上传文件真实内容中出现 | 校准记录（SQL 抽样 + 关键词 grep） |
| AC-4 | 第二轮报告 P2 完整链路相对 baseline 覆盖度提升 ≥30% 的样例比例 ≥ 40% (≥4/10) | REQ-027 报告 `自动比较结论` |
| AC-5 | `vector_fallback_count > 0` 的样例必须显式标记，禁止把 vector 通道增益归功于 P2 能力 | 报告固定字段 |
| AC-6 | 若 AC-4 未达成，必须登记独立 `REQ-028` 或 `TD-xxx` 接力数据回填 | 候选区登记 |

## 5. Architecture

### 5.1 新增样例集

新增 `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req027_weak_recall_v2.example.json`，与 REQ-026 v1 样例集并列：

- 不修改 v1（保持 git 历史可对照）
- v2 包含 5 条新增样例（不与 v1 重复）
- v2 同样支持 `samples[]` / `questions[]` / `expected_keypoints` 结构

### 5.2 脚本复用

`scripts/validate_req024_p2_real_validation.py` 已支持 REQ-026。REQ-027 不修改脚本主体，只需：

- 第二轮运行时同时加载 v1 + v2 样例（通过 `--weak-recall-samples` 参数两次指定 + 合并 JSON）
- 或在 v1 文件末尾追加 v2 内容（破坏 v1 完整性，不推荐）
- 或写一个 wrapper 脚本 `scripts/run_req027_validation.py` 串联 v1 + v2

**推荐方案：写 wrapper 脚本**。理由：
- v1 + v2 都可独立复跑
- 第二轮报告与第一轮报告可对比
- 不破坏 v1 样例集完整性

### 5.3 wrapper 脚本

```python
# scripts/run_req027_validation.py
# REQ-027 wrapper: load v1 + v2, run 2 rounds of validation, compare reports.
```

职责：
- 加载 v1 + v2 样例，合并为统一列表
- 调用 `validate_req024_p2_real_validation.py` 两次：
  - Round 1: 仅 v1（重跑第一轮报告作为 baseline 对比）
  - Round 2: v1 + v2（第二轮报告）
- 输出两个 Markdown 报告到 `docs/02-delivery-plans/01-specs/`：
  - `2026-06-18-req-027-rag-effect-comparison-v1-report.md`（v1 复跑）
  - `2026-06-18-req-027-rag-effect-comparison-v2-report.md`（v1+v2）

### 5.4 数据流

```
scripts/run_req027_validation.py (wrapper)
    │
    ├─► load v1 (validate_real_pg_rag_req026_weak_recall.example.json)
    │       + v2 (validate_real_pg_rag_req027_weak_recall_v2.example.json)
    │
    ├─► Round 1: run validate_req024_p2_real_validation.py --weak-recall-samples v1.json
    │       → 2026-06-18-req-027-rag-effect-comparison-v1-report.md
    │
    └─► Round 2: run validate_req024_p2_real_validation.py --weak-recall-samples merged.json
            → 2026-06-18-req-027-rag-effect-comparison-v2-report.md
```

## 6. File Layout

```
scripts/
├── run_req027_validation.py                          # 新增：wrapper 脚本
├── validate_real_pg_rag_req026_weak_recall.example.json  # 不修改
└── validate_real_pg_rag_req027_weak_recall_v2.example.json  # 新增：5+ 条新增样例

docs/02-delivery-plans/01-specs/
├── 2026-06-18-req-027-weak-recall-knowledge-coverage.md  # 本文件
└── 2026-06-18-req-027-rag-effect-comparison-v2-report.md  # 新增：第二轮报告

docs/02-delivery-plans/02-plans/
└── 2026-06-18-req-027-weak-recall-knowledge-coverage-plan.md  # 新增

docs/01-product-planning/05-requirements/REQ-027-...md  # 状态从 🟣 Shaping → 🟡 Doing
docs/01-product-planning/02-milestones/02-growth-phase.md
docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md
docs/01-product-planning/04-backlog.md
docs/03-engineering-governance/current-work.md
docs/03-engineering-governance/work-log.md
```

## 7. Diagnostics Trace

复用 REQ-026 diagnostics：retrieval_topn / fusion_topn / packed_blocks / document_sources / final_answer_preview / keypoint_coverage_pct / vector_fallback_count。

不修改 AIChatService diagnostics。

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | REQ-027 requirement + spec + plan + 新增样例集 v2 (dev DB 校准) | — |
| Slice 2 | wrapper 脚本 `run_req027_validation.py` | Slice 1 |
| Slice 3 | 真 PG dry-run v1 + v2 两轮 | Slice 2 |
| Slice 4 | 真 PG + `--allow-llm` v1 + v2 两轮真实 LLM 报告 | Slice 3 |
| Slice 5 | 文档收口 + commit + push + PR | Slice 4 |

## 9. Risks

- **新增样例 `expected_keypoints` 校准不严谨**：必须在 dev DB 真实内容中校准；建议先用 `grep` / `psql` 抽样。
- **第二轮报告仍达不到 AC-4**：必须登记 `REQ-028` 或 `TD` 接力数据回填，不能在本任务强行造数据。
- **wrapper 脚本复杂度**：若 REQ-024 脚本 API 变动，wrapper 需同步更新；本 PR 尽量保持 wrapper 简单（仅序列化 CLI 参数 + 调 subprocess）。
- **两次跑 LLM 的随机性**：用固定 seed（如 `_fake_query_understanding_response` 已固定）；`--allow-llm` 跑真 LLM 需注意 prompt 注入差异。

## 10. References

- REQ-026 requirement: `docs/01-product-planning/05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md`
- REQ-026 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md`
- REQ-026 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req026_weak_recall.example.json`
- REQ-026 脚本: `scripts/validate_req024_p2_real_validation.py`
- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`