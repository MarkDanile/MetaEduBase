# Q7 graph_edge 退化排查报告

> Status: 🟢 完成（关闭 — 非系统性，纠正归因）
> Created: 2026-06-23
> 任务来源: `docs/03-engineering-governance/current-work.md` 候选区「Q7_kg_occupation_to_skill graph_edge 退化排查」
> 触发报告: [REQ-039 验收报告 §6 follow-up #2](2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up)
> 模式: spike / ai-effect validation（只读排查 + 单问题真 LLM 隔离复现）

## 1. 排查目标

REQ-039 全量真 LLM 验收报告 §3.3 / §6 follow-up #2 记录：Q7 `kg_occupation_to_skill` 在 `baseline_rule_no_edge` (substring 0.4) → `graph_edge` (substring 0) 退化，归因为「graph_edge 通道在某些 fusion 排序下改变 packed chunk 选择导致命中下降」。本任务复核该归因是否成立，并判定是否需要修复。

## 2. 排查方法 — 场景隔离复现

### 2.1 关键 confound：报告的对比同时改了两个变量

[runner.py:22-63](../../../scripts/rag_validation/runner.py#L22-L63) 的场景定义：

| 场景 | `use_hybrid_ner` | `use_graph_edge` | graph_edge 权重 |
|------|------------------|------------------|-----------------|
| `baseline_rule_no_edge` | **False**（RuleBasedNER） | False | 0.0 |
| `query_understanding` | **True**（HybridQueryUnderstanding，真 LLM） | False | 0.0 |
| `graph_edge` | **True**（HybridQueryUnderstanding，真 LLM） | True | 0.5 |

报告 §3.3 比的是 `baseline_rule_no_edge` vs `graph_edge`，**同时**改了 NER 管线（rule→hybrid）和 graph_edge 通道。要隔离 graph_edge 的作用，正确对比是 `query_understanding` vs `graph_edge`（NER 相同，只差 graph_edge）。

### 2.2 单问题真 LLM 隔离复现

只跑 Q7（v3 fixture idx 6：「环境监测技术专业对应的职业资格和技能方向有哪些？」，5 个 keypoint）跨 3 个场景，`--allow-llm`（真 embedding + 真 NER LLM + 真答案 LLM），仅取确定性口径（substring/semantic），跳过 LLM-as-judge。复现脚本 `/tmp/q7_repro.py`（未入仓）。

DB 种子已确认（tenant `…0001`）：`document_chunks=1062`、`knowledge_edges=513`、`knowledge_nodes=599`，Q7 所需职业→技能边存在（`对应职业`/`对应职业资格`/`对应专业技能方向`/`专业技能方向`/`可获取证书`/`培养目标工作岗位`）。

## 3. 复现结果

| 场景 | NER | graph_edge | substring | semantic | sources | packed chunk_ids |
|------|-----|-----------|-----------|----------|---------|------------------|
| `baseline_rule_no_edge` | rule | OFF | **0.2** | 0.6 | 2 | — |
| `query_understanding` | hybrid | OFF | 0.2 | 0.8 | 2 | A |
| `graph_edge` | hybrid | ON | **0.4** | 0.8 | 2 | A（与上一行**逐字节相同**） |

隔离对比：

| 对比 | 隔离变量 | substring Δ | 解读 |
|------|----------|-------------|------|
| baseline → query_understanding | NER（edge 都关） | **0.0** | NER 切换不伤 Q7 |
| query_understanding → graph_edge | graph_edge（NER 相同） | **+0.2** | packed 逐字节相同 → 100% 答案噪声 |
| baseline → graph_edge（报告的混淆对比） | NER + graph_edge | **+0.2**（本次）/ −0.4（报告那次） | 符号跨 run 翻转 |

**`graph_edge` 场景的 `retrieval_counts.graph_edge=8`（召回了 8 条），但 `fusion_chunk_ids` / `packed_chunk_ids` / `sources_titles` 与 `query_understanding` 逐字节相同** —— 8 条 graph_edge 召回 0 条进 fusion top-10 / packed。

## 4. 根因

**根因：LLM 答案随机性，不是 graph_edge 通道结构性退化。** 三条铁证：

1. **graph_edge@0.5 是惰性死权重**：Q7 召回 8 条 graph_edge，但 0 条进 fusion/packed（`query_understanding` 与 `graph_edge` 的 `fusion_chunk_ids`、`packed_chunk_ids`、`sources_titles` 逐字节相同）。RRF 在 weight=0.5 下边项贡献 `0.5/(60+rank)` ≪ vector/keyword 的 `1.0/(60+rank)`，挤不进 top-10。与 [REQ-034 评估报告](2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md)「生产默认 0.5 下 graph_edge 召回 8 chunks/样例但 0 进 fusion/packed（惰性死权重）」一致。**因此 graph_edge 在结构上不可能改变 Q7 的 packed context，也就不可能改变 substring 覆盖。**

2. **substring 指标跑在 LLM 生成的答案文本上**：[runner.py:225](../../../scripts/rag_validation/runner.py#L225) `_compute_keypoint_coverage(final_answer_preview, sources_titles, ...)`。答案本身是真 LLM 随机采样。报告那次 graph_edge 答案恰好未提 keypoint（0），本次恰好提到「检测技术」（0.4）—— 同一份 packed context，不同采样。

3. **baseline 绝对值跨 run 漂移**：报告 baseline=0.4，本次 baseline=0.2。连不开 graph_edge 的基线都在变 → 答案方差主导，而非检索/通道结构差异。

## 5. 结论与归因纠正

- **REQ-039 报告 §3.3 / §6 follow-up #2 的归因「graph_edge 通道改变 fusion 排序导致 Q7 命中下降」不成立。** graph_edge@0.5 对 Q7 的 packed context 零影响（死权重），substring 跨场景差异全部来自 LLM 答案方差。
- **Q7 不是真实回归**，是测量噪声（deterministic 公式跑在 stochastic 输入上）。规模 1/27 + 跨 run 符号翻转，不构成系统性问题。
- **无需代码修复**。graph_edge 在生产本就默认关闭（REQ-036）；即便启用，weight=0.5 下也不会改变 packed context。
- **方法学提醒（不阻塞，不另立任务）**：substring/semantic 口径虽公式确定，但输入是真 LLM 答案，跨场景对比会混入答案方差。因果归因（「某通道是否改变命中」）须以 packed/fusion 逐字节对比为据，不能仅凭 substring Δ。REQ-039 §3.2 已将 26/37 mismatch 归为 LLM 噪声字段（continuous_pct + llm_judge_pct）；本次进一步澄清：连 substring/semantic 的 11 个 mismatch 也可能含答案方差成分，需结合 packed 对比判定。

## 6. 验收门禁

| 项 | 实际 | 判定 |
|----|------|------|
| 复现 Q7 跨隔离场景 | 3 场景单问题真 LLM run 完成 | ✓ |
| 隔离 graph_edge vs NER | query_understanding↔graph_edge（同 NER）+ baseline↔query_understanding（同 edge off） | ✓ |
| 定位根因 | packed 逐字节相同 + 跨 run 符号翻转 → LLM 答案方差 | ✓ |
| 纠正 REQ-039 归因 | 本报告 §5 + REQ-039 报告 §3.3/§6 增补纠正链接 | ✓ |
| 判定是否需修复 | 否（非系统性 + 生产已禁用） | ✓ |

## 7. 非目标（确认未做）

- 未改主链路代码 / 校验脚本（纯排查 + docs-only 收口）
- 未改 graph_edge gate 默认值（REQ-036 维持 off）
- 未跑全量 27 样例 suite（单问题隔离复现足以定位；全量受 provider 累积吞吐限制，见 [AC-4 子集验证报告](2026-06-22-td-071-ac4-subset-validation-report.md)）
- 未对 substring/semantic 口径做答案方差量化（仅结构性证明 packed 不变；如需量化方差需多次 run，非本任务范围）

## 8. 数据可复现

```bash
# 单问题真 LLM 隔离复现（脚本 /tmp/q7_repro.py，未入仓；核心逻辑见本报告 §2）
cd packages/server-python && python /tmp/q7_repro.py
# 期望：query_understanding 与 graph_edge 的 fusion_chunk_ids / packed_chunk_ids 逐字节相同；
#       substring 跨场景差异仅来自 final_answer_preview（LLM 答案方差）。
```

## 9. 文档收口摘要

- 本排查报告：`docs/02-delivery-plans/01-specs/2026-06-23-q7-graph-edge-degradation-investigation-report.md`
- [REQ-039 验收报告](2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md) §3.3 / §6 follow-up #2：增补归因纠正链接，follow-up #2 状态改「已关闭（归因纠正）」
- `current-work.md`：Q7 从「下一批候选任务」移入「最近完成」（关闭 — 非系统性）
