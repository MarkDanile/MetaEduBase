# TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector） — Plan

> Plan 入口：TD-047 实施计划。验收口径见 [`2026-06-11-td-047-zhparser-chinese-tsvector.md`](../01-specs/2026-06-11-td-047-zhparser-chinese-tsvector.md)。
> 任务事实源：[`docs/03-engineering-governance/technical-debt.md#td-047`](../../03-engineering-governance/technical-debt.md#td-047-中文分词回填-iliike-限制p1-数据债衍生)。
> 分支：`chore/td-047-zhparser-chinese-tsvector`（从干净 main `6a974d6` 拉出）。

## 切片划分

按"基础设施先行 + 链路切换 + 测试覆盖 + 真数据验证"原则，6 个切片顺序强依赖。每个切片 1 个原子提交，PR 描述按切片顺序排列：

| 切片 | 内容 | 依赖 | 顺序 |
|------|------|------|------|
| 切片 1 | **PG 镜像加 zhparser**（新增 `Dockerfile.postgres` + dev/prod compose 改 `build:` + image tag） | 无 | 1 |
| 切片 2 | **Alembic 010 迁移**（`CREATE EXTENSION zhparser` + `chinese_zh` 文本搜索配置 + `content_tsvector` 列切字典） | 切片 1 | 2 |
| 切片 3 | **3 个 tsvector 生产者切字典**（`chunk_repository` / `tasks/index` / `backfill_chunk_embedding`） | 切片 2 | 3 |
| 切片 4 | **`backfill_node_source._find_chunk_for_node` 改 `plainto_tsquery`** | 切片 3 | 4 |
| 切片 5 | **覆盖矩阵测试 + test 库扩展**（`test_db_setup.py` + `test_backfill_node_source.py` + `test_chunk_repository.py`） | 切片 4 | 5 |
| 切片 6 | **真 PG 重跑 backfill + 覆盖率报告**（dev 库 `deploy-postgres-1` 重起 + backfill 真跑 + `evidence_coverage_report.py`） | 切片 5 | 6 |

---

## 切片 1：PG 镜像加 zhparser

### Task 1.1 — 新建 `deploy/Dockerfile.postgres`（multi-stage）

- **Builder stage**（`AS builder`）：
  - 基础镜像 `pgvector/pgvector:pg16`。
  - 装 `postgresql-server-dev-16` / `gcc` / `make` / `bzip2` / `git` / `ca-certificates`。
  - `cd /tmp && curl -fsSLo scws-1.2.3.tar.bz2 http://www.xunsearch.com/scws/down/scws-1.2.3.tar.bz2 && tar -xf scws-1.2.3.tar.bz2 && cd scws-1.2.3 && ./configure --prefix=/usr/local && make -j2 && make install && ldconfig`。
  - `cd /tmp && git clone --depth 1 https://github.com/amutu/zhparser.git && cd zhparser && SCWS_HOME=/usr/local make && SCWS_HOME=/usr/local make install`。
  - 锁版本：把 `zhparser` git clone 改成 `--branch <commit-hash>` 或 `--revision <sha>`，避免上游变更导致镜像不可重建。
- **Runtime stage**（基础镜像 `pgvector/pgvector:pg16`）：
  - `--from=builder` 复制 `/usr/local/lib/libscws*` → `/usr/local/lib/`。
  - `--from=builder` 复制 `/usr/local/include/scws/` → `/usr/local/include/scws/`。
  - `--from=builder` 复制 `/usr/lib/postgresql/16/lib/zhparser.so` → `/usr/lib/postgresql/16/lib/`。
  - `--from=builder` 复制 `/usr/share/postgresql/16/extension/zhparser*` → `/usr/share/postgresql/16/extension/`。
  - `--from=builder` 复制 `/usr/share/postgresql/16/tsearch_data/dict.utf8.xdb` → `/usr/share/postgresql/16/tsearch_data/`。
  - `--from=builder` 复制 `/usr/share/postgresql/16/tsearch_data/rules.utf8.ini` → `/usr/share/postgresql/16/tsearch_data/`。
  - 末尾 `ldconfig`。
- **镜像 tag**：`metaedu/postgres-zhparser:pg16`。
- **已知优化**：把 `scws-1.2.3.tar.bz2` 缓存到 `deploy/cache/` 目录（`.gitignore` 加 `deploy/cache/`），Dockerfile 用 `ADD deploy/cache/scws-1.2.3.tar.bz2 /tmp/` + 校验和，避免 xunsearch.com 不可达时 build 失败。

**文件：**
- `deploy/Dockerfile.postgres`（新建）

### Task 1.2 — `deploy/docker-compose.dev.yml` 改 PG 镜像

- 把 `postgres.image: pgvector/pgvector:pg16` 改为：
  ```yaml
  postgres:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.postgres
    image: metaedu/postgres-zhparser:pg16
  ```
- 保留 `volumes` / `environment` / `healthcheck` 不变。
- `pgdata` volume 名保留（数据持久化卷名不变；老 dev 库数据可复用）。

**文件：**
- `deploy/docker-compose.dev.yml`（修改）

### Task 1.3 — `deploy/docker-compose.yml`（生产）改 PG 镜像

- 同 Task 1.2 的 `build + image` 改造。
- 加注释：生产部署时镜像从 registry 拉（`image: metaedu/postgres-zhparser:pg16`），`build:` 在生产 compose 中可注释（避免生产容器意外触发 build）。

**文件：**
- `deploy/docker-compose.yml`（修改）

### Task 1.4 — 本地验证

```bash
# 1. 冷 build（首次会下载 apt 包 + SCWS + zhparser 源码）
cd deploy && docker build -f Dockerfile.postgres -t metaedu/postgres-zhparser:pg16 .. 2>&1 | tail -30
# 预期：退出码 0；总耗时 < 10 min

# 2. 起一个独立测试容器
docker run --rm -d --name zhparser-probe -e POSTGRES_USER=metaedu -e POSTGRES_PASSWORD=dev_only_123 -e POSTGRES_DB=zhparser_probe metaedu/postgres-zhparser:pg16
sleep 5

# 3. 验证 CREATE EXTENSION
docker exec zhparser-probe psql -U metaedu -d zhparser_probe -c "CREATE EXTENSION zhparser; SELECT extversion FROM pg_extension WHERE extname='zhparser';"
# 预期：extversion = 2.4

# 4. 验证 chinese_zh 文本搜索配置可创建
docker exec zhparser-probe psql -U metaedu -d zhparser_probe -c "CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser); SELECT cfgname FROM pg_ts_config WHERE cfgname = 'chinese_zh';"
# 预期：cfgname = chinese_zh

# 5. 验证中文 tsvector
docker exec zhparser-probe psql -U metaedu -d zhparser_probe -c "SELECT to_tsvector('chinese_zh', '中华人民共和国国歌是义勇军进行曲');"
# 预期：返回分词序列（与 spike 验证一致）

# 6. 清理
docker rm -f zhparser-probe
```

### Task 1.5 — 重启 dev 库（保留 pgdata 数据）

```bash
# 1. 停旧容器（pgdata volume 保留）
docker stop deploy-postgres-1 2>/dev/null || true
docker rm -f deploy-postgres-1 2>/dev/null || true

# 2. 用新镜像重起
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
./dev.sh infra
# 预期：deploy-postgres-1 启动，pgdata volume 挂回，老数据（1006 个节点）可访问
```

**验证：**
- `docker exec deploy-postgres-1 psql -U metaedu -d metaedu -c "SELECT count(*) FROM metaedu.knowledge_nodes;"` 退出码 0，count ≈ 1006（与 TD-046 跑后基线一致）。
- `docker exec deploy-postgres-1 psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS zhparser;"` 退出码 0（dev 库应已自带扩展，IF NOT EXISTS 幂等）。

---

## 切片 2：Alembic 010 迁移

### Task 2.1 — 新建迁移文件

- 路径：`packages/server-python/alembic/versions/010_zhparser_chinese.py`。
- `revision = "010_zhparser_chinese"`，`down_revision = "009_kg_source_resolution"`（`alembic/versions/009_kg_source_resolution.py:33`）。
- `upgrade()`：
  1. `op.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")`。
  2. `op.execute("CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);")`（IF NOT EXISTS 不可用，先 SELECT 判断是否存在；存在则跳过）。
  3. `op.execute("ALTER TEXT SEARCH CONFIGURATION chinese_zh ADD MAPPING FOR n,v,a,i,e,l WITH simple;")`。
  4. `op.execute("ALTER TABLE document_chunks ALTER COLUMN content_tsvector TYPE tsvector USING to_tsvector('chinese_zh', content);")`。
- `downgrade()`：
  1. `op.execute("ALTER TABLE document_chunks ALTER COLUMN content_tsvector TYPE tsvector USING to_tsvector('simple', content);")`。
  2. `op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese_zh;")`。
  3. 注释：扩展 `zhparser` 不主动 `DROP`（cascading 风险，留给运维按需）。

**文件：**
- `packages/server-python/alembic/versions/010_zhparser_chinese.py`（新建）

### Task 2.2 — 迁移验证

```bash
cd packages/server-python
.venv/bin/python -m alembic upgrade head
# 预期：迁移到 010_zhparser_chinese 成功

.venv/bin/python -m alembic current
# 预期：head = 010_zhparser_chinese

.venv/bin/python -m alembic downgrade -1
# 预期：回滚到 009_kg_source_resolution；content_tsvector 回到 simple 字典

.venv/bin/python -m alembic upgrade head
# 预期：重入幂等

# 验证 chinese_zh 配置在迁移后存在
docker exec deploy-postgres-1 psql -U metaedu -d metaedu -c "SELECT cfgname FROM pg_ts_config WHERE cfgname = 'chinese_zh';"
# 预期：cfgname = chinese_zh
```

**已知风险**：

- 大表（> 100k chunks）`ALTER TABLE` 锁等待可能 > 1 min。dev 库 < 50k chunks 不阻塞；生产环境按 `data-integrity.md` 灰度策略。
- 如果切片 1 镜像没合 main，迁移 010 跑 `CREATE EXTENSION` 会报 `UndefinedObjectError`。**强依赖切片 1**。

---

## 切片 3：3 个 tsvector 生产者切字典

### Task 3.1 — `chunk_repository.update_tsvector`

- `packages/server-python/app/contexts/document/infrastructure/chunk_repository.py:70`：
  ```python
  # 旧
  SET content_tsvector = to_tsvector('simple', content)
  # 新
  SET content_tsvector = to_tsvector('chinese_zh', content)
  ```
- 注意：迁移 010 已把列类型重建为 `to_tsvector('chinese_zh', content)`，本切片与切片 2 一致。

**文件：**
- `packages/server-python/app/contexts/document/infrastructure/chunk_repository.py`（修改，1 行替换）

### Task 3.2 — `tasks/index.index_tsvector` Celery 任务

- `packages/server-python/app/contexts/document/application/tasks/index.py:58`：同 Task 3.1 的字符串替换。

**文件：**
- `packages/server-python/app/contexts/document/application/tasks/index.py`（修改，1 行替换）

### Task 3.3 — `backfill_chunk_embedding` 重跑脚本

- `packages/server-python/app/contexts/document/application/backfill_chunk_embedding.py:104`：同 Task 3.1 的字符串替换。

**文件：**
- `packages/server-python/app/contexts/document/application/backfill_chunk_embedding.py`（修改，1 行替换）

### Task 3.4 — 单元 / 集成测试

- 现有 pytest（`tests/contexts/document/test_*`）应仍绿（因为 `chunk_repository.update_tsvector` / `index_tsvector` 调用者无变化，只是底层 SQL 切字典）。
- 旧测试用 `to_tsvector('simple', content)` 期望的 tokens 序列可能与新字典不一致——如有 fixture 用 `assert to_tsvector == ...`，**必须更新**为 `to_tsvector('chinese_zh', content)` 期望。

**验证：**

```bash
cd packages/server-python
.venv/bin/python -m pytest tests/contexts/document/ -q
# 预期：全绿

.venv/bin/python -m ruff check app/ tests/
# 预期：退出码 0
```

---

## 切片 4：`backfill_node_source._find_chunk_for_node` 改 `plainto_tsquery`

### Task 4.1 — SQL 替换

- `packages/server-python/app/contexts/knowledge/application/backfill_node_source.py:58-86`：
  ```python
  # 旧
  SELECT id FROM metaedu.document_chunks
  WHERE tenant_id = :tid AND file_id = :fid
  AND content ILIKE :pattern
  ORDER BY chunk_index LIMIT 1
  # 传参：{"tid": tenant_id, "fid": file_id, "pattern": f"%{node_title}%"}

  # 新
  SELECT id FROM metaedu.document_chunks
  WHERE tenant_id = :tid AND file_id = :fid
  AND to_tsvector('chinese_zh', content) @@ plainto_tsquery('chinese_zh', :title)
  ORDER BY chunk_index LIMIT 1
  # 传参：{"tid": tenant_id, "fid": file_id, "title": node_title}
  ```
- 参数化：`plainto_tsquery` 自动转义（无需 escape 函数），但**仍用 bind param**，防 SQL 注入。
- 兜底：`plainto_tsquery('chinese_zh', :title)` 对空字符串返回空 tsquery → `@@` 永远 false → 函数返回 `None` → 业务侧 `file_only`（与旧 ILIKE 行为一致；旧 ILIKE 对空 `node_title` 走 `if file_id is None or not node_title: return None` 早退）。
- 函数签名 `async def _find_chunk_for_node(session, tenant_id, file_id, node_title)` 不变。
- 内部 docstring 更新：把"Find the first chunk in the same file whose content contains node_title" 改为"Find the first chunk in the same file whose content's Chinese-tsvector matches the node title tsquery"。

**文件：**
- `packages/server-python/app/contexts/knowledge/application/backfill_node_source.py`（修改，10-15 行）

### Task 4.2 — 现有测试更新

- `packages/server-python/tests/contexts/knowledge/test_backfill_node_source.py` 现有用例：
  - 5 个 fixture：① 空 file_id → None；② ILIKE 命中 → 更新 source_chunk_id；③ 标题不在 chunk 中 → file_only；④ dry_run 不写库；⑤ idempotent re-run。
  - ②与 ③ 的期望：旧 ILIKE 行为 → 新 plainto_tsquery 行为。fixture 字符串不变（中文标题与 chunk content 仍字面命中），**应**继续通过。
  - 如有 fixture 用"标题在 chunk 中逐字不存在但 to_tsquery 命中"场景（spike 验证里的"中华人民共和国建国初期" 类），需新增。
  - **测试不需要重写**，可能需要新增 ≥ 3 用例（详切片 5 Task 5.2）。

**验证：**

```bash
cd packages/server-python
.venv/bin/python -m pytest tests/contexts/knowledge/test_backfill_node_source.py -v
# 预期：现有 5 个用例全绿；新增 ≥ 3 用例后 ≥ 8 全绿
```

---

## 切片 5：覆盖矩阵测试 + test 库扩展

### Task 5.1 — `test_db_setup.py` 加 zhparser 扩展

- `packages/server-python/app/shared/infrastructure/test_db_setup.py:142-144` 段加：
  ```python
  if os.environ.get("METAEDU_TEST_ENABLE_ZHPARSER", "false").lower() == "true":
      await conn.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")
  ```
- 默认 `false` 不强制（沙箱 / dev / CI 缺镜像时不影响 test 库启动）；CI 上配 `METAEDU_TEST_ENABLE_ZHPARSER=true` 验证 zhparser 测试真跑。

**文件：**
- `packages/server-python/app/shared/infrastructure/test_db_setup.py`（修改，2 行新增）

### Task 5.2 — `test_backfill_node_source.py` 新增 3 用例

| 用例名 | 场景 | 期望 |
|--------|------|------|
| `test_find_chunk_for_node_matches_literal_chinese_title` | 标题"中华人民共和国"，chunk 含"中华人民共和国" | `_find_chunk_for_node` 返回 chunk_id |
| `test_find_chunk_for_node_matches_multi_token_split` | 标题"中华人民共和国建国初期"，chunk "本节讨论中华人民共和国建国初期的工业政策" | `_find_chunk_for_node` 返回 chunk_id（to_tsquery 拆 token 共享） |
| `test_find_chunk_for_node_returns_none_on_unmatched_title` | 标题"智能制造"，chunk "本节介绍智能化制造和工业互联网" | `_find_chunk_for_node` 返回 None（SCWS 词表外新词不归一化；走 file_only 兜底） |
| `test_find_chunk_for_node_escapes_special_chars` | 标题含 SQL 关键字 / 单引号 / 特殊字符 | `_find_chunk_for_node` 不报 SQL 错误，行为可预期（命中或 file_only） |

**文件：**
- `packages/server-python/tests/contexts/knowledge/test_backfill_node_source.py`（新增 4 用例）

### Task 5.3 — `test_chunk_repository.py` 新增 3 用例

- 路径：如不存在则新建 `packages/server-python/tests/contexts/document/test_chunk_repository.py`。
- 用例：① "中华人民共和国" 切词后 tokens 序列与预期一致；② "智能制造与工业4.0" 切词；③ 英文/标点混合文本不抛错。

**文件：**
- `packages/server-python/tests/contexts/document/test_chunk_repository.py`（新建或修改）

### Task 5.4 — 全量 pytest + ruff 验证

```bash
cd packages/server-python
.venv/bin/python -m pytest -q
# 预期：全绿；基线 319 passed + 1 skipped + 本任务新增 ≥ 7 用例

.venv/bin/python -m ruff check app/ tests/
# 预期：退出码 0；8 E402 pre-existing 仍存在（TD-049 范围）
```

---

## 切片 6：真 PG 重跑 backfill + 覆盖率报告

### Task 6.1 — dev 库恢复

- 检查 `deploy-postgres-1` 状态：`docker ps -a | grep deploy-postgres-1`。
- 如果 exited：按切片 1 Task 1.5 重起。
- 验证 `pg_extension` 包含 `zhparser`：`docker exec deploy-postgres-1 psql -U metaedu -d metaedu -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'zhparser';"`。

### Task 6.2 — Alembic 升级

```bash
cd packages/server-python
.venv/bin/python -m alembic upgrade head
# 预期：head = 010_zhparser_chinese
```

### Task 6.3 — backfill 真跑

```bash
# 1. dry-run 看预期
cd packages/server-python
.venv/bin/python -m app.cli.backfill node-source-chunk --dry-run
# 预期：scanned = 252（TD-046 跑后未 file_only 的 252 个节点）

# 2. 真跑
.venv/bin/python -m app.cli.backfill node-source-chunk
# 预期：updated + skipped_file_only + failed 三项实际值写到日志
```

### Task 6.4 — 覆盖率报告

- 跑：`python scripts/ai/evidence_coverage_report.py`（如存在；如不存在写脚本新增，输出 JSON）。
- 把实际 `updated / scanned / skipped_file_only` 三值写到：
  - `docs/03-engineering-governance/technical-debt.md#td-047` 交付记录段。
  - `docs/03-engineering-governance/work-log.md`（TD-047 收口索引行）。
  - PR 描述的 "Verification" 段。
- 与 P1 基线对比：
  - 旧：`skipped_file_only = 252 / scanned = 252 = 100% file_only`（TD-046 跑后没动过这 252 个节点）。
  - 新：`updated / scanned` 即 `chunk_resolved` 比例。
  - **最低目标**：`chunk_resolved ≥ 85%`（`file_only ≤ 15%`）。
  - **理想目标**：`chunk_resolved ≥ 90%`（`file_only ≤ 10%`）。
  - 任一未达成：PR 描述里写明降级方案（详见 spec"能力边界"段：同义 / 翻译 / 抽象语义 zhparser 不解，需要 REQ-012 后续 embedding 召回）。

### Task 6.5 — 跨事实源状态同步

- `docs/03-engineering-governance/technical-debt.md#td-047`：状态 `⚫ 待办` → `🟢 完成`；交付记录段写本任务 6 切片的 PR / commit 摘要。
- `docs/03-engineering-governance/current-work.md`：当前进行中行移除；最近完成区追加一行。
- `docs/01-product-planning/02-milestones/02-growth-phase.md:78` P2-SEARCH 状态：`⚫ Candidate` → `🟡 Shaping`（与 REQ-012 启动同步）。
- `docs/01-product-planning/05-requirements/REQ-012-...md`（如存在）：TD-047 段从"前置依赖"改为"已完成"。

**验证：**
- `git diff --name-status` 只包含 6 切片预期文件 + 上述文档。
- `scripts/check-engineering-docs` 退出码 0。
- `gh pr checks <PR#>` no checks reported（PR 未配 CI；本地门禁已过即可）。

---

## 验证矩阵

每个切片运行（具体子集在切片内 Task 中说明）：

| 命令 | 切片 1 | 切片 2 | 切片 3 | 切片 4 | 切片 5 | 切片 6 |
|------|--------|--------|--------|--------|--------|--------|
| `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cd packages/server-python && .venv/bin/python -m pytest -q` | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cd packages/server-python && .venv/bin/python -m alembic upgrade head` | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cd packages/server-python && .venv/bin/python -m alembic downgrade -1` | — | ✅ | — | — | — | — |
| `cd packages/server-python && .venv/bin/python -m app.cli.backfill node-source-chunk --dry-run` | — | — | — | — | ✅ | ✅ |
| `cd packages/server-python && .venv/bin/python -m app.cli.backfill node-source-chunk` | — | — | — | — | — | ✅ |
| `cd deploy && docker build -f Dockerfile.postgres -t metaedu/postgres-zhparser:pg16 ..` | ✅ | — | — | — | — | — |
| `docker exec deploy-postgres-1 psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS zhparser;"` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `python scripts/ai/evidence_coverage_report.py` | — | — | — | — | — | ✅ |
| `scripts/check-engineering-docs` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `pnpm --filter @metaedu/web typecheck/build/lint`（基线） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**已知未运行的验证**：

- `pytest tests/conftest.py` 8 E402 pre-existing（TD-049 范围；本任务不解决）。
- `gh pr checks <PR#>`（PR 未配 CI；按 TD-046 / TD-020 / TD-012 收口范式，明示"no checks reported / PR 未配 CI"）。
- 生产环境大表 `ALTER TABLE` 锁等待（dev 库 < 50k chunks 不阻塞；生产需独立灰度）。

---

## 提交 / PR 计划

### 6 原子提交（按顺序 squash 到 1 PR）

```
chore(infra): TD-047/1 add zhparser to PG image
  - deploy/Dockerfile.postgres (新建 multi-stage)
  - deploy/docker-compose.dev.yml (postgres.image -> build + image)
  - deploy/docker-compose.yml (postgres 同上)
  - deploy/.gitignore (新增 cache/)

chore(rag): TD-047/2 alembic 010 zhparser chinese_zh config
  - packages/server-python/alembic/versions/010_zhparser_chinese.py

chore(rag): TD-047/3 tsvector producers switch to chinese_zh
  - packages/server-python/app/contexts/document/infrastructure/chunk_repository.py
  - packages/server-python/app/contexts/document/application/tasks/index.py
  - packages/server-python/app/contexts/document/application/backfill_chunk_embedding.py

chore(rag): TD-047/4 backfill_node_source use plainto_tsquery
  - packages/server-python/app/contexts/knowledge/application/backfill_node_source.py

chore(rag): TD-047/5 add Chinese tsvector/tsquery coverage tests
  - packages/server-python/app/shared/infrastructure/test_db_setup.py
  - packages/server-python/tests/contexts/knowledge/test_backfill_node_source.py
  - packages/server-python/tests/contexts/document/test_chunk_repository.py (新建)

chore(rag): TD-047/6 rerun backfill on real PG, update coverage baseline
  - (无业务代码变更；本提交是 backfill 真跑 + 文档同步)
  - docs/03-engineering-governance/technical-debt.md
  - docs/03-engineering-governance/current-work.md
  - docs/03-engineering-governance/work-log.md
  - docs/01-product-planning/02-milestones/02-growth-phase.md
```

### PR 描述模板

```markdown
## TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector）

### 任务事实源
- `docs/03-engineering-governance/technical-debt.md#td-047`
- `docs/02-delivery-plans/01-specs/2026-06-11-td-047-zhparser-chinese-tsvector.md`
- `docs/02-delivery-plans/02-plans/2026-06-11-td-047-zhparser-chinese-tsvector-plan.md`

### 6 切片收口

- [x] 切片 1: PG 镜像加 zhparser
- [x] 切片 2: Alembic 010 迁移
- [x] 切片 3: 3 个 tsvector 生产者切字典
- [x] 切片 4: backfill 改 plainto_tsquery
- [x] 切片 5: 覆盖矩阵测试 + test 库扩展
- [x] 切片 6: 真 PG 重跑 + 覆盖率报告

### 行为变化声明

- `content_tsvector` 列字典从 'simple' 切到 'chinese_zh'；已存数据会按新字典重切（迁移 010 `ALTER TABLE USING`）。
- `backfill_knowledge_node_source._find_chunk_for_node` 从字节级 `ILIKE` 切到 `plainto_tsquery('chinese_zh', :title)`；逐字命中行为不变，拆字 / 多 token 共享场景从 file_only 升级为 chunk_resolved。
- 同义 / 翻译 / 抽象语义匹配**未解决**（zhparser 词表不连接同义词）；见 spec "能力边界" 段；属 REQ-012 后续 embedding 召回范围。

### 验证摘要

- `ruff check app/ tests/` → 退出码 0（8 E402 pre-existing 在 `tests/conftest.py`，TD-049 范围）
- `pytest -q` → 319 passed + 1 skipped + 新增 ≥ 7 用例（基线 + 本任务）
- `alembic upgrade head` → 退出码 0，head = 010_zhparser_chinese
- `alembic downgrade -1` → 退出码 0，回滚到 009_kg_source_resolution
- `python -m app.cli.backfill node-source-chunk --dry-run` → 退出码 0
- `python -m app.cli.backfill node-source-chunk` → 退出码 0
- `python scripts/ai/evidence_coverage_report.py` → 实际值见下
- `docker build -f deploy/Dockerfile.postgres -t metaedu/postgres-zhparser:pg16 ..` → 退出码 0，冷 build < 10 min
- `scripts/check-engineering-docs` → 退出码 0
- `pnpm --filter @metaedu/web typecheck/build/lint` → 退出码 0（基线）

### 覆盖率提升

- P1 基线（TD-046 跑后）：`skipped_file_only = 252/1006 = 25.05% file_only`
- 本任务跑后：`<实际值>` → `<达成目标 [最低 ≥ 85% | 理想 ≥ 90%] [是 / 否]>`
- 未达成时降级方案：见 spec "能力边界" 段；REQ-012 后续 embedding 召回

### 风险 / 后续接力

- 外部源依赖：xunsearch.com（SCWS 1.2.3）+ github.com/amutu/zhparser；Dockerfile 锁 commit hash。
- TD-049（E402 pre-existing）独立 PR；TD-050（EvidenceItem.source_chunk_id 字段）独立 PR；REQ-012 把本任务收口结果作为前置依赖。
- 生产灰度：切片 1 镜像推到 registry 后运维配合灰度切流量；大表 ALTER TABLE 锁等待需按 data-integrity.md 策略评估。
```

---

## 已知阻塞 / 风险

- **切片 1 冷 build 失败**：xunsearch.com 不可达时，缓存 tarball 到 `deploy/cache/` 兜底（spike 已验证 tarball 真实存在 + 大小合理）。
- **zhparser 上游 commit 漂移**：用 `--branch <sha>` 锁版本；首次成功 build 后记录 SHA 到 Dockerfile 注释。
- **dev 库 `deploy-postgres-1` exited**：切片 6 Task 6.1 显式重起；pgdata volume 持久化数据未损。
- **生产大表 ALTER 锁等待**：spec 已记录为已知风险；本任务不动生产。
- **同义 / 翻译 / 抽象语义**：本任务不解；spec 已明确边界。
- **TD-049 / TD-050 / REQ-012**：独立 PR / spec，不混入本 PR。

## 范围外

- 切片 1-6 之外的所有改动（如新增 zhparser 词典、修改 RecallChannel Protocol、改前端、改其他 Celery 任务）一律不做。
- 不写 zhparser 二次开发（如自定义词典、自定义同义词表）。
- 不改 PG 镜像的非 zhparser 部分（如 pgvector 版本、pg_hba.conf、postgresql.conf）。
- 不写 Dockerfile.postgres 的 ARM64 / x86_64 双架构（spike 已验 arm64；x86_64 走 multi-stage 路径应等价，CI 首次 build 验）。
