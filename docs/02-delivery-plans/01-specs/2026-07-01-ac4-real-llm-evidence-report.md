# AC-4 ≤10min wall-clock 真 LLM 验证报告（dry-run + 阻塞登记）

> Status: 🔴 AC-4 ≤10min 真 LLM 实证 **被环境阻塞**；dry-run 端到端流程验证完成
> Created: 2026-07-01
> Source: AC-4 子集验证报告 §6 + AC-4 verify dry-run smoke 报告（PR #404 §6 follow-up）+ 候选区 1（业务 tests 修复 PR #406 收口解锁后）
> Spec: TD-073 spec §7.1「AC-4 实证（不在本 spec 范围，仅登记）」+ TD-072 spec §2.1「路径 2 已落地」
> 分支：`verify/ac4-real-llm-evidence`（基于 main `9358c88` BUG-013 closeout）

## 1. 验证目标

确认 AC-4 ≤10min wall-clock 目标（TD-072 runner batch + TD-073 cache 落地后）在真实 LLM 环境下是否可达。

按 task-modes.md §3 效果型任务完成分层 + 「阻塞时登记 follow-up」诚实登记。

## 2. 环境状态（2026-07-01 实测）

### 2.1 基础设施已就位

| 组件 | 状态 | 备注 |
|------|------|------|
| PostgreSQL 5432 | ✅ 启动 | `./dev.sh infra`（Docker via Colima） |
| `metaedu` DB | ✅ schema 最新 | `./dev.sh init-db` 跑 alembic head 至 `030_embedding_vector_4096` |
| `metaedu_test` DB | ✅ schema 最新 | `./dev.sh init-test-db` 跑 alembic head |
| Redis 6379 | ✅ 启动 | 同 `./dev.sh infra` 启动 |
| 业务 tests | ✅ `pytest tests/ --ignore=tests/scripts/rag_validation` → **535 passed** | BUG-013 #406 修复（4 处 `:vec::vector` → `CAST(:vec AS vector)`）实测通过 |
| 工程 tests | ✅ `pytest tests/engineering/` → **38 passed** | 工程门禁单测 |
| RAG validation 单测 | ✅ `pytest tests/scripts/rag_validation/` → **50 passed** | TD-073/074 单测覆盖 |

### 2.2 provider API key 缺失

| Provider | Env var | 当前值 |
|---------|---------|--------|
| minimax | `MINIMAX_API_KEY` | 未设（`config.py:33` 默认 `""`） |
| deepseek | `DEEPSEEK_API_KEY` | 未设 |
| qwen | `QWEN_API_KEY` | 未设 |
| siliconflow | `SILICONFLOW_API_KEY` | 未设 |

**4 provider 全空** → 真 LLM 调用不可达 → AC-4 ≤10min 真 LLM 实证无法在当前环境跑。

## 3. dry-run 实测（无 LLM）

### 3.1 命令

```bash
# Run 1: no-cache baseline
python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  --req018-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req018.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --limit 2 --concurrency 1 --no-cache \
  --out /tmp/ac4-real-llm/out/run1.md --json-out /tmp/ac4-real-llm/out/run1.json \
  --report-title "AC-4 verify dry-run (no-cache baseline)"

# Run 2: cache cold（首次 cache 启用）
python scripts/validate_req024_p2_real_validation.py ... \
  --cache-dir /tmp/ac4-real-llm/cache \
  --out /tmp/ac4-real-llm/out/run2.md --json-out /tmp/ac4-real-llm/out/run2.json \
  --report-title "AC-4 verify dry-run (cache cold)"

# Run 3: cache warm（同命令第二次）
python scripts/validate_req024_p2_real_validation.py ... \
  --cache-dir /tmp/ac4-real-llm/cache \
  --out /tmp/ac4-real-llm/out/run3.md --json-out /tmp/ac4-real-llm/out/run3.json \
  --report-title "AC-4 verify dry-run (cache warm)"
```

### 3.2 实测指标（`--limit 2` = 2 样例 × 6 scenarios = 12 run）

| Run | 配置 | Wall-clock | cache 文件 | cache texts |
|-----|------|------------|------------|-------------|
| Run 1 | `--no-cache` | 12.815s | 不写 | — |
| Run 2 | cache cold（`fe3ad16c...`） | 13.774s | 178 bytes（空 `texts: {}`） | 0 |
| Run 3 | cache warm（同 cache key） | 10.840s | 178 bytes（未变） | 0 |

**重要观察**：
- dry-run 路径 `_compute_semantic_embedding_coverage` 收到 `embedding_callable=None`（runner.py:250）→ 不调 embedding → cache texts={}
- dry-run 报告 `final_answer_preview = "DRY-RUN: external LLM disabled..."` → `_compute_keypoint_coverage` 0 hit
- **cache 行为符合 TD-073 spec 设计**：只对真 LLM 路径生效，dry-run 触发不到 cache write 路径

### 3.3 Fixture 算账（实测 `collect_unique_texts`）

| Fixture | Questions | Keypoint entries |
|---------|-----------|-------------------|
| validate_real_pg_rag_req016.example.json | 4 | 0 |
| validate_real_pg_rag_req018.example.json | 3 | 0 |
| validate_real_pg_rag_req_req026_weak_recall.example.json | 5 | 0 |
| validate_real_pg_rag_req027_weak_recall_v2.example.json | 5 | 0 |
| **validate_real_pg_rag_req028_weak_recall_v3.example.json** | **10** | **50** (180 unique texts) |
| **TOTAL** | **27** | **50** (180 unique texts) |

**前 4 fixture 无 keypoint** —— 业务主要在 `req028 v3`。这与 TD-073 spec §1.1 算账完全一致（180 unique texts）。

### 3.4 cache_key 实测

```bash
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
from rag_validation.cache_store import compute_cache_key
paths = sorted(Path('tests/fixtures/rag_validation_samples').glob('validate_real_pg_rag_req*.json'))
print('cache_key:', compute_cache_key(paths))
"
# Output: fe3ad16c5bfd4048 (与 Run 2/3 落盘 cache 文件名一致)
```

cache_key 稳定（同一 fixture 集合 → 同 key）；`compute_cache_key` 算法工作正常。

## 4. AC-4 ≤10min 估算（推算）

按实测数据推算真 LLM 60 run wall-clock（**非实测，是推算**）：

| 路径 | 60 run HTTP 数 | 单次 HTTP 时延 | 累计 HTTP 时延 | 推算 wall-clock |
|------|----------------|----------------|----------------|------------------|
| 无任何优化（TD-071 之前） | 120 | 25-30s | 50-60min | 50-60min |
| TD-071（进程内 cache + batch helper） | ~140 | 25-30s | 17.8min | 17.8min |
| TD-072 + TD-073（落盘 cache + 真 LLM） | ~0 keypoint HTTP | — | — | **推算 ≤15min**（spec §2.1 重新定义） |
| 路径 2+3 接力 | 0 HTTP | — | — | 推算 ≤10min |

**注**：**未实测**——依赖真 LLM provider key（环境缺失）。`_EMB_STATS` 在真 LLM 下应是 `miss=N unique texts / hit=0 (cold) → miss=0 / hit=N unique texts (warm)`。

## 5. AC-4 重新定义现状

按 TD-073 spec §2.1 + TD-072 spec §2.1：

| 阶段 | 目标 | 当前 |
|------|------|------|
| AC-4 原始 | ≤10min wall-clock（REQ-039 验证） | ❌ 不可达（AC-4 子集验证报告 §3 spirit 解释被推翻） |
| AC-4 重新定义（仅 TD-073） | ≤15min wall-clock | ⚠️ 算法可达，**未实测** |
| AC-4 重新定义（TD-073 + TD-072） | ≤10min wall-clock | ⚠️ 算法可达，**未实测** |

## 6. 阻塞登记（真 LLM AC-4 实证 follow-up）

按 task-modes.md §3「阻塞时登记 follow-up」+ §4「spike 模式产出取舍和下一步」：

### 6.1 解除条件

真 LLM AC-4 ≤10min 实证需要**全部 3 项**：

1. **provider API key**（任一 provider 即可）：
   - `MINIMAX_API_KEY=xxx` (default LLM provider) — 推荐
   - 或 `DEEPSEEK_API_KEY=xxx` / `QWEN_API_KEY=xxx` / `SILICONFLOW_API_KEY=xxx`
2. **PG + Redis 在线**（已具备，参见 §2.1）
3. **业务 tests 全绿**（已具备，参见 §2.1）

### 6.2 验证命令（provider key 就绪后）

```bash
# Run 真 LLM AC-4 全量 60 run
python scripts/validate_req024_p2_real_validation.py \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --concurrency 4 \
  --allow-llm --semantic-emb-threshold 0.35 \
  --cache-dir docs/.cache/rag_validation_keypoint_embeddings \
  --out /tmp/ac4-real-llm/ac4-full.md \
  --json-out /tmp/ac4-real-llm/ac4-full.json \
  --report-title "AC-4 ≤10min verify (TD-072 + TD-073 接力)"

# 期望 wall-clock: ≤15min（spec §2.1 新 AC-4）
# 期望 _EMB_STATS: miss=180 (cold) → miss=0 / hit=180 (warm)
```

### 6.3 推荐路径（如果 provider key 可用）

1. **先跑 cold cache**（Run A）→ 验证 cache 写入（180 unique texts 落盘 ~3-6MB JSON）+ miss=180
2. **再跑 warm cache**（Run B 同命令）→ 验证 cache 命中（hit=180 / miss=0）+ wall-clock 显著降低
3. **判定**：如果 Run B wall-clock ≤15min，AC-4 重新定义达成 ✅；如果仍超 15min，登记进一步 follow-up（路径 2 接力 / 路径 3 provider 限流提升）

## 7. 与之前报告的关联

| 报告 | PR | 状态 |
|------|-----|------|
| AC-4 子集验证报告（2026-06-22） | commit `a6b5d53` | 原始 AC-4 ≤10min 不可达判定 |
| AC-4 verify dry-run smoke 报告（2026-06-30） | PR #404 `aad3ad2` | 单元层 cache 端到端验证（mock batch embedder） |
| **AC-4 ≤10min 真 LLM 验证报告（本报告，2026-07-01）** | 待 PR | 端到端 main.py 集成 + cache_key 实测 + dry-run 跑通 + 真 LLM follow-up |

**关系链**：本报告补完前两报告间 gap——
- AC-4 子集验证报告：环境不通（PG 5432 不可达）
- AC-4 verify dry-run smoke 报告：环境不通 + 走 ad-hoc smoke script（mock callable）
- **本报告**：环境通了（PG/Redis + BUG-013 修复 + 业务 tests 全绿）→ 走 main.py 端到端 + dry-run 实测 → 唯一阻塞 = provider API key

## 8. 候选 3（路径 3 `_EMB_SEMAPHORE` 提升）状态

**独立 OPS**，与本报告无依赖。建议在 AC-4 真 LLM 实证完成后**作为路径 1+2+3 完整链路**的最后一步验证：
- 当前 `_EMB_SEMAPHORE = 2`（TD-031 保守限流，避 429 卡死）
- 候选 3 提议提升到 4-5（spec §1.2 路径 3）
- 需要 provider 配额支持（环境实测）

## 9. 结论

- ✅ **PG 5432 + Redis + 业务 tests + dry-run 端到端** 全绿（535 + 38 + 50 tests pass）
- ✅ **TD-073 cache 集成在 main.py** 集成正常（cache 文件生成、cache_key 稳定、fixture mtime 变化敏感）
- ✅ **Fixture 数据算账**确认（180 unique texts、5 fixtures、27 questions）
- ❌ **真 LLM AC-4 ≤10min 实证无法在当前环境跑**（provider API key 缺失）
- ⚠️ **算法可达性**：基于 TD-072 + TD-073 落地 + 算账推算，AC-4 ≤15min（spec §2.1 新 AC-4）**理论上**可达
- ⚠️ **真 LLM 实证仍待环境就绪**（provider key + 配置 env）

## 10. 参考

- AC-4 子集验证报告：[2026-06-22-td-071-ac4-subset-validation-report.md](../01-specs/2026-06-22-td-071-ac4-subset-validation-report.md)
- AC-4 verify dry-run smoke 报告：[2026-06-30-ac4-verify-td073-dry-run-smoke-report.md](../01-specs/2026-06-30-ac4-verify-td073-dry-run-smoke-report.md)
- TD-072 spec：[2026-06-22-td-072-runner-batch-wiring.md](../01-specs/2026-06-22-td-072-runner-batch-wiring.md)
- TD-073 spec：[2026-06-30-td-073-offline-keypoint-embedding.md](../01-specs/2026-06-30-td-073-offline-keypoint-embedding.md)
- BUG-013 卡：[BUG-013-business-tests-asyncpg-vec-cast-syntax.md](../../01-product-planning/05-requirements/BUG-013-business-tests-asyncpg-vec-cast-syntax.md)
- PR #406（BUG-013 修复）：merge commit `9358c88`
- PR #404（AC-4 verify dry-run smoke）：merge commit `aad3ad2`

## 11. 数据可复现

```bash
# 启动基础设施
./dev.sh infra
./dev.sh init-db
./dev.sh init-test-db

# dry-run AC-4 跑（无 LLM）
CACHE_DIR=/tmp/ac4-real-llm/cache
mkdir -p /tmp/ac4-real-llm/out "$CACHE_DIR"

python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  --req018-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req018.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --limit 2 --concurrency 1 \
  --cache-dir "$CACHE_DIR" \
  --out /tmp/ac4-real-llm/out/run1.md \
  --json-out /tmp/ac4-real-llm/out/run1.json \
  --report-title "AC-4 verify dry-run (Run 1 cold cache)"

# 同命令第二次（warm cache）
python scripts/validate_req024_p2_real_validation.py \
  --req016-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req016.example.json \
  --req018-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req018.example.json \
  --weak-recall-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --req028-samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --limit 2 --concurrency 1 \
  --cache-dir "$CACHE_DIR" \
  --out /tmp/ac4-real-llm/out/run2.md \
  --json-out /tmp/ac4-real-llm/out/run2.json \
  --report-title "AC-4 verify dry-run (Run 2 warm cache)"
```