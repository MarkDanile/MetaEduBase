# TD-073 Spec: 离线批量 keypoint embedding 预计算落盘

> Status: 🔵 候选（docs-only 规格，待用户决策实施）
> Created: 2026-06-30
> Source: REQ-037 follow-up #2 + AC-4 子集验证报告 §4 路径 1 + TD-071 交付记录「已知 spec 偏差」
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-073`（待登记）
> Plan: 待登记（不在本 PR 范围）

## 1. Problem Statement

`scripts/rag_validation/coverage.py` `_EMBEDDING_CACHE`（REQ-031）是**进程内**缓存：脚本每次启动从空开始，跨 run 必须重算 keypoint embedding。REQ-031 把 27 样例 × 6 scenario 单次 dry-run 的 keypoint embedding HTTP 数从 4400 降到 ~140（hit=86%），但 AC-4 子集验证实测仍 132 run 29.6min（按比例 60 run 推算 15-20min，spirit 解释 6.6min 被推翻）。

**真正问题**：keypoint term+synonyms 文本在测试 fixture 内**静态**，跨 run 完全相同，但当前每个 run 都需重新计算一次（即使 cache 命中，hit 也是本次进程内累积产生）。把缓存从进程内升级为落盘：

- 启动时载入 cache（已有 embeddings 直接复用，不发 HTTP）；
- cache miss 时调用 `_get_cached_embeddings_batch` 计算并写盘；
- 下次启动同 fixture 命中，HTTP 数从 ~140（单进程累积）降到 ~0。

### 1.1 量化

精确算账（实测 7 fixture，2026-06-30 跑统计）：

| 维度 | 数值 |
|------|------|
| Fixture 数 | 7 |
| 总 keypoint entry | 100 |
| 唯一文本（term+synonyms union） | **180** |
| 单次全量 run | 162 run = 27 sample × 6 scenario |
| 旧 HTTP 数（keypoint coverage 路径，无 cache） | 100 × 162 = **16200** |
| 旧 HTTP 数（带 REQ-031 进程内 cache，hit 86%） | ~140 |
| 新 HTTP 数（落盘 cache 命中） | **0**（假设 fixture 不变） |
| 新 HTTP 数（fixture 首次/变更） | 180（一次性） |
| AC-4 子集（60 run，10 sample × 6 scenario）旧 | 100 × 60 = 6000（cache 后 ~840） |
| AC-4 子集新 | 0（落盘命中） |
| 估算节省（AC-4 全场景） | 旧 840 × 25-30s ≈ 5.8-7h；新 0 |

> 远超 AC-4 §4 报告估计的"省 50%"（§4 未算 run 维度摊销；每个 keypoint 在每个 run 都重算，进程内 cache 命中率受样本多样性压制到 86%）。

### 1.2 与其他路径的关系

AC-4 子集验证报告 §4 列出 3 条优化路径，本 spec 覆盖**路径 1**：

| 路径 | 范围 | 归属 |
|------|------|------|
| 1. 离线 keypoint 预计算（**本 spec**） | fixture 静态文本落盘 | TD-073 |
| 2. runner.py 接 `get_embeddings_with_timeout_batch` | 跨 run batch 化 answer+recall | TD-071 §5 偏差接力，独立 TD |
| 3. `_EMB_SEMAPHORE` 提升到 4-5 | provider 配额侧 | OPS / env 配置 |

**路径 1 + 路径 2 叠加**：路径 1 消除 keypoint 文本的 HTTP，路径 2 把 answer+recall 文本 batch 化（每 run 1-2 HTTP 替代 1-2 sequential HTTP）。叠加后 AC-4 ≤10min 可达。

## 2. Goal

把 `_EMBEDDING_CACHE` 从进程内 dict 升级为落盘 cache：

- 启动时：若 fixture 内容未变，载入已有 embedding，不发 HTTP；
- 运行中：cache miss 走 `_get_cached_embeddings_batch`，结果写盘；
- fixture 内容变更：cache key hash 变更，自动失效。

### 2.1 AC-4 重新定义

按子集验证报告 §3 + §5.2 重新定义 AC-4 wall-clock 目标：

- **新 AC-4**：路径 1 实施后，全量 60 run（REQ-028 v3 10 sample × 6 scenario）`--allow-llm` wall-clock ≤ 15min（原 ≤10min 不可达已诚实登记；路径 1+2 叠加后可达 ≤10min，由后续 TD 接力）。

## 3. Non-Goals

- 不改 `embedding_service.py` 的 batch helper（TD-071 已落地，无需再动）。
- 不动 `_get_cached_embeddings_batch` 实现（TD-071 行为正确，本 spec 仅在 cache 写入处增加落盘）。
- 不改 fixture 加载逻辑 `_load_questions`（loader.py 保持现状）。
- 不引入外部存储（DB / Redis）—— 用文件系统 + JSON/PKL 即可。
- 不改主链路 `packages/server-python/app/contexts/knowledge/` 任何代码（落盘 cache 是**校验脚本私有**，与生产 chat 无关）。
- 不接路径 2（runner.py batch 化 answer+recall）—— 独立 TD，本 spec 仅做 keypoint 落盘。
- 不接路径 3（provider 限流提升）—— OPS 范围。

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `scripts/rag_validation/cache_store.py` 新建：`save(texts_to_embeddings: dict[str, list[float]], cache_key: str, target_dir: Path)` + `load(cache_key: str, source_dir: Path) -> dict[str, list[float]] \| None`。JSON 序列化（可读、可调试、git-diff 友好）；fallback 无 schema 风险。 | 代码审查 + 单测 |
| AC-2 | `coverage.py` 启动钩子：在 `_compute_semantic_embedding_coverage` 首次调用前，**或** `main.py` `_run()` 入口，调用 `_KEYPOINT_CACHE.load(cache_key)`；若命中，写入 `_EMBEDDING_CACHE` dict（不调 HTTP）。cache miss 走原 `_get_cached_embeddings_batch`，新增写盘（`_KEYPOINT_CACHE.save(...)` 累加）。 | 代码审查 + 单测 |
| AC-3 | `cache_key` 设计：sha256(`fixture_path` 序列 + fixture mtime 序列 + `"keypoint_v1"`) 取前 16 hex。任一 fixture 内容/路径变化 → hash 变 → cache 自动失效。 | 代码审查 + 单测（手动改 fixture 触发失效） |
| AC-4 | 落盘路径：`docs/.cache/rag_validation_keypoint_embeddings/<cache_key>.json`（`.cache` 是 docs 内部 cache 目录，已 .gitignore——按 repo 现有约定 `docs/.cache/` 是隔离区）。可选 `--cache-dir <path>` CLI 覆盖（默认走约定路径）。 | 代码审查 + 路径检查 |
| AC-5 | 单测：cache_store save/load round-trip / cache_key 变更触发失效 / 不存在的 cache_key 返回 None / 同 cache_key 但 fixture mtime 变化返回 None。 | pytest |
| AC-6 | 端到端：跑 `--limit 2 --allow-llm` smoke（验证 cache 写入正常）；跑同命令第二次（验证 cache 命中、HTTP 数 0）；`git diff` 不应有意外改动；`ruff check` + `scripts/check-engineering-docs` 通过。 | pytest + 门禁 |
| AC-7 | 文档同步：`docs/03-engineering-governance/technical-debt.md` 新增 TD-073 卡（状态 🔵 候选）；`docs/03-engineering-governance/current-work.md` 候选区登记本 spec 引用；`docs/03-engineering-governance/work-log.md` 不动（spec 不是完成事件）。 | 文件检查 |

## 5. Architecture

### 5.1 数据流

```text
启动
  │
  ▼
load_questions(fixture_paths)
  │
  ▼
collect unique keypoint texts (term + synonyms)
  │
  ▼
compute cache_key = sha256(fixture_paths + mtimes + "keypoint_v1")
  │
  ▼
_KETPOINT_CACHE = load(cache_key) ──── 命中? ─┐
  │                                            │
  │ miss                                        │ hit
  ▼                                            ▼
_EMBEDDING_CACHE ← _KETPOINT_CACHE          _EMBEDDING_CACHE ← _KETPOINT_CACHE
  │
  ▼
_run loop（已有）：
  _get_cached_embedding(text) → cache hit OR batch miss → save(persist)
  │
  ▼
每次 miss → batch fill + 累加 write _KEYPOINT_CACHE → save at end of run
```

### 5.2 模块划分

| 模块 | 职责 | 文件 |
|------|------|------|
| `cache_store` | 落盘 save/load、cache_key 计算 | `scripts/rag_validation/cache_store.py`（新建） |
| `coverage` | 启动时载入 + miss 时累加写盘 | `scripts/rag_validation/coverage.py`（改） |
| `main` | 启动钩子（fixture 收集 + cache 载入） | `scripts/rag_validation/main.py`（小改） |

### 5.3 cache_key 计算

```python
import hashlib
from pathlib import Path

def _compute_cache_key(fixture_paths: list[Path]) -> str:
    """Stable cache key derived from fixture paths + mtimes + schema version."""
    parts = ["keypoint_v1"]  # schema version: bump on cache format change
    for p in sorted(fixture_paths):
        if not p.exists():
            continue
        parts.append(str(p.resolve()))
        parts.append(str(p.stat().st_mtime_ns))
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

### 5.4 cache 文件格式

```json
{
  "cache_key": "abc123def456",
  "schema_version": "keypoint_v1",
  "fixture_hashes": {
    "tests/fixtures/.../req028_v3.example.json": 1700000000.0,
    ...
  },
  "created_at": "2026-06-30T12:00:00Z",
  "embedding_dim": 4096,
  "texts": {
    "装饰器": [0.012, -0.034, ...],
    "decorator": [0.001, 0.023, ...],
    ...
  }
}
```

文件大小估算：180 texts × 4096 dim × 4 byte ≈ 3 MB；JSON 序列化后约 5-6 MB（数字字符开销）。可接受。

### 5.5 写入策略

- **累加**：miss 后 append 到 `_KEYPOINT_CACHE["texts"]`，**不**每次 miss 都 save（IO 抖）。
- **flush 时机**：`main.py` `_run()` 退出前一次性 save（`_KEYPOINT_CACHE.save()`）。
- **失败兜底**：save 失败（如磁盘满、权限）→ log warning + 不抛异常（不阻断主流程；下次启动 cache miss 重算即可）。

## 6. Risks & Mitigations

| 风险 | 缓解 |
|------|------|
| Fixture mtime 抖动（IDE 自动保存等）→ cache 频繁失效 | 备选方案：改用 fixture 内容 sha256（更稳）；当前 spec 用 mtime + schema_version，对开发体验影响小（失效 = 一次 180 HTTP ≈ 75-90min，仍比当前 50-60min × N 次跑优）。后续若发现抖动多，再升级。 |
| 多机/多账户跑 cache 不一致 | cache 在 `docs/.cache/`，按 user/机器本地路径（不入 git）；不同机器首次跑各自预计算，后续稳定。 |
| Cache 文件膨胀 | 180 texts × 3 MB = 5 MB 单文件；cache_key 失效自动清理；不需要 LRU。 |
| JSON 序列化慢 | 180 texts 一次性 serialize ≈ < 1s，可忽略；若未来扩展到 10K texts 改用 msgpack。 |
| 落盘 cache 与 REQ-031 进程内 cache 双层混淆 | 明确：进程内 cache = run 内 fast path；落盘 cache = run 间 persistent path；二者不冲突（hit 顺序：先查进程内 dict，无再查落盘载入 dict，再 miss 调 HTTP）。 |

## 7. Validation Plan

| 步骤 | 命令 / 操作 | 期望 |
|------|-------------|------|
| 1 | `pytest tests/rag_validation/test_cache_store.py -v` | 全部 pass（AC-5） |
| 2 | `pytest tests/rag_validation/ -v` | 现有测试无回归 |
| 3 | `python scripts/validate_req024_p2_real_validation.py --limit 2 --allow-llm`（首次） | cache 文件生成，HTTP 数 = 唯一 texts 数（180） |
| 4 | 重复步骤 3 第二次 | cache 命中，HTTP 数 ≈ 0（keypoint 路径） |
| 5 | 修改 fixture 任意 keypoint text → 步骤 3 | cache_key 变，新 cache 文件；HTTP 数 = 新 unique texts 数 |
| 6 | `ruff check scripts/rag_validation/` | 0 violations |
| 7 | `python scripts/check-engineering-docs` | exit 0 |
| 8 | `git diff --check` | clean |

### 7.1 AC-4 实证（不在本 spec 范围，仅登记）

TD-073 实施后，下一轮 AC-4 验证（建议建独立 verify 分支）：

- `--req028-samples` 不传 `--weak-recall-samples`（按子集验证 §2.1 命令）
- 期望 wall-clock ≤ 15min（保守）；若叠加路径 2 接力后可达 ≤ 10min

## 8. Out-of-Scope (Explicit)

- 不动 `embedding_service.py` / `get_embedding_with_timeout` / `get_embeddings_with_timeout_batch`（TD-071 范围）。
- 不动 `_get_cached_embeddings_batch` 内部 batch 逻辑（TD-071 范围）。
- 不改 fixture 文件（loader.py 保持现状）。
- 不接路径 2（runner.py batch 化 answer+recall）—— 独立 TD，本 spec 完成后才考虑。
- 不接路径 3（provider 限流）—— OPS，不在本 spec 范围。
- 不改生产代码 `packages/server-python/app/contexts/knowledge/`。
- 不写 `docs/02-delivery-plans/02-plans/` 实施计划（plan 在实施启动时另开 PR）。

## 9. 参考

- AC-4 子集验证报告：[2026-06-22-td-071-ac4-subset-validation-report.md](2026-06-22-td-071-ac4-subset-validation-report.md) §4 + §5
- REQ-037 验收报告 §6 follow-up #2：[2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md](2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md)
- TD-071 实施 + 交付记录：[docs/03-engineering-governance/technical-debt.md#td-071](../../03-engineering-governance/technical-debt.md#td-071) 已知 spec 偏差
- TD-070 vector-recall 超时兜底 spec：[2026-06-21-td-070-vector-recall-timeout.md](2026-06-21-td-070-vector-recall-timeout.md)
- REQ-031 semantic embedding 稳定性：[2026-06-20-req-030-new-quality-metric-report.md](2026-06-20-req-030-new-quality-metric-report.md)（进程内 cache 起源）