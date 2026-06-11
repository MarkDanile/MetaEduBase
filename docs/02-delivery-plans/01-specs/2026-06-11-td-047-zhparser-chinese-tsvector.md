# TD-047 中文分词回填 ILIKE 限制（路线 A zhparser + tsvector） — Spec

> Spec 入口：TD-047（技术债事实源 `docs/03-engineering-governance/technical-debt.md#td-047`）。本文件是验收口径与边界的事实源；实施拆分见 [`2026-06-11-td-047-zhparser-chinese-tsvector-plan.md`](../02-plans/2026-06-11-td-047-zhparser-chinese-tsvector-plan.md)。
> 规划归属：[`P2-SEARCH`](../../01-product-planning/02-milestones/02-growth-phase.md) — PostgreSQL `tsvector` + 中文分词搜索增强。
> 前置依赖：REQ-010 / TD-046（数据回填批次）已完成。
> 后续接力：REQ-012（Shaping）把 TD-047 收口路径写进前置依赖，TD-050（spec / 代码错位校正）独立 PR。

## 目标

解决 P1 RAG `node_source_chunk` 覆盖率 25.05% 缺口（252/1006 `file_only`）的根因：中文回填用字节级 `ILIKE '%{title}%'` 子串匹配，无法命中 chunk 中"同字面量缺失但同 token 序列存在"的中文节点。落地 PostgreSQL `tsvector` + zhparser 中文分词全文检索，与 P2-SEARCH 规划保持一致。

具体目标：

- `backfill_knowledge_node_source._find_chunk_for_node` 不再依赖字节级 `ILIKE` 子串匹配。
- `node_source_chunk` 覆盖率有明确提升目标与可量化结果（dev 库真 PG 重跑 backfill 统计）。
- P2-SEARCH 检索基础设施（中文分词 + `chinese_zh` 文本搜索配置）就位，REQ-012 启动时可直接复用。
- 镜像层基础设施同步（dev / CI / 生产 PG 镜像都带 zhparser），不留基础设施债。

## 决策记录（2026-06-11 路线澄清）

> 用户在 spike 阶段确认 2 项决策；后续 spec / plan 不得偏离。

- **Q1 — 路线选择**：4 候选（zhparser / SCWS / jieba 预分词 / pg_trgm）选 zhparser + tsvector（路线 A）。理由：① P2-SEARCH 规划已明确 `tsvector + zhparser`；② PG 内置中文检索与 `content_tsvector` 列 + 现有 3 个生产者架构天然兼容；③ 复用 `CREATE EXTENSION` + 文本搜索配置生态。
- **Q2 — 时机**：现在开工 + 独立 PR。理由：① 25.05% 缺口虽未达任务卡原文 70% 立即解决门槛，但 P2-SEARCH 启动时再补会让 REQ-012 spec 复杂化；② 提前打通基础设施降低 REQ-012 启动成本；③ 当前 dev PG 已跑 + 已有 1006 个节点的真实数据可用于验证。

## 能力边界（spike 验证结论）

> spike 在 spike 容器 `td047-zhparser-test2` 跑通 4 场景中文 tsvector / tsquery 验证，结论如下。

| 场景 | 输入 | ILIKE 行为 | to_tsquery('chinese_zh', ...) 行为 | TD-047 收益 |
|------|------|------------|----------------------------------|------------|
| ① 字面命中 | 标题"中华人民共和国"，chunk 含"中华人民共和国" | ✅ 命中 | ✅ 命中（零回归） | 平 |
| ② 多 token 拆字 | 标题"中华人民共和国建国初期"，chunk 含同 token 序列 | ✅ 命中（字面） | ✅ 命中（拆 token 共享） | 平 |
| ③ 顺序错乱 / 新词拆字 | 标题"智能制造"，chunk 含"智能化制造" | ❌ 不命中 | ❌ 不命中（SCWS 词表外新词不归一化，"智能化" 与 "智能" 在词表里不同） | **不**解决 |
| ④ 同义 / 翻译 / 抽象 | 标题"抗日战争"，chunk 含"抗战" | ❌ 不命中 | ❌ 不命中（SCWS 词表不连接同义词） | **不**解决 |

**关键结论**：

- zhparser 路线对 TD-047 覆盖率提升**有上限**——仅解"字面命中 + 拆字 + 多 token 共享"3 类，**不**解"同义 / 翻译 / 抽象"语义匹配。
- 任务卡原文（`technical-debt.md:2292`）写"中文实体、翻译实体、抽象能力点和同义表达"——zhparser 只能解其中"中文实体"部分；"翻译实体"和"抽象能力点"是 P2-SEARCH 后续引入 embedding 召回（REQ-012）的范围。
- 预期覆盖率提升需 dev 库真 PG 重跑 backfill 实测。**最低目标**：`skipped_file_only` 从 252/1006（25.05%）降到 ≤ 30%（即 ≤ 76 个）；**理想目标**：≤ 15%（即 ≤ 38 个）；**任一目标未达成**，需在 PR 描述里写明实测数字与降级方案。

## 数据模型 / 迁移

### 010 迁移：`alembic/versions/010_zhparser_chinese.py`

```sql
-- 1. 启用 zhparser 扩展
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 2. 配置中文文本搜索
CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);
-- 借鉴 SCWS 默认词典映射：n(名词) / v(动词) / a(形容词) / i(成语) / e(叹词) / l(习语) 走 simple
-- 其它 token (x 未知 / p 标点 等) 不入索引
ALTER TEXT SEARCH CONFIGURATION chinese_zh ADD MAPPING FOR n,v,a,i,e,l WITH simple;

-- 3. 重建 document_chunks.content_tsvector 列（从 'simple' 切到 'chinese_zh'）
--    这一步会触发全表重算，dev 库 ~10k chunks 应 < 5s；生产需评估锁等待
ALTER TABLE document_chunks
    ALTER COLUMN content_tsvector TYPE tsvector
    USING to_tsvector('chinese_zh', content);
```

**关键风险**（与 TD-038 同类）：

- `CREATE EXTENSION zhparser` 在没有 zhparser 共享库的 PG 实例上会报 `UndefinedObjectError`，**阻塞** `alembic upgrade head`。
- 缓解：切片 1（PG 镜像加 zhparser）必须**先于**切片 2（迁移）合并；CI 镜像同步；本地 dev 库先 `docker compose up --build postgres` 重建容器。
- 迁移中 `ALTER TABLE ... USING to_tsvector('chinese_zh', content)` 对**大表**会全表扫描 + 写锁；dev 库小（< 50k chunks）可接受，生产环境大表应分批或用 `CONCURRENTLY` 模式（PG ≥ 12 限制场景下需手动切片）。

**回滚**：

```sql
-- 1. content_tsvector 回 'simple'
ALTER TABLE document_chunks
    ALTER COLUMN content_tsvector TYPE tsvector
    USING to_tsvector('simple', content);
-- 2. 删 chinese_zh 文本搜索配置
DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese_zh;
-- 3. 删 zhparser 扩展（注意：cascading 到所有依赖 .so 的 PG 进程会断）
-- DROP EXTENSION IF EXISTS zhparser;  -- 不主动删；扩展不会自动清
```

回滚触发条件：① 真实 backfill 重跑后覆盖率**不升反降**；② `ALTER TABLE` 锁等待超时；③ zhparser 编译失败且多日无法修复。

## 范围

### 包含 — Backend

- **新 Alembic 迁移 010**：`packages/server-python/alembic/versions/010_zhparser_chinese.py`（含 upgrade + downgrade）。
- **3 个 tsvector 生产者切字典**：
  - `packages/server-python/app/contexts/document/infrastructure/chunk_repository.py:70` `to_tsvector('simple', content)` → `to_tsvector('chinese_zh', content)`。
  - `packages/server-python/app/contexts/document/application/tasks/index.py:58` 同上。
  - `packages/server-python/app/contexts/document/application/backfill_chunk_embedding.py:104` 同上。
- **backfill 替换 ILIKE**：
  - `packages/server-python/app/contexts/knowledge/application/backfill_node_source.py:58-86` `_find_chunk_for_node` 用 `plainto_tsquery('chinese_zh', :title)` 替代 `ILIKE '%{title}%'`。
  - SQL 改为：`SELECT id FROM metaedu.document_chunks WHERE tenant_id = :tid AND file_id = :fid AND to_tsvector('chinese_zh', content) @@ plainto_tsquery('chinese_zh', :title) ORDER BY chunk_index LIMIT 1`。
  - 参数化：`plainto_tsquery` 自动转义（无需手动 escape），防 SQL 注入。
  - 兜底：`plainto_tsquery` 对 `node_title` 含 `pg_trgm` 不识别的特殊字符（如全角标点）会返回空 token 序列 → 函数返回空 tsquery → `@@` 永远假 → 旧 ILIKE 路径已被替换，需保留 `file_only` 兜底（不命中时返回 `None` → 业务侧 `node_source_resolution = 'file_only'`，与现状一致）。
- **测试库扩展**：
  - `packages/server-python/app/shared/infrastructure/test_db_setup.py:142-144` 在 `CREATE EXTENSION` 段加 `CREATE EXTENSION IF NOT EXISTS zhparser`（仅当 `zhparser` 可用时；不可用时 graceful skip，CI 与 dev 都跑得到）。
- **覆盖矩阵测试**：
  - `packages/server-python/tests/contexts/knowledge/test_backfill_node_source.py` 新增 ≥ 3 用例：① 标题与原文逐字匹配（IL 旧路径已被替换，验证 to_tsquery 命中）② 标题多 token / 拆字（"中华人民共和国建国初期" 类）③ 节点标题被 SCWS 词典外新词分词 / chunk 同拆法命中；④ 节点标题在 chunk 中不命中 → 走 `file_only` 兜底。
  - `packages/server-python/tests/contexts/document/test_chunk_repository.py`（如不存在则新建）增加中文 fixture 验证 `update_tsvector` 走 `chinese_zh` 后切词序列。

### 包含 — Dev / CI / 生产基础设施

- **新增 PG 镜像构建**：`deploy/Dockerfile.postgres`（multi-stage）。
  - Stage 1 `builder`：基于 `pgvector/pgvector:pg16`，装 `postgresql-server-dev-16` + `gcc` + `make` + `bzip2` + `git`，从 xunsearch.com 拉 SCWS 1.2.3 编译装到 `/usr/local`，git clone `amutu/zhparser` 编译 `zhparser.so` 装到 `/usr/lib/postgresql/16/lib/`，控制文件 + dict.utf8.xdb + rules.utf8.ini 装到 `/usr/share/postgresql/16/extension/` 和 `/usr/share/postgresql/16/tsearch_data/`。
  - Stage 2 `runtime`：基于 `pgvector/pgvector:pg16`，从 builder 复制 `/usr/local/lib/libscws*` + `/usr/local/include/scws/` + `/usr/lib/postgresql/16/lib/zhparser.so` + `/usr/share/postgresql/16/extension/zhparser*` + `/usr/share/postgresql/16/tsearch_data/dict.utf8.xdb` + `/usr/share/postgresql/16/tsearch_data/rules.utf8.ini`。
  - 镜像 tag：`metaedu/postgres-zhparser:pg16`（推到 registry 后生产可拉）。
- **docker-compose 改 build 路径**：
  - `deploy/docker-compose.dev.yml` 的 `postgres.image: pgvector/pgvector:pg16` 改为 `build: { context: .., dockerfile: deploy/Dockerfile.postgres }` + `image: metaedu/postgres-zhparser:pg16`（让 docker compose 知道本地构建的镜像名）。
  - `deploy/docker-compose.yml`（生产）保持 `image: metaedu/postgres-zhparser:pg16`（推到 registry 后从远端拉），可选在迁移期保留 `image: pgvector/pgvector:pg16` + `build: { ... }` 双轨。
- **CI 镜像同步**：`scripts/ci/...` 如有 PG 镜像定义，同步改为 `metaedu/postgres-zhparser:pg16`。
- **国内镜像加速**：Dockerfile 拉 SCWS / zhparser 走 xunsearch.com + github.com；不切换 apt / git 源（沙箱验证：apt 清华 + 阿里云 PGDG 镜像已配置 `~/.docker/daemon.json`，但 Dockerfile 内 wget / git clone 不走 Docker daemon 镜像加速——这是已知的外部源依赖，由 Dockerfile 内的 `apt-get update` 走 daemon 镜像 + SCWS 拉源一次性 5-10 min cold build 解决）。

### 包含 — 真 PG 重跑 backfill + 覆盖率统计

- dev 库恢复（dev 库 `deploy-postgres-1` 已 exited 6h，pgdata volume 持久化未损；`./dev.sh infra` 重起或 `docker compose -f deploy/docker-compose.dev.yml up -d --build postgres` 重建）。
- `cd packages/server-python && .venv/bin/python -m alembic upgrade head` 跑迁移。
- `cd packages/server-python && .venv/bin/python -m app.cli.backfill node-source-chunk --dry-run` 看预期统计。
- `cd packages/server-python && .venv/bin/python -m app.cli.backfill node-source-chunk` 真跑。
- 写覆盖率报告（写到 work-log 或 PR 描述）：`scanned / updated / skipped_file_only / failed` 实际值与 P1 基线（754/1006 = 74.95% `chunk_resolved`）对比。
- 跑 `python scripts/ai/evidence_coverage_report.py`（如存在）刷新 P1 RAG 基线。

### 不包含

- **不**重写 `backfill_knowledge_node_source` 的 `_fetch_pending_nodes` / `list_distinct_tenants` / `BackfillStats` 行为。
- **不**改 `AiChatView` / `ai_router.py` / `mcp_server` 等下游消费方（节点级 evidence 已通过 `EvidenceItem` 消费，TD-048 已收口）。
- **不**引入 `pg_trgm` / `jieba` 预分词 / `SCWS` 独立调用（zhparser 路线已涵盖 SCWS 静态词典）。
- **不**写 `chinese_zh` 同义词词典（zhparser 上游已带 `dict.utf8.xdb`；本任务不二次开发词表）。
- **不**改 `tests/conftest.py` E402 8 个 pre-existing（TD-049 范围）。
- **不**改前端任何代码（web 端无中文检索 UI 入口；改动只到后端 SQL 与覆盖矩阵）。
- **不**改 `technical-debt.md#td-047` 完成标准的"覆盖率有明确提升目标"中"目标"字面数字（实测后由 PR 描述填写实际值，spec 给出**最低目标 / 理想目标**两个范围）。

## 验收标准（AC）

### AC-1：PG 镜像可重建（dev / CI / 生产三处）

- `cd deploy && docker build -f Dockerfile.postgres -t metaedu/postgres-zhparser:pg16 ..` 退出码 0，**冷 build 总耗时 < 10 min**（spike 验证：SCWS 编译 < 1 min + zhparser 编译 < 1 min + apt 拉包 < 5 min）。
- `docker run --rm -d -e POSTGRES_USER=metaedu -e POSTGRES_PASSWORD=dev_only_123 -e POSTGRES_DB=zhparser_probe --name zhparser-probe metaedu/postgres-zhparser:pg16` 启动后 `docker exec zhparser-probe psql -U metaedu -d zhparser_probe -c "CREATE EXTENSION zhparser; SELECT extversion FROM pg_extension WHERE extname='zhparser';"` 返回 `2.4`。
- 镜像体积：runtime 镜像与 `pgvector/pgvector:pg16`（639MB）相比增量 < 50MB（spike 估算 `/usr/local/lib/libscws*` ~5MB + `/usr/lib/postgresql/16/lib/zhparser.so` ~200KB + 词典文件 ~10MB）。

### AC-2：迁移 010 可执行 + content_tsvector 列重建

- 在 dev 库真跑 `alembic upgrade head` 退出码 0，不报 `UndefinedObjectError` / `extension "zhparser" is not available`。
- `alembic downgrade -1` 退出码 0，回滚后 `content_tsvector` 列回到 `simple` 字典。
- `alembic upgrade head` 第二次跑（重入场景）退出码 0，幂等。

### AC-3：3 个 tsvector 生产者切字典 + 中文 fixture 端到端

- `chunk_repository.update_tsvector` / `tasks/index.index_tsvector` / `backfill_chunk_embedding` 三个函数在调用后 `SELECT content_tsvector FROM document_chunks WHERE id = :id` 返回的 tokens 序列与 `to_tsvector('chinese_zh', content)` 一致。
- 新增 pytest 中文 fixture 覆盖：① "中华人民共和国" 切 5 token；② "智能制造与工业4.0" 切 4 token；③ 英文/标点/混合文本不抛错。

### AC-4：backfill 替换 ILIKE + 中文标题命中 + file_only 兜底

- `backfill_node_source._find_chunk_for_node` 用 `plainto_tsquery('chinese_zh', :title)` 替代 `ILIKE '%{title}%'`。
- pytest 覆盖：① 中文标题在 chunk 中逐字命中 → 走 `chunk_resolved`；② 中文标题在 chunk 中拆字命中（如 "中华人民共和国建国初期" 在 chunk 中含同样 token 序列）→ 走 `chunk_resolved`；③ 中文标题在 chunk 中完全无匹配（chinese_zh 词表外新词如 "智能制造" vs "智能化制造"）→ 走 `file_only`；④ 节点 `source_file_id IS NULL` → 走 `file_only`（旧行为保留）。
- SQL 注入测试：`node_title` 包含 SQL 关键字 / 单引号 / 特殊字符 → 走 `plainto_tsquery` 参数化转义，不报 SQL 错误。
- 行为变化声明（按 `quality-gates.md#行为变化声明检查`）：
  - 旧路径"节点标题与 chunk 文本逐字匹配"行为**不变**（to_tsquery 在"逐字"场景下与 ILIKE 等价）。
  - 旧路径"节点标题与 chunk 文本部分匹配"行为**可能扩展**（拆字 / 多 token 共享场景从 file_only 升级为 chunk_resolved）。
  - 旧路径"节点标题与 chunk 文本同义 / 翻译 / 抽象"行为**不变**（zhparser 不解，详见"能力边界"段）。

### AC-5：test 库扩展 + 覆盖矩阵测试

- `test_db_setup.py:142-144` 段加 `CREATE EXTENSION IF NOT EXISTS zhparser`（graceful skip：zhparser 不可用时不阻塞 test 库初始化，但**在 zhparser 可用时必须装好**；通过环境变量 `METAEDU_TEST_ENABLE_ZHPARSER=true` 控制是否必须，缺省 `false` 不强制）。
- `tests/contexts/knowledge/test_backfill_node_source.py` 新增 ≥ 3 用例（详 AC-4）。
- `tests/contexts/document/test_chunk_repository.py` 或同等文件新增 ≥ 3 用例（详 AC-3）。
- `pytest -q` 全量通过；`pytest tests/contexts/knowledge/ tests/contexts/document/ -q` 全绿。

### AC-6：真 PG backfill 重跑 + 覆盖率提升

- dev 库（pgdata volume 恢复后）真跑 `python -m app.cli.backfill node-source-chunk`，输出 `updated / skipped_file_only / failed` 三项实际值。
- 实际 `chunk_resolved` 比例（updated / scanned）**最低目标 ≥ 85%**（即 `skipped_file_only ≤ 15%`），**理想目标 ≥ 90%**（即 `skipped_file_only ≤ 10%`）。
- 实际值与 P1 基线（TD-046 跑后 754/1006 = 74.95% `chunk_resolved`）对比，写到 PR 描述。
- 跑 `python scripts/ai/evidence_coverage_report.py`（如存在）刷新 P1 RAG 基线并写到 `docs/03-engineering-governance/technical-debt.md#td-047` 交付记录。

## 范围外

- **不**改 `index_tsvector` Celery 任务的并发模型 / 调度（切片 3 只换字典，不改调度）。
- **不**改 `chunk_document` / `embed_chunks` Celery 任务的业务逻辑。
- **不**改 RAG 召回链路（`RecallChannel` Protocol / PgVectorRecallChannel / PgKeywordRecallChannel / PgMetadataRecallChannel）—— 切片 6 backfill 是数据债收口，不是检索链路增强（REQ-012 范围）。
- **不**做中文分词词表二次开发（zhparser 上游 `dict.utf8.xdb` 已够 P1 用，二次开发是 P2-SEARCH 长期任务）。
- **不**写 Dockerfile.postgres 的 ARM64 / x86_64 双架构（spike 验证 arm64 OK；x86_64 走标准 multi-stage 路径应等价，CI 上首次 build 验）。
- **不**写 zhparser 自动升级策略（用 zhparser 上游 master 固定 commit hash 锁版本）。

## 范围外但需知会

- **TD-049**：`tests/conftest.py` 8 E402 pre-existing；本任务在 pytest 验证时不解决。
- **TD-050**：`EvidenceItem` 缺 `source_chunk_id` 字段的 spec / 代码错位；与本任务独立，本 PR 不修复。
- **REQ-012**：本任务完成后，REQ-012 启动时把"TD-047 已收口"作为前置依赖，不在 REQ-012 spec 里再复述本任务细节。
- **P2-SEARCH milestone**：本任务收口后更新 `docs/01-product-planning/02-milestones/02-growth-phase.md:78`（P2-SEARCH Candidate → Shaping 或 Ready，取决于 REQ-012 启动节奏）。
- **真生产 PG 升级窗口**：切片 1（Dockerfile.postgres 落地）后需通知运维：① 重建 PG 镜像推到 registry；② 灰度切流量；③ 跑 `alembic upgrade head`（可能锁等待——按 doc 提到的 `CONCURRENTLY` 模式分批）；④ 真生产数据量大时 backfill 单次跑可能 > 10 min，按 TD-046 batch 模式分批（详情 plan）。

## 实施切片（6 切片，1 个独立 PR，6 个原子提交）

> 详细实施步骤见 `2026-06-11-td-047-zhparser-chinese-tsvector-plan.md`；本节只列切片与验收。

| # | 切片 | 主要文件 | 原子验收 | 阻断依赖 |
|---|------|----------|----------|----------|
| 1 | **PG 镜像加 zhparser** | `deploy/Dockerfile.postgres`（新建）+ `deploy/docker-compose.dev.yml`（image → build）+ `deploy/docker-compose.yml`（image） | AC-1 全部 | 无（基础） |
| 2 | **Alembic 010 迁移** | `packages/server-python/alembic/versions/010_zhparser_chinese.py`（新建） | AC-2 全部 | 切片 1（PG 镜像有 zhparser） |
| 3 | **3 个 tsvector 生产者切字典** | `chunk_repository.py:70` + `tasks/index.py:58` + `backfill_chunk_embedding.py:104` | AC-3 pytest 全绿 | 切片 2（迁移已升 head，chinese_zh 配置存在） |
| 4 | **backfill 改 to_tsquery** | `backfill_node_source.py:58-86` | AC-4 pytest 全绿 | 切片 3（chinese_zh 切词链路已通） |
| 5 | **覆盖矩阵测试 + test 库扩展** | `test_db_setup.py:142-144` + `test_backfill_node_source.py` + `test_chunk_repository.py` | AC-5 全部 | 切片 4（被测函数已切） |
| 6 | **真 PG 重跑 + 覆盖率报告** | dev 库 `deploy-postgres-1` 重起 + `alembic upgrade head` + backfill 真跑 + `evidence_coverage_report.py` | AC-6 全部 | 切片 5（测试全绿，行为稳定） |

## 验证矩阵

> 详 `2026-06-11-td-047-zhparser-chinese-tsvector-plan.md#验证矩阵`。

每个切片运行：

- `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0（**注**：8 个 E402 pre-existing 在 `tests/conftest.py` 仍存在，属 TD-049 范围）。
- `cd packages/server-python && .venv/bin/python -m pytest -q` 全绿（基线 319 passed + 1 skipped + 本任务新增 ≥ 9 用例）。
- `cd packages/server-python && .venv/bin/python -m alembic upgrade head` 退出码 0。
- `cd packages/server-python && .venv/bin/python -m alembic downgrade -1` 退出码 0（仅切片 2 / 6 验证）。
- `python -m app.cli.backfill node-source-chunk --dry-run` 退出码 0（仅切片 4 / 5 / 6 验证）。
- `python -m app.cli.backfill node-source-chunk` 退出码 0（仅切片 6 验证）。
- `scripts/check-engineering-docs` 退出码 0。
- `pnpm --filter @metaedu/web typecheck/build/lint` 退出码 0（本任务不动前端，作为基线）。

## 已知风险 / 外部依赖

- **外部源依赖**：
  - `xunsearch.com`（SCWS 1.2.3 源码 tarball）—— 第三方网站，可靠性中等；建议 Dockerfile 缓存 wget tarball 到 builder 阶段。
  - `github.com/amutu/zhparser`（zhparser 源码）—— 用 `--depth 1` 拉 master；建议 Dockerfile 用固定 commit hash 锁版本。
  - PGDG 源（postgresql-server-dev-16）—— Dockerfile 内 apt 走 Docker daemon 镜像加速（沙箱已配 1ms.run / unsee.tech / daocloud），但 Dockerfile 内 wget / git clone 不走 daemon 加速。
- **冷 build 时间**：dev 镜像首次 build 5-10 min；CI 上靠 Docker build cache 命中（multi-stage 缓存 builder 层），后续 build 增量 < 1 min。
- **运行时镜像体积**：runtime 镜像 < 50MB 增量（SCWS .so ~5MB + zhparser.so ~200KB + 词典 ~10MB + 头文件 ~1MB）。
- **生产灰度**：切片 1 落地后需运维配合灰度切流量；大表 `ALTER TABLE` 锁等待评估。
- **同义词 / 翻译 / 抽象语义匹配**：本任务**不解**；P2-SEARCH 后续引入 embedding 召回（REQ-012）。

## 范围外但记录

- **TD-047 任务卡原文覆盖率门槛 70%**：用户决策 Q2 已越过（25.05% 也开工）；本任务完成时在 `technical-debt.md#td-047` 交付记录里写明实际覆盖率提升与未到门槛但仍开工的决策。
- **zhparser 上游维护活跃度**：amutu/zhparser 上游 2022 后基本停更；本任务锁版本后短期不追新。
- **arm64 vs x86_64**：spike 验证 arm64；x86_64 等价（PG 多架构 binary 兼容），CI 首次 build 验。
- **macOS dev 沙箱限制**：沙箱对 GitHub 直连不稳（spike 验证 git clone 失败），生产 CI 不会受影响（CI 网络策略不同）；spec 写"生产 CI 已知 OK"，沙箱验证走"host 端 `git clone` + `docker cp` 复制"路径仅用于 spike，不写进 Dockerfile。
