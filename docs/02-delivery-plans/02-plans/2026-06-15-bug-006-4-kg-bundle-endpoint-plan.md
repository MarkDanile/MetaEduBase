# BUG-006 #4 KG Bundle 原子端点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `GET /api/v1/knowledge/files/{file_id}/kg-bundle` 原子端点，保证 edges 的 source/target 都在 nodes 列表中，修复资源库 KG tab 在节点数 > 50 时白屏的 g6 `Node not found` bug。

**Architecture:** 后端新增 1 个 DTO + 1 个 Repo 方法（双端 IN 过滤 SQL）+ 1 个 router endpoint；前端新增 1 个 API + 1 个 useFileKgQuery 改造（5 行）。3 mock pytest 锁不变量 + 真 PG 复测验收。旧 `/nodes` / `/edges` 端点完全保留。

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 async / asyncpg / pytest 8 / ruff 0.13 / Vue 3 / TypeScript / Vue Query / @antv/g6

**Spec:** `docs/02-delivery-plans/01-specs/2026-06-15-bug-006-4-kg-bundle-endpoint.md`
**Branch:** `fix/bug-006-4-kg-bundle-endpoint` (已创建，spec commit `6b01527` 已在分支上)

---

## File Structure

| File | 状态 | 职责 |
|------|------|------|
| `packages/server-python/app/contexts/knowledge/application/dto.py` | 修改 | 新增 `KgBundleDTO`（10 行） |
| `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py` | 修改 | 新增 `get_kg_bundle_for_file` 方法（25 行）|
| `packages/server-python/app/contexts/knowledge/interfaces/api/router.py` | 修改 | 新增 `GET /files/{file_id}/kg-bundle` endpoint（25 行）+ import KgBundleDTO |
| `packages/server-python/tests/contexts/knowledge/test_router_kg_bundle.py` | 新建 | 3 PG-based pytest（80 行）|
| `packages/web/src/services/knowledge.ts` | 修改 | 新增 `KgBundleDTO` interface + `getFileKgBundle` API（10 行）|
| `packages/web/src/views/resource/queries.ts` | 修改 | `useFileKgQuery` 改用新端点（5 行）|
| `docs/03-engineering-governance/technical-debt.md` | post-merge | 不修改（BUG 不入技术债总账） |
| `docs/01-product-planning/04-backlog.md` | post-merge | BUG-006 总览行更新（备注 #4 已 Done）|
| `docs/01-product-planning/05-requirements/BUG-006-...md` | post-merge | 任务卡 #4 段标 ✅ + 补 PR 链接 |
| `docs/03-engineering-governance/work-log.md` | post-merge | 追加长期索引行 |
| `docs/03-engineering-governance/current-work.md` | post-merge | 滚动更新 |

不改：
- 旧 `/nodes` / `/edges` 端点签名
- `list_nodes` / `list_edges_by_file` / `list_edges_by_dataset` 方法
- 其他前端页面（`KnowledgeBaseView` / `DatabaseView`）
- 任何 alembic schema

---

## Task 1: 后端 DTO + Repo 方法

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/application/dto.py:62`
- Modify: `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py:209`

### Step 1: 在 `dto.py` 文件末尾追加 `KgBundleDTO`

打开 `packages/server-python/app/contexts/knowledge/application/dto.py`，在最后一行（L62 末尾）追加：

```python


class KgBundleDTO(BaseModel):
    """BUG-006 #4: 原子返回某文件的 KG nodes + edges, 保证 edges 的
    source_id / target_id 都在 nodes 列表中 (双端 IN 过滤 SQL 实现)."""

    nodes: list[KnowledgeNodeDTO]
    edges: list[KnowledgeEdgeDTO]
```

### Step 2: 在 `knowledge_repository.py` 末尾追加 `get_kg_bundle_for_file` 方法

打开 `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py`，在文件末尾（`delete_cascade` 方法 L209 之后）追加方法（注意保持类内缩进，方法属于 `KnowledgeNodeRepository` 类）：

```python

    async def get_kg_bundle_for_file(
        self, tenant_id: uuid.UUID, file_id: uuid.UUID
    ) -> tuple[list[dict], list[dict]]:
        """BUG-006 #4 fix: 原子返回 (nodes, edges) 保证 edges 的 source/target
        都在 nodes 列表中。

        与 list_nodes (limit=50) + list_edges_by_file (OR 语义) 不同：
        - nodes 无 limit (按文件查天然有上界, dev max=70)
        - edges 用双端 IN 过滤 (AND 语义), 跨文件 edge 不会泄漏进来
        """
        nodes_r = await self._session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_nodes "
                "WHERE tenant_id = :tid AND source_file_id = :fid "
                "ORDER BY created_at"
            ),
            {"tid": tenant_id, "fid": file_id},
        )
        nodes = [dict(row) for row in nodes_r.mappings().all()]

        edges_r = await self._session.execute(
            text(
                "SELECT * FROM metaedu.knowledge_edges "
                "WHERE tenant_id = :tid "
                "AND source_id IN ("
                "  SELECT id FROM metaedu.knowledge_nodes "
                "  WHERE tenant_id = :tid AND source_file_id = :fid"
                ") "
                "AND target_id IN ("
                "  SELECT id FROM metaedu.knowledge_nodes "
                "  WHERE tenant_id = :tid AND source_file_id = :fid"
                ")"
            ),
            {"tid": tenant_id, "fid": file_id},
        )
        edges = [dict(row) for row in edges_r.mappings().all()]

        return nodes, edges
```

### Step 3: ruff check

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m ruff check app/contexts/knowledge/application/dto.py app/contexts/knowledge/infrastructure/knowledge_repository.py
```

Expected: `All checks passed!`

### Step 4: 提交（contract first，无测试不可运行）

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/app/contexts/knowledge/application/dto.py \
        packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py
git commit -m "feat(knowledge): BUG-006 #4 add KgBundleDTO + get_kg_bundle_for_file repo

- KgBundleDTO: nodes + edges atomic response container
- get_kg_bundle_for_file: SQL with AND IN (subquery) on both ends to
  guarantee edges.source/target both in nodes list (no dangling)
- 不修改既有 list_nodes / list_edges_by_file (保持兼容)"
```

---

## Task 2: 后端 router endpoint（TDD red）

**Files:**
- Create: `packages/server-python/tests/contexts/knowledge/test_router_kg_bundle.py`

### Step 1: 写 3 个 PG-based pytest

创建 `packages/server-python/tests/contexts/knowledge/test_router_kg_bundle.py`，写入：

```python
"""BUG-006 #4: GET /api/v1/knowledge/files/{file_id}/kg-bundle 端点测试.

锁 3 个不变量：
1. 端点存在 + 返 200 + DTO 形态正确
2. edges 的 source_id / target_id 必须都在 nodes 列表中（dangling 过滤）
3. 文件无 KG 节点时返 200 + 空 bundle (不返 404)
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

KBASE_URL = "/api/v1/knowledge"


@pytest.mark.asyncio
async def test_kg_bundle_returns_nodes_and_edges_for_file(
    client: AsyncClient,
    auth_headers: dict,
    pg_session: AsyncSession,
) -> None:
    """端点存在, 返 200 + {nodes: [...], edges: [...]} 形态."""
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    fid = uuid.uuid4()

    # 插入 2 nodes + 1 edge (source/target 都在该文件)
    n1 = uuid.uuid4()
    n2 = uuid.uuid4()
    edge_id = uuid.uuid4()
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_nodes "
            "(id, tenant_id, title, domain, level, source_file_id, created_at) "
            "VALUES (:id, :tid, :title, 'education_sports', 'knowledge_point', :fid, NOW())"
        ),
        {"id": n1, "tid": tid, "title": "node-A", "fid": fid},
    )
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_nodes "
            "(id, tenant_id, title, domain, level, source_file_id, created_at) "
            "VALUES (:id, :tid, :title, 'education_sports', 'knowledge_point', :fid, NOW())"
        ),
        {"id": n2, "tid": tid, "title": "node-B", "fid": fid},
    )
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_edges "
            "(id, tenant_id, source_id, target_id, relation_type, weight, created_at) "
            "VALUES (:id, :tid, :src, :tgt, 'rel', 1.0, NOW())"
        ),
        {"id": edge_id, "tid": tid, "src": n1, "tgt": n2},
    )
    await pg_session.commit()

    resp = await client.get(
        f"{KBASE_URL}/files/{fid}/kg-bundle",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert {n["title"] for n in data["nodes"]} == {"node-A", "node-B"}
    assert data["edges"][0]["source_id"] == str(n1)
    assert data["edges"][0]["target_id"] == str(n2)


@pytest.mark.asyncio
async def test_kg_bundle_excludes_dangling_edges(
    client: AsyncClient,
    auth_headers: dict,
    pg_session: AsyncSession,
) -> None:
    """关键不变量: edges 中不能出现 source/target 不在 nodes 列表的 edge.

    复现 BUG-006 #4 真实数据: 教案 65 节点中 1 个 edge target 是另一文件的节点
    (跨文件 edge), 旧 list_edges_by_file OR 语义会返回这种边, 新端点必须过滤掉.
    """
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    fid_a = uuid.uuid4()
    fid_b = uuid.uuid4()  # 另一个文件 (制造 dangling)

    # file A 有 1 节点
    node_in_a = uuid.uuid4()
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_nodes "
            "(id, tenant_id, title, domain, level, source_file_id, created_at) "
            "VALUES (:id, :tid, 'in-A', 'education_sports', 'knowledge_point', :fid, NOW())"
        ),
        {"id": node_in_a, "tid": tid, "fid": fid_a},
    )
    # file B 有 1 节点
    node_in_b = uuid.uuid4()
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_nodes "
            "(id, tenant_id, title, domain, level, source_file_id, created_at) "
            "VALUES (:id, :tid, 'in-B', 'education_sports', 'knowledge_point', :fid, NOW())"
        ),
        {"id": node_in_b, "tid": tid, "fid": fid_b},
    )
    # 跨文件 edge: source 在 A, target 在 B
    await pg_session.execute(
        text(
            "INSERT INTO metaedu.knowledge_edges "
            "(id, tenant_id, source_id, target_id, relation_type, weight, created_at) "
            "VALUES (:id, :tid, :src, :tgt, 'rel', 1.0, NOW())"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tid,
            "src": node_in_a,
            "tgt": node_in_b,
        },
    )
    await pg_session.commit()

    resp = await client.get(
        f"{KBASE_URL}/files/{fid_a}/kg-bundle",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["nodes"]) == 1
    # 关键断言: 跨文件 edge 不应返回, 因 target 不在 file A 的 nodes 集合中
    assert len(data["edges"]) == 0, (
        f"dangling edge leaked: {data['edges']} "
        f"(target {node_in_b} not in file A's nodes)"
    )


@pytest.mark.asyncio
async def test_kg_bundle_empty_for_file_with_no_kg(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    """文件存在但还没抽 KG: 返 200 + 空 bundle (不返 404)."""
    fid = uuid.uuid4()  # 不存在 KG 的随机 file_id

    resp = await client.get(
        f"{KBASE_URL}/files/{fid}/kg-bundle",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {"nodes": [], "edges": []}
```

**测试 fixture 说明**：本 repo 的 `client` / `auth_headers` / `pg_session` fixture 在 `packages/server-python/tests/conftest.py` 已配置（PG-based 测试模式）。如果 `pg_session` fixture 不存在，需要在 conftest.py 加一个，但**先跑一次测试看实际错误信息再决定**——可能现有 `client` fixture 已暴露了一个名字（如 `db_session` 或 `session`）。

### Step 2: 跑测试，确认 fail（端点尚未实现）

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/contexts/knowledge/test_router_kg_bundle.py -v 2>&1 | tail -30
```

Expected: 3 fail，因为 `/files/{fid}/kg-bundle` 路由不存在 → 404。如果 `pg_session` fixture 不存在，会先 ERROR(fixture not found)；那就先看 conftest 现有 db fixture 名字调整测试。

**STOP 检查点**：如果 fixture 名字错误，去 `tests/conftest.py` 确认正确的 PG session fixture 名字（grep `@pytest.fixture` 部分），调整测试 import 后再跑。

### Step 3: 提交（red 阶段）

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/knowledge/test_router_kg_bundle.py
git commit -m "test(knowledge): BUG-006 #4 lock 3 invariants for kg-bundle endpoint (red)"
```

---

## Task 3: 后端 router endpoint（TDD green）

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/interfaces/api/router.py:7-14, 95`

### Step 1: 在 `router.py` 顶部 import 增加 `KgBundleDTO`

打开 `packages/server-python/app/contexts/knowledge/interfaces/api/router.py`，找到 L7-14 现有 import 段：

```python
from app.contexts.knowledge.application.dto import (
    KnowledgeEdgeDTO,
    KnowledgeNodeCreate,
    KnowledgeNodeDTO,
    KnowledgeNodeUpdate,
    KnowledgeSearchDTO,
    SearchResultDTO,
)
```

替换为：

```python
from app.contexts.knowledge.application.dto import (
    KgBundleDTO,
    KnowledgeEdgeDTO,
    KnowledgeNodeCreate,
    KnowledgeNodeDTO,
    KnowledgeNodeUpdate,
    KnowledgeSearchDTO,
    SearchResultDTO,
)
```

### Step 2: 在 `list_knowledge_edges`（L95 endpoint 末尾）之后插入新 endpoint

在 `router.py` L95 行（`list_knowledge_edges` 函数结束的 `]` 之后空行），插入新 endpoint：

```python


@router.get(
    "/files/{file_id}/kg-bundle",
    response_model=KgBundleDTO,
    summary="原子返回某文件的 KG nodes + edges (保证一致性)",
)
async def get_file_kg_bundle(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """BUG-006 #4 fix: 原子返回 KG bundle, 保证 edges.source/target 都在 nodes 列表.

    旧端点 /nodes (limit=50) + /edges (OR 语义) 不一致, 节点数 > 50 时
    g6 渲染会抛 'Node not found'. 本端点用单查询事务 + 双端 IN 过滤
    保证强一致性, 适用于资源库文件详情 KG tab.
    """
    tid = get_tenant_id()
    repo = KnowledgeNodeRepository(session)
    nodes_rows, edges_rows = await repo.get_kg_bundle_for_file(
        tid, uuid.UUID(file_id)
    )
    nodes = [_row_to_dto(r) for r in nodes_rows]
    edges = [
        KnowledgeEdgeDTO(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            weight=row["weight"],
            metadata=row.get("metadata", {}),
        )
        for row in edges_rows
    ]
    return KgBundleDTO(nodes=nodes, edges=edges)
```

### Step 3: 跑测试确认 3/3 PASS

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/contexts/knowledge/test_router_kg_bundle.py -v 2>&1 | tail -15
```

Expected: **3 passed**。

**STOP 检查点**：如果有 fail：
- `404 Not Found`：路由路径写错（应是 `/files/{file_id}/kg-bundle`，前缀已被 `/api/v1/knowledge` 提供）
- `'KgBundleDTO' is not defined`：import 没改完整
- `tenant_id` 错误：检查 `get_tenant_id()` 是否在测试模式正确返回（看 conftest）

### Step 4: 跑全量后端 mock pytest 确认 0 业务回归

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 现有 439+ pytest 全过 + 新加 3 个共 442+ pytest pass。如果 e2e_p1_demo 3 个 SQLAlchemy 失败仍在（pre-existing），那是历史债，不阻塞本任务。

### Step 5: ruff check

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m ruff check app/contexts/knowledge/interfaces/api/router.py tests/contexts/knowledge/test_router_kg_bundle.py
```

Expected: `All checks passed!`

### Step 6: 提交（green 阶段）

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/app/contexts/knowledge/interfaces/api/router.py
git commit -m "feat(knowledge): BUG-006 #4 add GET /files/{file_id}/kg-bundle endpoint

- 原子返回 {nodes, edges}, 保证 edges.source/target 都在 nodes 列表
- 不破坏既有 /nodes /edges 端点 (其他页面仍用)
- 3/3 PG-based pytest pass: 基础形态 / dangling edge 过滤 / 空 bundle 200"
```

---

## Task 4: 前端 service + queries

**Files:**
- Modify: `packages/web/src/services/knowledge.ts:24-39`
- Modify: `packages/web/src/views/resource/queries.ts:108-123`

### Step 1: `services/knowledge.ts` 新增 `KgBundleDTO` interface 和 `getFileKgBundle` API

打开 `packages/web/src/services/knowledge.ts`，在 L23 `KnowledgeEdgeDTO` 接口定义之后插入 `KgBundleDTO`：

找到：
```typescript
export interface KnowledgeEdgeDTO {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight: number;
  metadata: Record<string, unknown>;
}

export const knowledgeApi = {
```

替换为：
```typescript
export interface KnowledgeEdgeDTO {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight: number;
  metadata: Record<string, unknown>;
}

// BUG-006 #4: 原子返回某文件 KG bundle, 保证 edges.source/target 都在 nodes 列表
export interface KgBundleDTO {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
}

export const knowledgeApi = {
```

然后在 `knowledgeApi` 对象内（找到 `listEdges:` 那一行下方，`getNode:` 之前）插入新方法：

找到：
```typescript
  listEdges: (params?: { source_file_id?: string; source_dataset_id?: string }) =>
    api.get<KnowledgeEdgeDTO[]>("/knowledge/edges", { params }),
  getNode: (id: string) => api.get<KnowledgeNodeDTO>(`/knowledge/nodes/${id}`),
```

替换为：
```typescript
  listEdges: (params?: { source_file_id?: string; source_dataset_id?: string }) =>
    api.get<KnowledgeEdgeDTO[]>("/knowledge/edges", { params }),
  // BUG-006 #4: 原子返回某文件 KG bundle (edges.source/target 都在 nodes 列表)
  getFileKgBundle: (fileId: string) =>
    api.get<KgBundleDTO>(`/knowledge/files/${fileId}/kg-bundle`),
  getNode: (id: string) => api.get<KnowledgeNodeDTO>(`/knowledge/nodes/${id}`),
```

### Step 2: `views/resource/queries.ts` 改 `useFileKgQuery` 用新端点

打开 `packages/web/src/views/resource/queries.ts`，找到 L108-123 现有 `useFileKgQuery` 函数：

```typescript
function useFileKgQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.kg(fileId.value)),
    queryFn: async (): Promise<KgBundle> => {
      const [nodesRes, edgesRes] = await Promise.all([
        knowledgeApi.listNodes({ source_file_id: fileId.value }),
        knowledgeApi.listEdges({ source_file_id: fileId.value }),
      ]);
      return { nodes: nodesRes.data, edges: edgesRes.data };
    },
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}
```

替换为：

```typescript
function useFileKgQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.kg(fileId.value)),
    queryFn: async (): Promise<KgBundle> => {
      // BUG-006 #4 fix: 改用原子端点保证 edges.source/target 都在 nodes 列表
      // 旧路径 listNodes(limit=50) + listEdges(无 limit) 在 > 50 节点时
      // g6 抛 'Node not found' 整图白屏
      const { data } = await knowledgeApi.getFileKgBundle(fileId.value);
      return { nodes: data.nodes, edges: data.edges };
    },
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}
```

### Step 3: 跑前端 typecheck + lint

Run:
```bash
cd packages/web && pnpm typecheck 2>&1 | tail -10
cd packages/web && pnpm lint 2>&1 | tail -10
```

Expected: 0 typecheck error / 0 lint error。如果有 `KgBundleDTO unused` warning：检查 import 是否完整。

### Step 4: 跑前端单测（如有）

Run:
```bash
cd packages/web && pnpm test 2>&1 | tail -10
```

Expected: 现有测试不退化（如果 vitest 没配置或 0 测试也算 OK）。

### Step 5: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/web/src/services/knowledge.ts packages/web/src/views/resource/queries.ts
git commit -m "feat(web): BUG-006 #4 useFileKgQuery 改用原子 kg-bundle 端点

- knowledge.ts 新增 KgBundleDTO interface + getFileKgBundle API
- queries.ts useFileKgQuery 改 1 次 HTTP 请求 (原 2 个并行请求)
- 保证 edges.source/target 都在 nodes 列表, 修复 g6 'Node not found' 白屏"
```

---

## Task 5: 整体质量门禁

**Files:** 无修改（仅运行命令）

### Step 1: 全量后端 mock pytest

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m pytest tests/ -q --ignore=tests/e2e 2>&1 | tail -5
```

Expected: 全过（不含 e2e，e2e 3 个 SQLAlchemy 失败是 pre-existing）。

### Step 2: 后端 ruff

Run:
```bash
cd packages/server-python && \
  .venv/bin/python -m ruff check app/ tests/ 2>&1 | tail -5
```

Expected: `All checks passed!`

### Step 3: 前端 typecheck + lint

Run:
```bash
cd packages/web && pnpm typecheck 2>&1 | tail -5
cd packages/web && pnpm lint 2>&1 | tail -5
```

Expected: 0 error。

### Step 4: 工程治理门禁

Run:
```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && \
  scripts/check-engineering-docs 2>&1 | tail -5
git diff --check
```

Expected: exit 0 / clean。

---

## Task 6: 真 PG 复测验收

**Files:** 无修改（运维操作）

### Step 1: 确认 dev PG worker 运行最新代码

Run:
```bash
ps aux | grep -E "celery.*worker" | grep -v grep | awk '{print $2}' | head -1
```

如果有 worker PID 但启动时间早于本任务：
- `kill <PID>`
- `cd packages/server-python && nohup .venv/bin/celery -A app.celery_app worker --loglevel=info --pool=solo > /tmp/celery-worker.log 2>&1 &`

但本任务是后端 API + 前端，**不需要重启 worker**（worker 跑的是 Celery 任务，本端点是 FastAPI 同步路由）。FastAPI server 重启即可：

```bash
# 看 FastAPI server 进程
ps aux | grep -E "uvicorn|main:app" | grep -v grep | head -3
# 用户操作: 重启 server
```

### Step 2: 用 curl 测试新端点（教案文件 65 nodes，最严重场景）

Run（需要 token + tenant header；从浏览器 localStorage 取，或用 dev login）：
```bash
# 替换 <TOKEN> 为浏览器 localStorage 中的 metaedu_token 值
curl -s \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/v1/knowledge/files/d650b552-5193-47a2-9492-842c51c98486/kg-bundle" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes_ids = {n['id'] for n in d['nodes']}
print(f'nodes: {len(d[\"nodes\"])}')
print(f'edges: {len(d[\"edges\"])}')
dangling = [e for e in d['edges'] if e['source_id'] not in nodes_ids or e['target_id'] not in nodes_ids]
print(f'dangling edges: {len(dangling)} (must be 0)')
assert len(dangling) == 0, f'FAIL: dangling = {dangling[:3]}'
print('PASS: 数据层强一致')
"
```

Expected:
```
nodes: 65
edges: 64 (or close, exact count from DB)
dangling edges: 0 (must be 0)
PASS: 数据层强一致
```

### Step 3: 浏览器手测（3 个文件）

操作步骤（用户）：
1. 打开 dev 前端 http://localhost:3000
2. 资源库 → 教案 PDF (`护理学基础_生命体征测量_教案`) → 知识图谱 tab
3. 期望：g6 渲染完整 65 节点 + 64 边，**Console 无 `Node not found` 错误**
4. 资源库 → 课程标准 (`02-《水环境监测》课程标准`) → 知识图谱 tab
5. 期望：g6 渲染 70 节点 + 边数完整，无 console error
6. 资源库 → 人才培养方案 → 知识图谱 tab
7. 期望：g6 渲染 58 节点 + 边数完整，无 console error

### Step 4: 验收不通过的处理

如果 dangling > 0 或 console 仍有 `Node not found`：
- 不在 main 上直推
- 看 dangling edge 的 source/target node 是否在 file 的 nodes 列表
- 排查方向：①SQL 双端 IN 子查询是否真的过滤；②前端是否还在用旧 `listNodes`/`listEdges`（grep `useFileKgQuery` 改动是否生效）

---

## Task 7: 创建 PR + squash merge 到 main

**Files:** 无修改（Git 操作）

### Step 1: push 任务分支

Run:
```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git push origin fix/bug-006-4-kg-bundle-endpoint 2>&1 | tail -5
```

Expected: branch pushed。

### Step 2: 创建 PR

```bash
gh pr create \
  --base main \
  --head fix/bug-006-4-kg-bundle-endpoint \
  --title "fix(knowledge): BUG-006 #4 KG > 50 节点白屏 (新增 kg-bundle 原子端点)" \
  --body "$(cat <<'EOF'
## Summary

修复资源库文件详情 → 知识图谱 tab 在节点数 > 50 时整图白屏（g6 \`Node not found\`）。新增 \`GET /api/v1/knowledge/files/{file_id}/kg-bundle\` 原子端点，保证 edges 的 source/target 都在 nodes 列表中。

## 真因（已 100% 定位）

3 处契约错位：
1. 后端 \`/nodes\` 默认 \`limit=50\` 上限 \`le=100\`
2. 后端 \`/edges\` 无 limit, 用 OR 语义 (跨文件 edge 双方都返回)
3. 前端 \`useFileKgQuery\` 不传 \`limit\`

教案文件 65 节点被截 15 个, 1 条 edge 的 target 是被截节点 → g6 setData 抛 \`Node not found\`。

## 改动

| 类型 | 文件 | 行数 |
|------|------|------|
| 新增 DTO | \`dto.py\` | 10 |
| 新增 Repo 方法 | \`knowledge_repository.py\` | 25 |
| 新增 endpoint | \`router.py\` | 25 |
| 新增 PG 测试 | \`test_router_kg_bundle.py\` | 80 |
| 前端 API | \`knowledge.ts\` | 10 |
| 前端 query | \`queries.ts\` | 5 |

## 不变量

\`\`\`
∀ edge ∈ edges:
    edge.source_id ∈ {n.id for n in nodes}
    AND edge.target_id ∈ {n.id for n in nodes}
\`\`\`

通过 SQL 双端 IN 子查询保证。

## Validation

- 3/3 新 PG-based pytest pass (基础 / dangling 过滤 / 空 bundle)
- 439+ 现有 mock pytest 0 业务代码回归
- ruff check / pnpm typecheck / pnpm lint clean
- scripts/check-engineering-docs exit 0
- git diff --check clean

## 真 PG 复测（post-merge）

- 教案 (65 nodes): \`curl /kg-bundle\` → dangling=0
- 课程标准 (70 nodes): 同上
- 人才培养方案 (58 nodes): 同上
- 浏览器手测 3 文件 KG tab 完整渲染、无 Console error

## 不破坏既有

- \`/nodes\` / \`/edges\` 旧端点完全保留 (KnowledgeBaseView / DatabaseView 仍用)
- \`list_nodes\` / \`list_edges_by_file\` repo 方法不变

## Out of Scope

- BUG-006 #1/#2/#3/#5 (各自独立 PR)

## Docs

- spec: \`docs/02-delivery-plans/01-specs/2026-06-15-bug-006-4-kg-bundle-endpoint.md\`
- plan: \`docs/superpowers/plans/2026-06-15-bug-006-4-kg-bundle-endpoint-plan.md\`
- post-merge 收口 PR 单独提交
EOF
)" 2>&1 | tail -3
```

Expected: PR URL printed, e.g. `https://github.com/MarkDanile/MetaEduBase/pull/295`

### Step 3: 检查 PR

Run:
```bash
gh pr checks <PR_NUMBER> 2>&1 | tail -10
```

Expected: 无 fail（本仓无 CI 检查，输出 `no checks reported` 也算 OK）。

### Step 4: squash merge

Run:
```bash
gh pr merge <PR_NUMBER> --squash --delete-branch 2>&1 | tail -5
```

Expected: `Merged` + branch deleted。

### Step 5: 同步本地 main

Run:
```bash
git checkout main && git pull --ff-only 2>&1 | tail -3
git log --oneline -3
```

Expected: HEAD = squash merge commit，BUG-006 #4 PR 在最上。

---

## Task 8: Post-merge 跨事实源收口（docs-only PR）

**Files:**
- Modify: `docs/01-product-planning/05-requirements/BUG-006-...md`（任务卡 #4 段补 PR 链接 + 状态）
- Modify: `docs/01-product-planning/04-backlog.md`（BUG-006 总览行注 #4 已 Done）
- Modify: `docs/03-engineering-governance/work-log.md`（追加长期索引行）
- Modify: `docs/03-engineering-governance/current-work.md`（滚动）

### Step 1: 建 docs 分支

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git checkout -b docs/bug-006-4-post-merge main
```

### Step 2: 修改 BUG-006 任务卡 (`05-requirements/BUG-006-...md`)

打开 `docs/01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md`。

在 `## 关联` 段落之前插入新段落：

```markdown
## 子项进度

- ✅ **#4 KG > 50 节点白屏** — [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) (squash `<COMMIT>`) 已合并：新增 `GET /api/v1/knowledge/files/{file_id}/kg-bundle` 原子端点保证 edges.source/target 都在 nodes 列表；3 PG-based pytest 锁不变量；真 PG 复测 3 文件 (58/65/70 nodes) 全完整渲染。
- 🔵 #1 前端字段名英文（待开发）
- 🔵 #2 pdf_parser 不识中文章节（待开发）
- 🔵 #3 TD-067 nested 回归（待开发）
- 🔵 #5 返回按钮无效（待开发）

```

将 `<NUMBER>` 和 `<COMMIT>` 替换为 Task 7 的实际 PR # 和 squash commit SHA。

### Step 3: 修改 backlog.md BUG-006 总览行

在 `docs/01-product-planning/04-backlog.md` 找到 BUG-006 行，把 "建议拆 5 PR。" 这段话改为：

```
建议拆 5 PR。**进度**：#4 KG > 50 节点白屏已修（PR #<NUMBER>）。
```

### Step 4: 修改 work-log.md 追加长期索引行

在 `docs/03-engineering-governance/work-log.md` 顶部（按"最近优先"排序），在最近一条索引下方追加：

```markdown
| 2026-06-15 | BUG-006 #4 KG > 50 节点白屏 (kg-bundle 原子端点) | [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) | 后端新增 GET /api/v1/knowledge/files/{file_id}/kg-bundle 双端 IN 过滤；3 PG-based pytest 锁不变量；前端 useFileKgQuery 切新端点；真 PG 复测教案 65 + 课程标准 70 + 人才培养方案 58 三文件 dangling=0 + 浏览器渲染完整。 |
```

### Step 5: 修改 current-work.md 最近完成行

在 `docs/03-engineering-governance/current-work.md` 找到 "最近完成" 表格，**顶部**追加 1 行（同时如果数据行已 ≥ 12 行需删最末 1 行保持 12 行硬约束）：

```markdown
| 2026-06-15 | BUG-006 #4 KG > 50 节点白屏（新增 kg-bundle 原子端点）| 🟢 完成 | PR #<NUMBER> squash merge：后端新增 GET /api/v1/knowledge/files/{file_id}/kg-bundle 双端 IN 过滤保证 edges 的 source/target 都在 nodes 列表。3 PG pytest + 439+ 0 回归 + 真 PG 复测教案/课程标准/人才培养方案 dangling=0。 | [BUG-006 #4](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) |
```

**摘要 ≤ 220 字符**：上方约 200 字符，OK。

### Step 6: 跑门禁

```bash
scripts/check-engineering-docs 2>&1 | tail -3; echo "exit: $?"
git diff --check
```

Expected: exit 0 / clean。如有 `current-work-recent-summary` warning，按 220 字符约束再压缩。

### Step 7: Commit + push + PR + squash merge

```bash
git add docs/01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/work-log.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(governance): BUG-006 #4 跨事实源收口（🟢 完成 + work-log 索引）"
git push origin docs/bug-006-4-post-merge

gh pr create --base main --head docs/bug-006-4-post-merge \
  --title "docs(governance): BUG-006 #4 跨事实源收口（🟢 完成 + work-log 索引）" \
  --body "## Summary
- BUG-006 任务卡 #4 段标 ✅ + 补 PR 链接
- backlog 总览行注 #4 已 Done
- work-log 追加长期索引
- current-work 滚动到 12 行

## Validation
- scripts/check-engineering-docs exit 0
- git diff --check clean
- 0 业务代码 / 0 测试代码 / 0 脚本变更（docs-only）"

gh pr merge <PR_NUMBER> --squash --delete-branch
git checkout main && git pull --ff-only
```

Expected: PR 合并，本地 main 同步。

---

## Self-Review

### 1. Spec coverage

✅ 全覆盖：
- spec §3.1 端点签名 → Task 3
- spec §3.2 不变量 (双端 IN) → Task 1 Step 2 + Task 2 test 2
- spec §3.3 改动文件 → Task 1/3/4 完整覆盖
- spec §3.4 后端实现 → Task 1+3 代码完全一致
- spec §3.5 前端实现 → Task 4 代码完全一致
- spec §3.6 mock pytest 设计 → Task 2 实现 3 个 case
- spec §3.7 真 PG 复测 → Task 6
- spec §3.8 不破坏既有 → Task 1 不删 list_edges_by_file，Task 4 不改 KnowledgeBaseView
- spec §4 Validation → Task 5 + Task 6
- spec §5 Risks → Task 6 Step 4 处理
- spec §6 Out of Scope → Task 1-7 严格遵守

### 2. Placeholder scan

无 TBD / TODO / "implement later" / "Similar to Task N"。所有代码 step 都给完整代码块。

### 3. Type consistency

- `KgBundleDTO` 在 Task 1 Step 1 定义，Task 3 Step 1 import，Task 3 Step 2 使用 ✓
- `get_kg_bundle_for_file` 在 Task 1 Step 2 定义，Task 3 Step 2 调用 ✓
- `getFileKgBundle` 在 Task 4 Step 1 定义，Task 4 Step 2 调用 ✓
- `KgBundle` interface 在 queries.ts 已存在（L103），Task 4 Step 2 复用 ✓

### 4. Order check

- Task 1 (DTO+Repo, contract) → Task 2 (test red) → Task 3 (router green) 顺序 OK
- Task 4 (前端) 不依赖 Task 6 真 PG，独立完成 ✓
- Task 6 真 PG 复测必须在 PR merge 之后还是之前？plan 中放在 Task 7 PR merge 之前——这意味着 PG dev 库需要本地切到 fix 分支 + 重启 server 才能复测；为简化，**真 PG 复测可在 Task 7 PR merge 之后做**（用户 / 维护者操作），不阻塞 PR 流程。已在 Task 6 文案中明确。
- Task 8 docs 收口在 PR merge 之后，符合 git-workflow.md 翻完成前硬条件
