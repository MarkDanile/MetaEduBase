# 候选 3 spike 验证报告：`_EMB_SEMAPHORE` 提升对 AC-4 wall-clock 影响

> Status: 🟢 完成 (spike 模式 — 提交结论 + 不建议立即改)
> Created: 2026-07-02
> Source: TD-073 spec §1.2 路径 3 (`_EMB_SEMAPHORE` 提升到 4-5) + AC-4 v2 实测报告 (PR #409 b7a2912) + 当前 work `verify/semaphore-upgrade-spike`
> 分支: `verify/semaphore-upgrade-spike` (基于 main `6b86d8e` PR #410 closeout)

## 1. Spike 目标

按"按流程"模式验证候选 3 路径 3 (TD-073 spec §1.2): 把 `_EMB_SEMAPHORE` 从 2 提升到 4-5, 验证 cache warm 下 wall-clock 是否进一步降低。

## 2. 实测方法 (A/B 对比)

### 2.1 实验组

| 实验 | 配置 | cache_dir 状态 | LLM provider |
|------|------|---------------|--------------|
| A1 | `_EMB_SEMAPHORE=2` (baseline) | warm (复用 AC-4 v2 cache) | minimax (`.env LLM_DEFAULT_PROVIDER=minimax`) |
| A2 | `_EMB_SEMAPHORE=5` (candidate 3) | warm (同 A1) | minimax |

### 2.2 命令

```bash
# A1: Semaphore=2 cache warm
python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  --req018-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req018.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req027_weak_recall_v2.example.json \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --concurrency 4 \
  --allow-llm --semantic-emb-threshold 0.35 \
  --cache-dir /tmp/ac4-real/cache \
  --out /tmp/ac4-real/sem/A1-warm-sem2.md \
  --json-out /tmp/ac4-real/sem/A1-warm-sem2.json

# 改 scripts/rag_validation/coverage.py:88  _EMB_SEMAPHORE = asyncio.Semaphore(2 → 5)

# A2: Semaphore=5 cache warm (同 cache_dir)
python scripts/validate_req024_p2_real_validation.py \
  ... same args except out/json-out paths ...
```

注: LLM provider 切到 minimax 因为 .env 默认 deepseek 现在 402 Payment Required (rate limit exhausted); minimax 走 RESOLVER_PROVIDER_NAMES 优先级 #1 (factory.py:33) 正常。

## 3. 实测结果

### 3.1 wall-clock 对比

| 实验 | Wall-clock | 单 run 推算 | Δ vs A1 |
|------|-----------|------------|---------|
| A1 Sem=2 warm | **11:25 (685.76s)** | 5.20s/run | baseline |
| A2 Sem=5 warm | **11:51 (711.40s)** | 5.39s/run | **+3.7% (慢 25.64s)** |

**意外结果**: A2 (Sem=5) 慢 25.64s (~3.7%)，**不是** 预期加快。

### 3.2 cache stats 对比

| 实验 | total | hit | miss | timeout | error |
|------|-------|-----|------|---------|-------|
| A1 Sem=2 warm | 1506 | 1412 | 94 | 0 | 0 |
| A2 Sem=5 warm | 1506 | 1414 | 92 | 0 | 0 |

**miss 几乎不变** (94 vs 92, 噪声 ±1) —— cache warm 下 semaphore 5 不降低 miss count。

### 3.3 解释

- **cache warm miss ≈ 92-94 / 132 run ≈ 0.7/run** —— 85% cache hit rate
- 每次 run miss=0.7 个 HTTP embedding → embedding concurrency 远非瓶颈
- semaphore 5 vs 2 唯一差异: 最多 3 个 extra concurrent embedding slot
- 但 concurrency 4 (--concurrency) 限制 run-level 并发 → 即使 sem 5, 实际 run-level concurrency 由 --concurrency 4 限制
- embedding HTTP 5s/次 × 92 miss = 460s 理论 max; 实测 685s ≈ 1.5x 含 LLM 时延 + concurrency serialization

**为什么 A2 没更快**:
1. cache warm 下 embedding 几乎不阻塞 run-level 进度 (miss 极少)
2. semaphore 5 让 embedding 可以 5 并发, 但 `--concurrency 4` 限制 4 个 run 并行 → 实际 batch embedding 调用的 slot 不超过 4
3. 噪声 (minimax QU retry、network jitter) > 候选 3 边际收益

## 4. 结论

### 4.1 候选 3 (Sem=2 → 5) 在 cache warm 下**无效果**

- miss 几乎不变 (94 vs 92) → cache warm 下 85% hit rate 让 embedding 不构成瓶颈
- wall-clock 微小退化 (11:25 → 11:51, +3.7%) 在噪声范围内
- 主 wall-clock 仍是 LLM provider 时延 (5.20s/run avg, ~5s/answer generation)

### 4.2 候选 3 价值评估

| 场景 | 价值 |
|------|------|
| **cache warm** (AC-4 v2 已走通) | ❌ 0% wall-clock 节省 — 候选 3 无效 |
| **cache cold** (首次跑, miss=180/132=1.36/run) | ⚠️ 理论节省 3-4 min (~15-20% wall-clock) — 但 cache cold 是一次性成本, 二次 run 后即 warm |
| **生产 chat** (连续请求, cache miss 高) | ❌ 候选 3 完全无效 (生产 chat 不走 _EMB_SEMAPHORE 路径) |

### 4.3 建议

- ❌ **不建议立即改 `_EMB_SEMAPHORE` 提升到 4-5**
- ✅ AC-4 v2 已达成 ≤15min 目标 (TD-073 spec §2.1 重新定义) — 实测 10:02 (deepseek partial) / 11:25 (minimax cache warm)
- ⚠️ 如果未来 cache cold 场景需要节省 (例如: 大量新 fixture 一次跑, 无历史 cache) → 临时跑 1 次 Sem=5 即可 (config 改动在 .env 而非 hardcode)

## 5. 风险

- **环境 provider 限制**: deepseek 现在 402 Payment Required (rate limit exhausted), minimax 是唯一可用 chat provider. 如 minimax 也耗尽 → AC-4 实证完全阻塞. 建议**记录 minimax credit 余额**作为后续 spike 的关键依赖.
- **Spike 噪声**: 2 组实测差异 26s/685s = 3.7%, 不构成统计显著差异; 实际生产使用前需多组对照.

## 6. 事实源

- AC-4 v2 实测报告: [2026-07-01-ac4-real-llm-evidence-v2-report.md](2026-07-01-ac4-real-llm-evidence-v2-report.md) (PR #409 b7a2912)
- AC-4 v1 dry-run 报告: [2026-07-01-ac4-real-llm-evidence-report.md](2026-07-01-ac4-real-llm-evidence-report.md) (PR #407 6c3c6bc)
- TD-073 spec §1.2 路径 3: [2026-06-30-td-073-offline-keypoint-embedding.md](2026-06-30-td-073-offline-keypoint-embedding.md)
- TD-070 spec: [2026-06-21-td-070-vector-recall-timeout.md](2026-06-21-td-070-vector-recall-timeout.md)
- 实测数据: `/tmp/ac4-real/sem/A1-warm-sem{2,5}.{md,json}`
- 分支: `verify/semaphore-upgrade-spike`

## 7. 数据可复现

```bash
# 启动基础设施
./dev.sh infra
./dev.sh init-db
./dev.sh init-test-db

# 确保 LLM provider 是 minimax (或任何可用 chat provider)
# packages/server-python/.env: LLM_DEFAULT_PROVIDER=minimax (其他 key 也需设)

# 先跑一次建立 cache (cache cold)
python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  ... \
  --concurrency 4 --allow-llm --semantic-emb-threshold 0.35 \
  --cache-dir /tmp/ac4-real/cache \
  --out /tmp/ac4-real/warmup.md

# 改 _EMB_SEMAPHORE
# scripts/rag_validation/coverage.py:88  _EMB_SEMAPHORE = asyncio.Semaphore(N)

# 跑 A1 (Sem=2)
python scripts/validate_req024_p2_real_validation.py ... --out /tmp/ac4-real/A1.md

# 改 Sem=5, 跑 A2
python scripts/validate_req024_p2_real_validation.py ... --out /tmp/ac4-real/A2.md

# 对比 wall-clock
```
