# REQ-035 Plan: P2 graph_edge 通道去留决策

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision.md`

## 任务模式

决策任务（Decision），同 REQ-033/034。不改主链路代码，基于 REQ-033/034 既有证据 + 召回成本分析给出决策。

## 执行步骤

### Slice 1: 脚本改造

1. 在 `scripts/rag_validation/report_chain.py` 新增 `_render_req035_section(runs, grouped)`，镜像 REQ-034 结构：
   - **Table 1: 成本/收益对照** — 生产默认 0.5（成本 8 召回/3 SQL、产出 0 进 fusion/packed）vs w=1.2 boosting（产出 5/10 进 packed、但 Metric B=1/10 跨文档=0/10）vs 禁用（成本 0、产出 0）
   - **Table 2: 禁用可行性** — 机制 / REQ-018 影响 / REQ-025 影响 / 测试覆盖
   - **Table 3: 上调权重可行性** — 机制 / 收益 / 成本 / REQ-018 影响 / REQ-025 影响
   - **决策判定**（按 spec §5.4 框架）
2. 在 `report.py` `_render_report` 挂载 REQ-035 章节（紧跟 REQ-034 之后）。
3. 复用 REQ-034 的 `_req034_scenario_metrics` / weight sweep 数据（同源 dry-run）。

### Slice 2: dry-run 验证

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-035 graph_edge 通道去留决策 (dry-run)"
```

确认：REQ-035 章节渲染正确；dry-run 不调 LLM。

### Slice 3: 决策 + 报告

依据 spec §5.4 决策框架写独立评估报告 `2026-06-20-req-035-graph-edge-channel-decision-report.md`。

### Slice 4: 文档收口 + Git

- 同步 backlog / iteration / milestone / current-work / work-log
- `scripts/check-engineering-docs` 门禁
- commit + push + PR + squash merge + 删分支 + 同步 main

## 验证矩阵

| 项 | 命令 |
|----|------|
| 代码风格 | `ruff check scripts/rag_validation/` |
| 工程门禁 | `scripts/check-engineering-docs` |
| dry-run 复跑 | Slice 2 命令 |

## 风险与回退

- 全部改动限定在 `scripts/rag_validation/report_chain.py` + `report.py` + 新增文档，不碰主链路；回退即 revert。
- 决策若为禁用/上调，触发后续独立实现需求，不在本任务改代码。
