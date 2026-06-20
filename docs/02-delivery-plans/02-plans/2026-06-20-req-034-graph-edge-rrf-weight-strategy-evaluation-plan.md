# REQ-034 Plan: P2 graph_edge RRF 权重/策略调整评估

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation.md`

## 任务模式

评估任务（Evaluation），同 REQ-033。不改主链路代码，基于 dry-run retrieval 层数据 + 代码分析给出建议。

## 执行步骤

### Slice 1: 脚本改造

1. `_default_scenarios()` 新增 2 个 scenario：
   - `graph_edge_w03`：`use_graph_edge=True`, `graph_edge: 0.3`，其余同 `graph_edge` scenario
   - `graph_edge_w07`：`use_graph_edge=True`, `graph_edge: 0.7`，其余同 `graph_edge` scenario
2. 新增 `_render_req034_section(runs, grouped)`，镜像 `_render_req033_section` 结构：
   - **Table 1: weight sensitivity** — per weight level（off / 0.3 / 0.5 / 0.7 / 1.2），计算 Metric A / Metric B（vs off-baseline）/ 跨文档 grounding / packed overlap vs off-baseline / fusion edge 均值
   - **Table 2: 策略可行性** — 策略 1（权重下调，数据驱动）/ 策略 2（conditional trigger，代码分析）/ 策略 3（packer 优先级，代码分析）
   - **Table 3: REQ-018/025 影响面**
   - **建议判定**（按 spec §5.4 框架）
3. 在报告渲染主流程挂载 REQ-034 章节（紧跟 REQ-033 之后）。
4. 复用 REQ-033 的 `_distinct_sections` / packed overlap 计算逻辑（提取为模块内 helper 或内联）。

### Slice 2: dry-run 验证

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-034 graph_edge RRF 权重/策略评估 (dry-run)"
```

确认：weight sweep 5 点数据齐全；REQ-034 章节渲染正确；dry-run 不调 LLM。

### Slice 3: 判定 + 报告

依据 weight sweep 数据填 spec §5.4 判定框架，写独立评估报告 `2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md`。

### Slice 4: 文档收口 + Git

- 同步 backlog / iteration / milestone / current-work / work-log
- `scripts/check-engineering-docs` 门禁
- commit + push + PR

## 验证矩阵

| 项 | 命令 |
|----|------|
| 代码风格 | `ruff check scripts/validate_req024_p2_real_validation.py` |
| 工程门禁 | `scripts/check-engineering-docs` |
| dry-run 复跑 | 上文 Slice 2 命令 |

## 风险与回退

- weight sweep 增加运行时间：dry-run 可接受；若过慢可 `--limit` 缩小样例集做机制验证。
- 全部改动限定在 `scripts/validate_req024_p2_real_validation.py` + 新增文档，不碰主链路；回退即 revert 单文件。
