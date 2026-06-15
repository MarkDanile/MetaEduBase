# BUG-006 #4: KG Bundle 原子端点设计

**Date**: 2026-06-15
**Status**: Design — awaiting approval
**Branch**: `fix/bug-006-4-kg-bundle-endpoint`
**Owner**: Claude Code
**Bug source**: [BUG-006 #4](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md)

## 1. Context（背景）

### 1.1 Bug 现象

资源库 → 文件详情 → 知识图谱 tab：当文件 KG 节点数 > 50 时，整图谱白屏。浏览器 Console 报错：

```
Uncaught (in promise) Error: Node not found for id: e25a8f15-c45f-4cf4-bd1a-cb44abe1c308
    at _Graph.getNode (@antv_g6.js:44457:13)
    at _Graph.checkNodeExistence (@antv_g6.js:44434:10)
    at _Graph.doAddEdge (@antv_g6.js:44671:10)
```

### 1.2 真因（已 100% 定位）

不一致由 **3 处契约错位** 累积造成：

| 位置 | 行为 | 后果 |
|------|------|------|
| 后端 `/api/v1/knowledge/nodes` | 默认 `limit=50`、上限 `le=100` | 节点 > 50 被截断 |
| 后端 `/api/v1/knowledge/edges` | 无 limit | 返回该文件全部 edges |
| 前端 `useFileKgQuery` | 不传 `limit` | 用默认 50 |
| 后端 `list_edges_by_file` SQL | 用 **OR** 语义（source 或 target 的 source_file_id 匹配） | 跨文件 edge 双方都返回，但任一方查 nodes 都不含对端 |

数据复测（教案文件 65 nodes）：
- nodes 列表只有前 50 个（按 `created_at` 排序）
- edges 列表 64 条全返回
- 节点 `e25a8f15-... '提灯天使'` rank=62 被截断
- 但 1 条 edge 的 target 是该节点 → g6 渲染时 `Node not found` → 整图崩溃

### 1.3 为何之前没暴露

之前测试人才培养方案 (58 nodes)：前 50 节点恰好涵盖所有 edge 的两端，没触发 dangling。教案 / 课程标准在「前 50 节点不涵盖某 edge 端点」时必现。

## 2. Goal（目标）

- 资源库文件详情 → KG tab 在任意节点数（含 > 50 / > 100 / > 1000）下都能完整渲染
- 浏览器 Console 不再出现 `Node not found` 报错
- 后端返回 `{nodes, edges}` 在数据层保证强一致性：**edge 的 source_id / target_id 都在 nodes 列表中**
- 不破坏现有 `/nodes` / `/edges` 端点（KnowledgeBaseView 主页面 / DatabaseView 仍用）

## 3. Design（设计）

### 3.1 修复策略：新增原子端点

**端点签名**：

```
GET /api/v1/knowledge/files/{file_id}/kg-bundle
→ 200 {
    "nodes": [KnowledgeNodeDTO, ...],
    "edges": [KnowledgeEdgeDTO, ...]
  }
→ 404  file_id 不属于当前 tenant 或不存在（保留 404 语义；空文件返回空 bundle 而非 404）
→ 401  未鉴权（标准 dependencies）
```

### 3.2 关键不变量

新端点保证：

```
∀ edge ∈ edges:
    edge.source_id ∈ {n.id for n in nodes}
    AND edge.target_id ∈ {n.id for n in nodes}
```

通过 SQL 双端 IN 过滤实现（**而非** 旧端点的 OR 语义）：

```sql
-- nodes (no limit; per-file 自然边界)
SELECT * FROM metaedu.knowledge_nodes
WHERE tenant_id = :tid AND source_file_id = :fid;

-- edges (双端必须都在该文件的 nodes 集合中)
SELECT * FROM metaedu.knowledge_edges
WHERE tenant_id = :tid
  AND source_id IN (SELECT id FROM metaedu.knowledge_nodes WHERE source_file_id = :fid)
  AND target_id IN (SELECT id FROM metaedu.knowledge_nodes WHERE source_file_id = :fid);
```

### 3.3 改动文件清单

| File | 改动类型 | 行数估算 |
|------|----------|----------|
| `packages/server-python/app/contexts/knowledge/application/dto.py` | 新增 `KgBundleDTO` | ~10 行 |
| `packages/server-python/app/contexts/knowledge/infrastructure/knowledge_repository.py` | 新增 `get_kg_bundle_for_file` | ~25 行 |
| `packages/server-python/app/contexts/knowledge/interfaces/api/router.py` | 新增 `GET /files/{file_id}/kg-bundle` | ~25 行 |
| `packages/server-python/tests/contexts/knowledge/test_router.py` | 新增 3 mock pytest | ~80 行 |
| `packages/web/src/services/knowledge.ts` | 新增 `getKgBundle` API + DTO | ~10 行 |
| `packages/web/src/views/resource/queries.ts` | `useFileKgQuery` 改用新端点 | ~5 行 |

### 3.4 后端实现

**dto.py 新增**：

```python
class KgBundleDTO(BaseModel):
    nodes: list[KnowledgeNodeDTO]
    edges: list[KnowledgeEdgeDTO]
```

**knowledge_repository.py 新增方法**：

```python
async def get_kg_bundle_for_file(
    self, tenant_id: uuid.UUID, file_id: uuid.UUID
) -> tuple[list[dict], list[dict]]:
    """BUG-006 #4 fix: 原子返回 (nodes, edges) 保证 edges 的 source/target
    都在 nodes 列表中。

    与 list_nodes (limit=50) + list_edges_by_file (OR 语义) 不同：
    - nodes 无 limit (按文件查天然有上界)
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

**router.py 新增端点**（位置：放在 `list_knowledge_edges` L69 之后）：

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
    """BUG-006 #4 fix: 原子返回 KG bundle, 保证 edges.source/target 都在 nodes 列表。

    旧端点 /nodes (limit=50) + /edges (OR 语义) 不一致, 节点数 > 50 时
    g6 渲染会抛 'Node not found'. 本端点用单查询事务 + 双端 IN 过滤
    保证强一致性, 适用于资源库文件详情 KG tab。
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

**说明**：路径选 `/files/{file_id}/kg-bundle` 而非 `/kg-bundle?file_id=...`，因 RESTful 资源风格更清晰；且未来若加 `/datasets/{ds_id}/kg-bundle` 双胞胎端点更对称。

### 3.5 前端实现

**services/knowledge.ts 新增**：

```typescript
export interface KgBundleDTO {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
}

export const knowledgeApi = {
  // ... 现有方法保留 ...
  getFileKgBundle: (fileId: string) =>
    api.get<KgBundleDTO>(`/knowledge/files/${fileId}/kg-bundle`),
};
```

**queries.ts 改动 useFileKgQuery**：

```typescript
function useFileKgQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.kg(fileId.value)),
    queryFn: async (): Promise<KgBundle> => {
      // BUG-006 #4 fix: 改用原子端点保证 edges 不引用未返回的 nodes
      const { data } = await knowledgeApi.getFileKgBundle(fileId.value);
      return { nodes: data.nodes, edges: data.edges };
    },
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}
```

### 3.6 mock pytest 设计

新建 `tests/contexts/knowledge/test_router.py` 的 3 个 case（patch repo + AsyncMock session）：

1. **test_kg_bundle_returns_nodes_and_edges_for_file**
   - mock repo 返 5 nodes + 3 edges (source/target 都在 nodes)
   - 断言响应 `{"nodes": [...5 items...], "edges": [...3 items...]}`
   - 断言 status_code=200

2. **test_kg_bundle_excludes_dangling_edges_via_sql_filter**
   - mock session.execute 第一次（nodes 查询）返 3 nodes [A, B, C]
   - mock session.execute 第二次（edges 查询）—— 因为是真实 SQL 双端 IN 过滤，dangling edge 在 SQL 层已过滤；本测试通过 spy SQL 字符串验证 `IN (SELECT id FROM ...)` 双端过滤
   - 断言两次 execute 的 SQL 字符串都含 `source_id IN` AND `target_id IN`

3. **test_kg_bundle_empty_for_file_with_no_nodes**
   - mock repo 返 ([], [])
   - 断言响应 `{"nodes": [], "edges": []}`、status_code=200（**不返 404**——文件可能合法但还没抽 KG）

### 3.7 真 PG 复测验收

修复合 main 后维护者跑：

```bash
# 1. 取教案 file_id (65 nodes，最严重)
curl -s -H "X-Tenant-ID: 00000000-...001" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/knowledge/files/d650b552-5193-47a2-9492-842c51c98486/kg-bundle" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes_ids = {n['id'] for n in d['nodes']}
print(f'nodes: {len(d[\"nodes\"])}, edges: {len(d[\"edges\"])}')
dangling = [e for e in d['edges'] if e['source_id'] not in nodes_ids or e['target_id'] not in nodes_ids]
print(f'dangling edges: {len(dangling)} (must be 0)')
assert len(dangling) == 0
"

# 2. 浏览器手测：资源库 → 教案 → KG tab
#    期望: 65 节点 + 64 边完整渲染, 无 Console error
```

### 3.8 不破坏既有调用方

- `/api/v1/knowledge/nodes` / `/api/v1/knowledge/edges` 完全保留，签名不变
- `KnowledgeBaseView.vue` 主页面用 `listNodes(parent_id)` 不变
- `DatabaseView` 用 `listNodes(source_dataset_id)` 不变
- 仅 `useFileKgQuery`（资源库文件详情 KG tab）改用新端点

## 4. Validation（验证）

### 4.1 单元测试

- 后端：`pytest tests/contexts/knowledge/test_router.py::test_kg_bundle_* -v` → 3/3 pass
- 后端：`pytest tests/ -q` → 现有 439 mock pytest 0 业务代码回归
- 前端：`pnpm test` 现有测试不退化（本任务暂不加前端单测，端到端真 PG 复测兜底）

### 4.2 真 PG 复测

- dev 库教案文件（65 nodes）：curl `/kg-bundle` → dangling=0 / nodes 完整 / status=200
- dev 库人才培养方案 (58) / 课程标准 (70) 各跑 1 次复测
- 浏览器手测 3 个文件 KG tab 全部完整渲染、无 Console error

### 4.3 质量门禁

- `ruff check app/ tests/` clean
- `pnpm typecheck` clean（前端 TS）
- `git diff --check` clean
- `scripts/check-engineering-docs` 退出码 0

## 5. Risks（风险）

| 风险 | 缓解 |
|------|------|
| 双端 IN 子查询性能（大文件 1000+ 节点）| dev 库 max=70 节点；PG 内联 IN+索引 (source_file_id, source_id, target_id) 估计 < 50ms；如生产 > 1s 加 follow-up TD |
| 跨文件 edge 不再返回（旧 OR 语义返回的）| 文件详情 KG 视图本就期望"本文件内的图谱"，跨文件 edge 不属于本视图；如需跨文件 edge 走 KnowledgeBaseView 主页面 |
| 前端 useFileKgQuery 单点切换 | listNodes/listEdges 旧 API 仍存活，仅资源库 KG tab 切换；其他视图不受影响 |
| 路径冲突 | `/files/{file_id}/kg-bundle` 在 `/knowledge/` prefix 下，与 `/knowledge/nodes/{node_id}` 不冲突（不同动词路径段）|

## 6. Out of Scope（不在范围）

- BUG-006 #1（前端字段名 label）—— 独立 PR
- BUG-006 #2（pdf_parser 中文章节）—— 独立 PR
- BUG-006 #3（TD-067 nested 回归）—— 独立 PR
- BUG-006 #5（返回按钮无效）—— 独立 PR
- 废弃 `/nodes` / `/edges` 旧端点（保留兼容）
- KnowledgeBaseView 主页面 limit 调整（不涉及）
- DatabaseView 数据集 KG（不涉及）
- 任何 alembic schema 改动
- 后端 KG-bundle 大文件性能优化（dev 库 max 70 节点足够，未触发性能瓶颈）

## 7. Plan

进入 writing-plans skill 编写实施计划后落地：

1. `fix/bug-006-4-kg-bundle-endpoint` 分支已建（commit 0 个，本 spec 是首个 commit）
2. 写后端 DTO + Repo + Router (3 文件 + 60 行)
3. 写 3 mock pytest（TDD red → green）
4. 写前端 service + queries（2 文件 + 15 行）
5. 跑 pytest + ruff + check-engineering-docs + typecheck
6. commit + push + PR (fix 分支) → merge
7. 真 PG dev 库复测（教案 / 人才培养方案 / 课程标准 3 文件）
8. 浏览器手测 3 文件 KG tab 完整渲染
9. post-merge 收口 PR (docs 分支：BUG-006 任务卡 #4 翻 🟢 完成 + work-log 索引 + current-work 滚动)
10. 删分支
