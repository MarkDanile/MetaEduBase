# TD-073 Plan: 离线批量 keypoint embedding 预计算落盘（实施）

> Status: 🟡 进行中
> Created: 2026-06-30
> Source: TD-073 spec [`docs/02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md`](../01-specs/2026-06-30-td-073-offline-keypoint-embedding.md)
> Spec: 同上（218 行）
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-073`
> Branch: `feat/td-073-offline-keypoint-cache-impl`

## 1. 目标（重申 spec 范围）

把 `scripts/rag_validation/coverage.py` 进程内 `_EMBEDDING_CACHE` 升级为**落盘 cache**（`docs/.cache/rag_validation_keypoint_embeddings/<key>.json`），跨 run 复用 fixture 静态 keypoint (term+synonyms) embedding。AC-4 重新定义 ≤15min（叠加 TD-072 接力后 ≤10min）。

## 2. 实施拆分（3 task / TDD）

### Task 1: `cache_store.py` 模块（纯函数 + I/O）— RED → GREEN

**目标**：新建 `scripts/rag_validation/cache_store.py`（约 100 行），含 `compute_cache_key` / `save` / `load` / `collect_unique_texts` 4 个纯函数。

**RED 步骤**：
- 新建 `packages/server-python/tests/scripts/rag_validation/test_cache_store.py`
- 写 9 个测试 case（每个对应一个函数行为边界）：
  1. `test_compute_cache_key_deterministic_for_same_inputs` — 同 fixture paths + mtimes → 同 key
  2. `test_compute_cache_key_changes_when_fixture_mtime_changes` — 改 mtime → key 变
  3. `test_compute_cache_key_changes_when_fixture_path_added` — 多一个 path → key 变
  4. `test_compute_cache_key_includes_schema_version` — `"keypoint_v1"` 前缀：版本变 → key 变
  5. `test_collect_unique_texts_dedups_and_lowercases` — 同一 term 出现多次 → set；混合大小写 → lowercase
  6. `test_collect_unique_texts_includes_synonyms` — `term` + `synonyms` 都进入
  7. `test_save_load_round_trip` — save → load → dict 等价
  8. `test_load_returns_none_for_missing_key` — 不存在的 cache_key → None（不抛错）
  9. `test_save_creates_target_dir_if_missing` — 目标目录不存在 → 自动 mkdir

**GREEN 步骤**：写 `cache_store.py` 4 函数（spec §5.3 / §5.4 已给出 cache_key 算法 + JSON schema）。**保持 I/O 边界窄**：save 失败 → 抛 + 让 caller 处理；load 失败（JSON 损坏 / 字段缺失）→ 返回 None + 警告。

**测试位置**：`packages/server-python/tests/scripts/rag_validation/test_cache_store.py`（与 TD-074 `test_coverage_batch_routing.py` 同包）。继承已有 conftest.py（已 inject REPO_ROOT + scripts/）。

**RED 验证**（与 TD-074 同样路径）：
- 跑 `pytest packages/server-python/tests/scripts/rag_validation/test_cache_store.py -v` 看 import / 函数缺失导致的 RED
- 实现 `cache_store.py` 后跑 GREEN

### Task 2: `coverage.py` 启动钩子 + miss 累加写盘 — RED → GREEN

**目标**：在 `coverage.py` 引入持久化层概念 + 启动时载入 + miss 时累加。

**改动**（4 处，约 +30 行）：
1. **新增模块级 dict** `_KEYPOINT_CACHE_PENDING: dict[str, list[float]] = {}`（miss 累加）
2. **新增 `_load_keypoint_cache(questions, cache_dir) -> None`**：
   - 调 `cache_store.collect_unique_texts(questions)` 收集 unique texts
   - 调 `cache_store.compute_cache_key(fixture_paths)`（从 `Question.group` 映射到 fixture 路径——需要新 helper）
   - 调 `cache_store.load(cache_key, cache_dir)` → 若非 None，灌入 `_EMBEDDING_CACHE`
3. **改 `_get_cached_embeddings_batch` miss 分支**：写入 cache 时**同步**写入 `_KEYPOINT_CACHE_PENDING[t] = emb`
4. **新增 `_save_keypoint_cache(cache_dir) -> None`**：
   - 合并 `_EMBEDDING_CACHE` + `_KEYPOINT_CACHE_PENDING`（去重）
   - 调 `cache_store.save(merged, cache_key, cache_dir)`
   - save 失败 → `print warning, do not raise`（不阻断主流程）

**RED 步骤**（在 `test_coverage_batch_routing.py` 加 4 个新测试，或新建 `test_coverage_persistent_cache.py`）：
1. `test_load_keypoint_cache_populates_embedding_cache_from_disk` — 预先写 cache 文件 → 调 `_load_keypoint_cache` → `_EMBEDDING_CACHE` 有内容
2. `test_load_keypoint_cache_with_no_existing_file_is_noop` — cache 文件不存在 → 静默跳过 + `_EMBEDDING_CACHE` 仍空
3. `test_get_cached_embeddings_batch_records_miss_to_pending_cache` — 调 _get_cached_embeddings_batch → 验证 `_KEYPOINT_CACHE_PENDING` 含 miss 的 texts
4. `test_save_keypoint_cache_persists_pending_and_in_memory` — 调 `_save_keypoint_cache` → 读盘验证文件含 merged 内容

**关键问题**：`fixture_paths` 从哪里来？——`Question.group` 只有 "REQ-016" / "REQ-018" / "REQ-026" / "REQ-028" 字符串。`_load_questions` 接 4 个 path 参数（`req016_samples` / `req018_samples` / `req016_samples` / `req028_samples`）。需要把 group→path 映射传给 cache_key 计算。

**方案 A**（最简）：`_load_keypoint_cache` 接 4 个 fixture paths 参数（`main.py` 传）。  
**方案 B**（不侵入接口）：`Question` 增加 `fixture_path: Path` 字段，`_load_questions` 填充。  

**采用 A**——更小侵入 + 不动 dataclass（保持 model 简单）。

**GREEN 步骤**：写 4 个新增函数 / 改动 + 跑 4 个 RED → GREEN。

### Task 3: `main.py` 启动载入 + 退出保存 — RED → GREEN

**目标**：在 `_run` 启动时调 `_load_keypoint_cache`，退出时调 `_save_keypoint_cache`。

**改动**（`main.py`，约 +8 行）：
- 新增 CLI flag `--cache-dir <path>`（默认 `docs/.cache/rag_validation_keypoint_embeddings`）
- `_load_questions(...)` 之后：调 `coverage._load_keypoint_cache(questions, cache_dir, [req016_path, req018_path, req026_path, req028_path])`
- `_run` 退出前（return 之前）：调 `coverage._save_keypoint_cache(cache_dir, [req016_path, req018_path, req026_path, req028_path])`
- 失败兜底：save 失败 → log warning + 继续（不阻断 main 流程）

**RED 步骤**（在 `test_cache_store.py` 或新建 `test_main_integration.py`）：
- 这个层级的测试需要 mock 整个 `_run` flow（DB / session / settings）。**复杂度高**。
- **替代方案**：在 `test_coverage_persistent_cache.py`（Task 2 新建）加 1 个集成测试：直接调 `main._run` 模拟 fixture + cache_dir，验证 load/save 副作用。

**简化决策**：把 main.py 改动**作为纯 plumbing**（不写专门测试），由 Task 2 的 coverage 层测试间接覆盖。**风险** = main.py 的 fixture path 映射写错（路径顺序与 group 不对应）。Mitigation：4 个 fixture paths 在 main.py 是显式参数，写成命名字典避免顺序错乱。

**GREEN 步骤**：直接写 main.py 改动 + 跑 `test_coverage_persistent_cache.py` 验证（间接覆盖）。

## 3. Task 依赖顺序

```
Task 1 (cache_store.py + 9 tests)
   ↓
Task 2 (coverage.py 启动钩子 + 4 tests)  ← 依赖 Task 1 的 cache_store
   ↓
Task 3 (main.py 集成 + 不写专门测试)    ← 依赖 Task 2 的 coverage API
```

**严格 TDD**：每 Task 跑 RED → 看 fail 原因 → 实现 → GREEN，再进下一 Task。

## 4. 验证策略

### 4.1 单测（pytest）

| 命令 | 期望 |
|------|------|
| `pytest packages/server-python/tests/scripts/rag_validation/test_cache_store.py -v` | 9 PASS |
| `pytest packages/server-python/tests/scripts/rag_validation/test_coverage_persistent_cache.py -v` | 4 PASS |
| `pytest packages/server-python/tests/scripts/rag_validation/ -v`（全套） | 26 (TD-074) + 9 (TD-073 Task 1) + 4 (TD-073 Task 2) = 39 PASS |
| `pytest tests/engineering/ -q` | 38 PASS（无回归） |

### 4.2 端到端（手动 smoke）

不在 CI；**留给后续 verify 分支**（AC-4 实证）。本 PR 仅 lock 单元行为。

### 4.3 门禁

- `python scripts/check-engineering-docs` exit 0
- `ruff check scripts/rag_validation/ packages/server-python/tests/scripts/` 0 violations
- `git diff --check` clean

## 5. 风险 + 缓解

| 风险 | 缓解 |
|------|------|
| fixture mtime 抖动（IDE 自动保存）→ cache 频繁失效 | 备选升级为 fixture 内容 sha256（spec §6 已记）；当前用 mtime 起步，未来若抖动多再升级 |
| 180 texts × 4096 dim × 4 byte ≈ 3MB JSON serialize < 1s | 实测；若慢则升级 msgpack（spec §5.4 已记） |
| `_KEYPOINT_CACHE_PENDING` 与 `_EMBEDDING_CACHE` 双层 dict 容易混淆 | 文档 + 单测明确区分：`_EMBEDDING_CACHE` 是 run-time fast path，`_KEYPOINT_CACHE_PENDING` 是 save-time accumulator |
| save 失败（磁盘满、权限）→ 主流程断 | spec §5.5 明确：log warning + 不抛 + 不阻断；单测覆盖 failure path |
| 跨 run 行为：fixture 改了 → cache_key 变 → load 命中 None → 走 miss 路径（正常） | Task 1 测试 3 (`test_compute_cache_key_changes_when_fixture_path_added`) 锁死 |
| `Question.group` 到 fixture path 映射写错 → cache_key 不稳定 | main.py 用 **命名参数** + 显式列表（不依赖位置顺序）；Task 1 测试 2 锁死 mtime 敏感性 |

## 6. 不在范围（explicit out-of-scope，spec §8 同步）

- 不动 `embedding_service.py` / `get_embedding_with_timeout_batch`（TD-071 范围）
- 不动 `_get_cached_embeddings_batch` 内部 batch 逻辑（TD-071/072 范围）
- 不接路径 2（runner.py batch 化 answer+recall）—— 独立 TD
- 不接路径 3（provider 限流）—— OPS
- 不改生产代码 `packages/server-python/app/contexts/knowledge/`
- 不写 `_run` 端到端集成测试（DB 依赖复杂；改用 Task 2 间接覆盖）
- 不持久化 `_EMB_STATS`（统计是 per-run 状态，不跨 run）
- 不接 `--cache-dir <path>` 外的 env 配置（默认路径足够）

## 7. 完成标准（spec §4 + 本 plan 展开）

| AC | 内容 | 状态 |
|----|------|------|
| AC-1 | `cache_store.py` 新建 + `save/load/cache_key/collect_unique_texts` 4 函数 + JSON 序列化 | Task 1 |
| AC-2 | `coverage.py` 启动钩子 + miss 累加 + 退出 flush | Task 2 + Task 3 |
| AC-3 | `cache_key = sha256(fixture paths + mtimes + "keypoint_v1")[:16]` | Task 1 |
| AC-4 | 落盘路径 `docs/.cache/rag_validation_keypoint_embeddings/<key>.json` + `--cache-dir` CLI 覆盖 | Task 1 + Task 3 |
| AC-5 | 单测 9 (cache_store) + 4 (coverage) = 13 个新测试 | Task 1 + Task 2 |
| AC-6 | 端到端 smoke（不在本 PR 范围，登记给后续 verify） | 推迟到独立 verify 分支 |
| AC-7 | 文档同步：technical-debt.md / current-work / work-log / spec 状态 | 本 plan closeout |

## 8. 交付序列

1. **本 PR 范围**：Task 1 + Task 2 + Task 3 + closeout
2. **后续 verify 分支**（不在本 PR）：跑 `--limit 2 --allow-llm` smoke（验证 cache 写入正常）；跑同命令第二次（验证 cache 命中、HTTP 数 0）；AC-4 ≤15min 实测

## 9. Self-review check

- [x] Plan 覆盖 spec 全部 AC
- [x] TDD 顺序：先 RED 测试 → 实现 → GREEN
- [x] 风险有缓解措施
- [x] 不在范围显式声明
- [x] 验证命令明确
- [x] 依赖关系清晰
