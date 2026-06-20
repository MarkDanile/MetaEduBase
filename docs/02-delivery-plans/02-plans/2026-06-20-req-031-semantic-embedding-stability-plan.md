# REQ-031 P2 semantic embedding 覆盖率稳定性 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-031-semantic-embedding-stability.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md`
> Base script: `scripts/validate_req024_p2_real_validation.py`

## Scope

`_compute_semantic_embedding_coverage` 加进程内 embedding 缓存 + `asyncio.wait_for` 硬超时 + 降级。不修改生产 `embedding_service.py`，不引入新依赖。

## Slice 1 — 缓存 + 超时改造

**文件**：`scripts/validate_req024_p2_real_validation.py`（修改）

**改动**：

1. **新增** 模块级 `_EMBEDDING_CACHE: dict[str, list[float]] = {}`
2. **新增** `_get_cached_embedding(text, embedding_callable) -> list[float] | None`:
   - cache hit 直接返回
   - miss 时 `asyncio.wait_for(embedding_callable(text), timeout=60.0)`
   - 超时 / 异常返回 None（降级，不抛）
   - 成功写入缓存
3. **改造** `_compute_semantic_embedding_coverage`:
   - answer embedding 走 `_get_cached_embedding`（answer 文本跨 scenario 不同，但同 scenario 内只算一次）
   - keypoint candidate embedding 走 `_get_cached_embedding`（跨 4 scenarios 命中）
   - 保留 `_EMB_SEMAPHORE`（未来并发化保护）
4. **日志**：缓存命中 / miss / 超时降级计数，写报告诊断段

**验收**：
- `python -m py_compile` 通过
- `ruff check` 通过
- 旧字段不变

## Slice 2 — dry-run 验证

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/req031_dry.md \
  --report-title "REQ-031 dry-run (cache + timeout)"
```

**验收**：exit 0，0 scenario errors。

## Slice 3 — `--allow-llm` 真 LLM 重跑 v3

**命令**：
```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md \
  --json-out /tmp/req031_real.json \
  --report-title "REQ-031 v3 re-run (cache + timeout, real LLM)" \
  --allow-llm
```

**验收**：
- exit 0，无 1h+ 挂起（预计 ~5-10 分钟）
- semantic_emb 非零 sample ≥ 5/10（AC-3）
- Spearman ρ 如实计算（AC-4）
- REQ-030 AC-4 / AC-5 补判（AC-5）

## Slice 4 — 文档收口 + Git 闭环

**文件改动**：
- `docs/01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md` — Status: 进行中 → Done / 部分收口
- `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md` — 覆盖式重跑 + AC 补判
- `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md` — AC-4/5 补判 + Status
- `docs/01-product-planning/02-milestones/02-growth-phase.md` — REQ-030 / REQ-031 状态
- `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md` — REQ-030 / REQ-031 状态
- `docs/01-product-planning/04-backlog.md` — REQ-030 / REQ-031 状态
- `docs/03-engineering-governance/current-work.md` — 候选 → 最近完成
- `docs/03-engineering-governance/work-log.md` — 一行索引

**Git 闭环**：
```bash
git commit -m "feat(rag): REQ-031 semantic embedding cache + timeout stabilization"
git push origin feat/req-031-semantic-embedding-stability
gh pr create --title "REQ-031 P2 semantic embedding 覆盖率稳定性 (cache + timeout)"
gh pr merge --squash --delete-branch
```

**验收**：
- `gh pr view <PR>` state = `MERGED`
- 本地 `main` 已 fast-forward
- `scripts/check-engineering-docs` 通过

## Files To Inspect First

- `scripts/validate_req024_p2_real_validation.py`（`_compute_semantic_embedding_coverage` + `_EMB_SEMAPHORE`）
- `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`（诊断段）
- `packages/server-python/app/contexts/knowledge/application/embedding_service.py`（get_embedding 4096 维）

## Required Checks

- `python -m py_compile scripts/validate_req024_p2_real_validation.py`
- `ruff check scripts/validate_req024_p2_real_validation.py`
- `git diff --check`
- `scripts/check-engineering-docs`
- 真 LLM 验收：`--allow-llm` 退出码 0 且无 1h+ 挂起

## Follow-up (Out of Scope)

- 若缓存+超时仍无法产出非 0：评估 sentence-transformers 本地 embedding（独立 PR）
- 重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR）
- TD-032 脚本拆分（独立任务）
