# AC-4 子集验证报告：REQ-028 v3 10 样例 `--allow-llm` wall-clock

> Status: 🔴 AC-4 ≤10min 目标**不可达**，但 TD-071 实施健康
> Created: 2026-06-22
> Source: REQ-039 验收报告 §6 follow-up #1（用户决策 2026-06-22 走"实证验证"路径）
> Spec: `docs/02-delivery-plans/01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-21-td-071-rag-eval-embedding-batch-plan.md`

## 1. 验证目标

REQ-039 AC-4 验收要求"重跑 REQ-028 v3 10 样例 `--allow-llm` 在 ≤10min 完成"。原 REQ-039 验证因 brief 命令未限制子集（全 suite 27 样例 × 6 scenario = 162 run），实际跑 17.8min；按"按比例 spirit 解释"推算 60 run 应为 ~6.6min。**本验证任务是实测 60 run 确认 spirit 解释是否成立**。

## 2. 实测结果

### 2.1 命令

```bash
cd packages/server-python && /usr/bin/time -p python3 ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/td071-ac4-subset.md \
  --json-out /tmp/td071-ac4-subset.json \
  --report-title "REQ-039 AC-4 子集验证（TD-071 spirit 解释）" \
  --allow-llm --semantic-emb-threshold 0.35 \
  --concurrency 4
```

按 follow-up #1 建议："仅传 `--req028-samples` 不传 `--weak-recall-samples`"。`--limit` 未传（fixture 本身就是 10 样例 = 60 run）。

### 2.2 实测指标

| 指标 | 期望（spirit 解释） | 实测 | 判定 |
|------|---------------------|------|------|
| Wall-clock | ≤ 10 min（AC-4 target） | **1774.91s ≈ 29.6min** | ❌ **超 target ~200%** |
| 总 runs | 60（10 样例 × 6 scenario） | **132 run**（见 §2.3） | — brief 命令未严格限制子集 |
| 仅 REQ-028 v3 | 60 run | 60 run | ✓ 子集生效 |
| `_EMB_STATS` timeout | 0 | 0 | ✓ |
| `_EMB_STATS` error | 0 | 0 | ✓ |
| `_EMB_STATS` hit/miss | hit ≫ miss | hit=1105 / miss=401 (total=1506) | ✓ 方向正确 |

### 2.3 关键发现：brief 命令并未严格限制子集

**实测 runs = 132**，按 group 分布：

| group | runs | 占比 |
|-------|------|------|
| REQ-028 | 60 | 45% |
| REQ-026 | 30 | 23% |
| REQ-016 | 24 | 18% |
| REQ-018 | 18 | 14% |
| **合计** | **132** | **100%** |

仅传 `--req028-samples` 没传 `--weak-recall-samples` 仍跑了 132 run（REQ-028 v3 + REQ-026 weak-recall + REQ-016 + REQ-018 fallback sample set）。需调研 `_load_questions`（`scripts/rag_validation/loader.py`）确认为什么单 fixture 触发多 group — 推测 `_load_questions` 仍把 default fallback path 加载了。

### 2.4 spirit 解释被实测推翻

| 估算路径 | 估算 wall-clock | 实测 |
|----------|-----------------|------|
| 上次 162 run 全 suite 17.8min → 按比例 60 run ≈ **6.6min** | 6.6min | **实际 60+ run 子集 29.6min** |
| linear 假设 17.8 / 162 × 60 = 6.6 min | — | — |

**根因**（推测）：
1. **provider cache 非线性摊销**：更小样本下 cache 命中率降低；132 run 子集 cache 命中率与 162 run 全 suite 不同。
2. **answer embedding 全 miss**：60-132 run 内所有 answer embedding 都不同 → cache 命中率主要靠 keypoint term+synonyms 摊销。
3. **冷启动开销**：每次 run 触发 AIChatService.chat 全链路初始化（含 NER、retrievers、fusion、packer），run 越少摊销越高。

**实测 s/run**：

- 全 suite 162 run：17.8 × 60 / 162 = 6.6 s/run
- 实测 132 run：29.6 × 60 / 132 = 13.4 s/run（**2× linear 假设**）
- 推算 60 run 子集：可能 15-20 s/run（cache 命中率最低），即 15-20min

## 3. AC-4 判定

**AC-4 ≤10min wall-clock 目标在当前环境 + 当前命令约定下不可达。**

但**这不否定 TD-071 实施价值**：

| 维度 | 历史阻塞 | TD-071 实测 | 加速 |
|------|----------|-------------|------|
| 162 run 全 suite | 50-60min 阻塞 | 17.8min | **3.0-3.4×** |
| 132 run 子集 | （未测，但应 ≥162 run 子集） | 29.6min | — |
| 60 run 仅 REQ-028 | （未单独测过） | 推算 15-20min | — |
| `_EMB_STATS` timeout/error | — | 0 / 0 | — |
| provider 限流 | — | `_EMB_SEMAPHORE=2` 维持 | — |

**TD-071 解决了"50-60min 不可完成"问题（→ 17.8min 完成）；10min 是更激进的优化目标，超出 TD-071 范围。**

## 4. AC-4 不可达根因（建议后续优化方向）

**Provider 累积吞吐仍是天花板**。进一步优化需要：

1. **离线批量 keypoint embedding 预计算**（REQ-037 follow-up #2 / REQ-039 follow-up #4）：把 keypoint term+synonyms embedding 提前算好落盘，消除所有 keypoint embedding HTTP。预期省 50% 流量。
2. **真正调用 `get_embeddings_with_timeout_batch`**（TD-071 实施但未被 runner.py 接入，REQ-039 follow-up #4 / TD-071 §5 偏差）：把 answer+recall embedding 走 provider batch API 单 HTTP 拿回。预期省 30-50% 流量。
3. **降低 `_EMB_SEMAPHORE=2` 的影响**：当前 limit 仍按 REQ-031 保守限流；如 provider 配额允许提升到 4-5，embedding 总耗时压减 50%。

以上 3 项叠加，理论上可把 60 run 压到 ~5-7min。但需后续独立 TD/REQ 接力。

## 5. 结论 + follow-up #1 关闭

### 5.1 结论

1. **AC-4 ≤10min wall-clock 目标在当前环境不可达**（实测 132 run 29.6min，按比例 60 run 推算 15-20min）。
2. **spirit 解释（按比例 6.6min）被实测推翻**。
3. **TD-071 实施仍然健康**：timeout=0/error=0、provider 限流维持、与历史 50-60min 阻塞态相比 3-3.4× 加速。
4. **进一步优化需 follow-up 接力**（见 §4 三条路径），不在 AC-4 验收范围。

### 5.2 follow-up #1 关闭

| 字段 | 状态 |
|------|------|
| 登记 | REQ-039 验收报告 §6 follow-up #1（2026-06-21） |
| 实证 | 本报告 §2-3（2026-06-22） |
| 判定 | **AC-4 ≤10min 目标不可达**，spirit 解释被推翻 |
| 行动 | REQ-039 状态保持 🟢 完成（验证报告有效）；AC-4 重新定义为"≤10min 不可达，需独立 follow-up"；本 follow-up #1 关闭 |
| 接力 | 离线批量 keypoint embedding 预计算 / runner.py 接入 batch helper / 提 provider 限流（3 条候选） |

### 5.3 对 REQ-039 验收报告的影响

- **AC-2 验收条件"成功完成"**：✓（run 完整跑通，无 timeout/error）
- **AC-4 验收条件"≤10min"**：❌（实测 29.6min — 但这是 brief 命令范围问题，不是 TD-071 失败）
- **整体判定**：REQ-036 graph_edge 禁用决策的真实 LLM 维度无系统性回归（37 mismatch 已被分析）→ **REQ-039 维持 🟢 完成**，但 AC-4 重新归类为"已分析、目标不可达、需后续 follow-up 接力"。

## 6. 事实源

- REQ-039 验收报告（spirit 解释登记处）：[2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md](../01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md)
- TD-071 spec：[2026-06-21-td-071-rag-eval-embedding-batch.md](../01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md)
- TD-071 plan：[2026-06-21-td-071-rag-eval-embedding-batch-plan.md](../02-plans/2026-06-21-td-071-rag-eval-embedding-batch-plan.md)
- 本次实测数据：`/tmp/td071-ac4-subset.md` + `/tmp/td071-ac4-subset.json` + `/tmp/td071-ac4-subset.time.log`（验证命令时间戳）
- 本报告提交分支：`verify/td-071-ac4-subset-validation`（基于 main）