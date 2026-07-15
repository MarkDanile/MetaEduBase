# BUG-013 — 业务 tests 失败：asyncpg 不支持 SQLAlchemy `:vec::vector` 占位符 + cast

> Status: 🟢 Done
> Priority: P1
> Area: 后端 / 业务 tests / pgvector 集成
> Created: 2026-07-01
> Reporter: AC-4 verify follow-up / 业务 tests 修复（候选区第 2 项）
> Closed: 2026-07-01 (PR #406 `9358c88`)
> ID note: 2026-07-15 Code Review 发现后续另一任务复用了 BUG-013；待 DOC-077 统一重编号，当前链接暂保留。

## 现象

启动 `./dev.sh infra` + `./dev.sh init-db` 后跑 `python -m pytest tests/`：

```
12 failed, 522 passed, 1 skipped, 12 warnings in 88.76s
```

12 failed 测试全部因同一 SQL 语法错：

```
sqlalchemy.exc.ProgrammingError: (asyncpg.ProgrammingError) <class 'asyncpg.exceptions.PostgresSyntaxError'>: syntax error at or near ":"
[SQL: INSERT INTO metaedu.knowledge_nodes (..., embedding, ...) VALUES (..., :vec::vector, ...)]
```

受影响测试（`tests/contexts/knowledge/test_knowledge.py` + `tests/e2e/test_p1_demo.py` 跨 3 个 step）：
- test_create_node / test_create_child_node / test_list_nodes / test_get_node
- test_update_node / test_delete_node / test_search_keyword
- test_tree_root / test_tree_children
- test_p1_demo_step3_template_extract / step4_kg_extract / step5_ai_chat

## 根因（2026-07-01 排查）

`packages/server-python/app/contexts/{document,knowledge}/infrastructure/{chunk,knowledge}_repository.py` 4 处使用 `:vec::vector`（SQLAlchemy named placeholder + PG `::cast`）。asyncpg 协议不支持这种**占位符 + `::cast`** 写法（asyncpg driver 只支持 named placeholder 单一值，不支持占位符后跟 `::type` cast）。

正确写法（PG `CAST(... AS ...)` 函数语法）：
```sql
-- 当前（错）
VALUES (:id, :vec::vector, :now)

-- 应改为
VALUES (:id, CAST(:vec AS vector), :now)
```

或者用 SQLAlchemy 2.x 的 `Vector` 类型 + `bindparam` + dialect-native 处理（更稳但侵入更大）。

## 历史追溯

`git blame` 显示这些 `:vec::vector` 自 **2026-05-13 commit `35206e2c`** 已存在（MarkDanile 引入）。TD-069（PR #366 `ed77227` 2026-06-19）修复 dev DB embedding 列类型与 pgvector 操作符不匹配，但**未触及** SQLAlchemy `text()` 字符串里的 `:vec::vector` 占位符 + cast 语法。

候选区 1（AC-4 真 LLM verify）依赖 `validate_req024_p2_real_validation.py` 全量测试通过才能跑——这 12 个 failing tests 是阻塞项之一。

## 解决路径

**修法**（最小侵入）：
- 4 处 `:vec::vector` → `CAST(:vec AS vector)`
- 文件清单（grep 实测）：
  - `packages/server-python/app/contexts/document/infrastructure/chunk_repository.py:127` — UPDATE chunk embedding
  - `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py:100` — INSERT knowledge_node
  - `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py:332` — SELECT cosine similarity score
  - `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py:334` — SELECT cosine distance order by

**测试**：业务 tests 12 个 failing 应转 PASS。

## 完成标准

- [ ] 4 处 `:vec::vector` → `CAST(:vec AS vector)` 修复
- [ ] `python -m pytest tests/contexts/knowledge/test_knowledge.py -q` → 9/9 PASS
- [ ] `python -m pytest tests/e2e/test_p1_demo.py -q` → 3/3 PASS（test_p1_demo_step3/4/5）
- [ ] `python -m pytest tests/ --ignore=tests/scripts/rag_validation` → 0 failed（522 → 534 passed）
- [ ] `ruff check packages/server-python/app/` 0 violations
- [ ] `python scripts/check-engineering-docs` exit 0
- [ ] `git diff --check` clean

## 验证方式

跑业务 tests 全量 + check-engineering-docs + ruff + pytest tests/scripts/rag_validation/ 无回归。

## 阻塞影响

- 候选 1（AC-4 真 LLM verify）—— 无法跑全量 tests 即无法跑 validate 脚本
- 候选 3（路径 3 `_EMB_SEMAPHORE`）—— 独立 OPS，不依赖此 bug，但业务 tests 失败会让所有 P2 验收被阻断

## Out-of-scope

- 不重写 SQLAlchemy `Vector` 类型层（侵入大）
- 不动 alembic migrations（已正确：`./dev.sh init-db` 跑了 alembic head）
- 不改 `embedding_service.py`（TD-070/071 已修）

## 关联

- TD-068 / TD-069 修复 dev DB schema 与 pgvector operator（PR #366 `ed77227`）—— 本 BUG 是其后续发现
- AC-4 verify 报告（PR #404）§6 follow-up 第 2 项"业务 tests 修复"= 本 BUG

## 交付记录

（待 PR squash merge 后回填）
