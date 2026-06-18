# REQ-026 Spec: P2 RAG 效果比较与弱召回样例集收口

> Status: 🟣 Shaping
> Created: 2026-06-18
> Source: REQ-024 / REQ-025 validation follow-up
> Spec author: REQ-026 owner (this task)
> Plan: `docs/02-delivery-plans/02-plans/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples-plan.md`

## 1. Problem Statement

REQ-024 / REQ-025 已证明：

- **机制存在**：4 通道召回（vector / keyword / graph_node / graph_edge）已上线，Query Understanding 已接入，graph_edge 可回源 chunk 进入 packed context。
- **真实 LLM 报告**：在 dry-run 与 `--allow-llm` 真实 provider 下均有完整诊断输出。

但 REQ-025 报告同时指出：

1. 部分 baseline / Query Understanding 已能正常回答的样例，引入 graph_edge + weighted RRF 后**反而回答质量下降**（`Q2_course_quality` 在 `weighted_rrf` 场景下退化为「未找到足够参考来源」）。
2. 部分 graph_edge-only 场景仍回答「未找到足够参考来源」，没有真实增益证据。
3. 报告只能给出 retrieval topN / fusion topN / packed blocks 计数 + LLM 回答预览，**没有自动化的"最终回答是否覆盖关键事实"比较口径**。
4. `vector fallback trace count` 持续大于 0，vector topN 不可作为真实语义向量召回的代表。

REQ-024 AC-2「至少 2 个真实样例展示 graph_edge 对 keyword/vector 弱召回的补足价值」与 REQ-025 AC-2「至少 2 个真实问题最终回答比 baseline 更完整」均未达成。

## 2. Goal

把"机制存在"推进到"质量可证"：

1. 建立 P2 RAG 弱召回样例集，覆盖 Query Understanding / graph_edge / weighted RRF / context packing 的真实增益场景。
2. 为每个样例定义「关键事实要点」与「baseline vs P2 完整链路」自动覆盖度比较。
3. 复用 `scripts/validate_req024_p2_real_validation.py` 扩展，自动输出对比矩阵与"答得更完整"的判断。
4. dry-run 与 `--allow-llm` 两种模式都能产出报告，且报告必须明确区分：
   - 代码能力已接入
   - prompt-level evidence 已进入
   - 真实 LLM 回答质量已改善
5. 当数据缺口导致无法构造足够弱召回样例时，必须显式登记后续数据回填任务。

## 3. Non-Goals

- 不引入 Neo4j / Elasticsearch / Milvus / reranker / cross-encoder。
- 不重写现有 AI Chat 主链路，不重写 RRF / ContextPacker / AIChatService。
- 不把 LLM-as-judge 作为唯一验收依据；自动比较口径必须可人工复核（覆盖关键词命中 + answer preview 文本 + 引用的 evidence id）。
- 不在 REQ-026 内修复 `vector fallback`（TD-068 已单独跟踪）。
- 不在 REQ-026 内调整 graph_edge 权重（REQ-017 已承接配置化）。

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 至少 5 个弱召回样例：baseline 回答不足，P2 完整链路（+QU +graph_edge +weighted RRF）回答明显更完整或引用更准确 | 自动化覆盖度 + 人工抽样 |
| AC-2 | 每个样例必须记录 retrieval topN / fusion topN / packed blocks / document sources / final answer preview / `vector fallback` 计数 | 报告字段固定 |
| AC-3 | 至少 2 个样例证明 graph_edge 的 evidence 进入 packed context，并对最终回答有正向贡献；若无正向贡献必须显式记录原因 | per-sample 自动覆盖度对比 |
| AC-4 | 至少 1 个样例证明 Query Understanding 对自然问法有正向贡献 | baseline vs +QU 对比 |
| AC-5 | 自动比较口径必须可复跑：同一份样例 + 同一份脚本能产出同一份对比结论；人工只能补 qualitative 备注，不能作为唯一判定 | 脚本可重复执行 |
| AC-6 | 报告区分三层结论：机制存在 / prompt-level evidence 已进入 / 真实 LLM 回答质量已改善 | 报告章节固定 |
| AC-7 | 数据缺口必须登记独立 `TD` / `REQ`，并出现在 `current-work.md` 或候选区 | 任务登记 |
| AC-8 | dry-run 与 `--allow-llm` 两种模式都可用，且 `--allow-llm` 必须由用户在命令行明确确认 | CLI 行为 |

## 5. Architecture

### 5.1 复用与扩展点

不另起一套脚本。在 `scripts/validate_req024_p2_real_validation.py` 基础上扩展：

- **新增弱召回样例集**：`scripts/validate_real_pg_rag_req026_weak_recall.example.json`
  - 与 `validate_real_pg_rag_req016.example.json` / `req018.example.json` 并列
  - 样例必须包含 `expected_keypoints`（中文关键词 / 短语列表，至少 3 个），用于自动覆盖度比较
  - 样例必须包含 `category`（python_tutorial / training_program / course_standard / cross_doc_relationship）
- **复用 4 个 scenario**：`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / `weighted_rrf`
  - 不新增 scenario，避免与 REQ-024 报告对照失效
- **扩展 ScenarioRun 数据结构**：新增 `keypoint_coverage_pct` / `keypoint_hit_count` / `keypoint_total`
- **扩展 CLI 参数**：
  - `--weak-recall-samples` 指向新样例集
  - `--report-title` 默认改为 "REQ-026 P2 RAG 弱召回样例集与效果比较报告"
  - `--report-group` 控制报告显示 REQ-016 / REQ-018 / REQ-026 三组
  - 保留 `--allow-llm`，无破坏性变更
- **新增 report 章节**：
  - 「REQ-026 弱召回样例关键事实覆盖度对比」（per-sample per-scenario 矩阵）
  - 「自动比较结论」（机制层 / prompt 层 / 质量层）
  - 「数据缺口与后续任务」（独立 `TD` / `REQ` 候选）
- **新增 JSON 字段**：`keypoint_hit_count` / `keypoint_total` / `keypoint_coverage_pct` / `keypoint_hit_list`

### 5.2 自动比较口径（核心新增）

对每个 (sample, scenario) 对：

1. **关键事实覆盖度** = `answer_preview` + `document_sources` 文本中**包含** `expected_keypoints` 中关键词的数量 / `expected_keypoints` 总数
   - 关键词匹配：子串包含（case-insensitive），允许 0 token 后缀
   - 单 sample 单 scenario 输出 `keypoint_coverage_pct` ∈ [0, 1]
2. **质量改善判定**（per-sample）：
   - `baseline_coverage = baseline_rule_no_edge.keypoint_coverage_pct`
   - `p2_coverage = weighted_rrf.keypoint_coverage_pct`
   - `delta = p2_coverage - baseline_coverage`
   - **正向贡献**：`delta >= 0.3`（覆盖至少多 30% 关键事实）
   - **反向退化**：`delta <= -0.3`
   - **中性**：`abs(delta) < 0.3`
3. **graph_edge 价值判定**（per-sample）：
   - `edge_in_packed = weighted_rrf.graph_edge_packed_count`
   - `edge_in_fusion = weighted_rrf.graph_edge_fusion_count`
   - **正向**：`edge_in_packed > 0` 且 `delta >= 0.3`
   - **有召回无价值**：`edge_in_packed > 0` 且 `delta < 0.3`
   - **无召回**：`edge_in_packed == 0`

### 5.3 数据流

```
validate_req026_weak_recall.py (扩展自 validate_req024_p2_real_validation.py)
    │
    ├─► 加载 samples (REQ-016 + REQ-018 + REQ-026 weak recall)
    │
    ├─► 对每个 sample x scenario 跑 AIChatService
    │       ├─ retrieval_topn / fusion_topn / packed_blocks
    │       ├─ answer_preview
    │       └─ keypoint_coverage_pct (新)
    │
    ├─► 自动比较
    │       ├─ baseline vs P2 覆盖度矩阵
    │       ├─ graph_edge 价值判定
    │       └─ QU 增益判定
    │
    └─► 输出 Markdown 报告 + JSON 摘要
```

## 6. File Layout

```
scripts/
├── validate_req024_p2_real_validation.py            # 修改：扩展 scenario run + 新报告章节 + CLI
└── validate_real_pg_rag_req026_weak_recall.example.json  # 新增：弱召回样例集（>=5 条）

docs/02-delivery-plans/01-specs/
├── 2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples.md  # 本文件
└── 2026-06-18-req-026-rag-effect-comparison-validation-report.md  # 新增：dry-run / --allow-llm 报告

docs/02-delivery-plans/02-plans/
└── 2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples-plan.md  # 新增

docs/01-product-planning/05-requirements/REQ-026-...md   # 状态从 Ready -> Doing -> Done
docs/01-product-planning/02-milestones/02-growth-phase.md  # P2 open item 状态
docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md  # REQ-026 状态
docs/01-product-planning/04-backlog.md                       # REQ-026 状态
docs/03-engineering-governance/current-work.md              # 候选 -> 进行中 -> 最近完成
docs/03-engineering-governance/work-log.md                  # 一行式索引
```

## 7. Diagnostics Trace

扩展 `AIChatService` diagnostics 不变。脚本侧新增字段：

```json
{
  "question_group": "REQ-026",
  "question_id": "Q1_function_param_advanced",
  "scenario": "weighted_rrf",
  "keypoint_total": 5,
  "keypoint_hit_count": 4,
  "keypoint_coverage_pct": 0.8,
  "keypoint_hit_list": ["默认参数", "可变参数", "关键字参数", "参数传递"],
  "retrieval_counts": {...},
  "vector_fallback_count": 8,
  "graph_edge_packed_count": 2,
  "document_sources_count": 3,
  "final_answer_preview": "..."
}
```

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | 弱召回样例集 `req026_weak_recall.example.json`（>= 5 条）+ spec/plan | — |
| Slice 2 | 扩展 `validate_req024_p2_real_validation.py`：新增 keypoint 字段、CLI 参数、报告章节 | Slice 1 |
| Slice 3 | 真 PG dry-run 报告（含 baseline vs P2 覆盖度对比矩阵 + 数据缺口说明） | Slice 2 |
| Slice 4 | `--allow-llm` 真实 LLM 报告（需用户授权） | Slice 3 |
| Slice 5 | 文档收口（current-work / work-log / Backlog / Iteration / P2 milestone / REQ-026 / REQ-024 / REQ-025 关联） + commit + push + PR | Slice 4 |

## 9. Risks

- **弱召回样例不足**：当前 dev DB 数据集若不支持构造 >=5 条弱召回样例，必须登记独立 `TD` / `REQ` 跟踪数据回填，不在本任务内强行造数据。
- **`vector fallback` 干扰**：vector topN 不可作为真实语义向量召回，报告必须显式记录 `vector_fallback_count`，并避免把 vector 通道增益归功于 P2 能力。
- **`--allow-llm` 速率限制**：真实 LLM provider 可能限流；脚本需保留 `--limit` 参数控制样例数。
- **关键事实覆盖度口径偏脆**：子串匹配可能误判（如匹配到 `默认参数` 但语义相反）。报告必须同时保留 answer preview + 引用 sources 供人工复核。

## 10. References

- REQ-024 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md`
- REQ-025 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md`
- REQ-024 script: `scripts/validate_req024_p2_real_validation.py`
- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`
- Existing sample sets: `scripts/validate_real_pg_rag_req016.example.json`, `scripts/validate_real_pg_rag_req018.example.json`