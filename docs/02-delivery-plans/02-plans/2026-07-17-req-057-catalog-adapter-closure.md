# REQ-057 Implementation Plan: Catalog 数据源 Adapter 路由与 entity_type 契约收口

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 adapter registry 路由（imported_dataset / direct_db / mcp）+ MCP 不伪装成功 + entity_type 策略文档统一 + REQ-054 完成声明修正。

**Architecture:** 扩展 `default_adapter_factory` 支持 3 种类型路由；MCP adapter 改为抛 `CapabilityUnavailableError`；文档统一为"动态发现"策略；REQ-054 AC 按真实验证层级重写。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pytest + pydantic v2

## Global Constraints

- 不破坏现有 215+ backend tests
- MCP V1 不得返回 `[]` 伪装"查询成功但无数据"
- DirectDB V1 接入 registry，只读 SELECT + table_name 正则白名单 + limit clamp
- entity_type 策略统一为"动态发现"（PR #422 已实施），所有文档只保留一种事实
- pytest 必须在 packages/server-python/ 下跑
- ruff 0 / check-engineering-docs 0

---

## File Structure

### 后端修改
- `app/contexts/structured_data/application/query_service.py` - 扩展 `default_adapter_factory` 支持 3 种类型
- `app/contexts/structured_data/infrastructure/mcp_adapter.py` - 改为抛 `CapabilityUnavailableError`
- `app/contexts/structured_data/domain/data_source_adapter.py` - 加 `CapabilityUnavailableError` 异常

### 后端新建测试
- `tests/contexts/structured_data/test_adapter_registry.py` - adapter factory 路由测试

### 文档修改
- `docs/01-product-planning/05-requirements/REQ-054-platform-database-catalog.md` - AC 按真实验证层级重写
- `docs/01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md` - Status + Delivery Record
- `docs/01-product-planning/04-backlog.md` - REQ-057 状态
- `docs/03-engineering-governance/current-work.md` - TASK card
- `docs/03-engineering-governance/work-log.md` - +1 index row

---

## Task 1: Adapter registry 扩展 + DirectDB 接入 + MCP 改为明确 unavailable

**Files:**
- Modify: `app/contexts/structured_data/domain/data_source_adapter.py` (加 CapabilityUnavailableError)
- Modify: `app/contexts/structured_data/application/query_service.py` (扩展 default_adapter_factory)
- Modify: `app/contexts/structured_data/infrastructure/mcp_adapter.py` (不返回 []，抛异常)
- Test: `tests/contexts/structured_data/test_adapter_registry.py` (new)

**Interfaces:**
- Consumes: ImportedDatasetAdapter / DirectDBAdapter / MCPAdapter (已有)
- Produces: `default_adapter_factory` 支持 3 种类型路由 + MCP 明确 unavailable

- [ ] **Step 1: 加 CapabilityUnavailableError 异常**

```python
# data_source_adapter.py
class CapabilityUnavailableError(Exception):
    """Raised when an adapter's capability is not yet implemented (e.g. MCP V1).
    
    Distinct from returning [] (which would masquerade as 'query succeeded, no data').
    The router maps this to a 501 Not Implemented or 400 with clear capability message.
    """
```

- [ ] **Step 2: MCP adapter 改为抛异常（不返回 []）**

```python
# mcp_adapter.py
async def query(self, query_plan, semantic_model, tenant_id, user_role) -> list[dict]:
    raise CapabilityUnavailableError(
        "MCP adapter V1: 真实 MCP server 未接入（REQ-044 / REQ-046 承接）。"
        "当前不支持查询，不得伪装为空结果成功。"
    )
```

- [ ] **Step 3: 扩展 default_adapter_factory 支持 3 种类型**

```python
# query_service.py
async def default_adapter_factory(data_source_config, session):
    ds_type = (data_source_config or {}).get("type", "imported_dataset")
    if ds_type == "imported_dataset":
        return ImportedDatasetAdapter(session)
    if ds_type == "direct_db":
        return DirectDBAdapter(session, config=data_source_config)
    if ds_type == "mcp":
        return MCPAdapter(session, config=data_source_config)
    raise ValueError(f"Unknown data_source type: {ds_type!r}")
```

- [ ] **Step 4: 写 adapter registry 测试**

```python
# test_adapter_registry.py
@pytest.mark.asyncio
async def test_factory_routes_imported_dataset():
    adapter = await default_adapter_factory({"type": "imported_dataset"}, session)
    assert isinstance(adapter, ImportedDatasetAdapter)

@pytest.mark.asyncio
async def test_factory_routes_direct_db():
    adapter = await default_adapter_factory({"type": "direct_db", "connection_string": "...", "table_name": "t"}, session)
    assert isinstance(adapter, DirectDBAdapter)

@pytest.mark.asyncio
async def test_factory_routes_mcp():
    adapter = await default_adapter_factory({"type": "mcp", "server_url": "...", "tool_name": "..."}, session)
    assert isinstance(adapter, MCPAdapter)

@pytest.mark.asyncio
async def test_mcp_query_raises_capability_unavailable():
    adapter = MCPAdapter(session, config={...})
    with pytest.raises(CapabilityUnavailableError):
        await adapter.query(...)

@pytest.mark.asyncio
async def test_unknown_type_raises_value_error():
    with pytest.raises(ValueError):
        await default_adapter_factory({"type": "unknown"}, session)
```

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_adapter_registry.py -v -W error
git commit -m "feat(structured-data): REQ-057 adapter registry 3 类型路由 + MCP 改为 CapabilityUnavailableError"
```

---

## Task 2: 两 Catalog 同 entity_type 隔离集成测试 (AC-5)

**Files:**
- Test: `tests/contexts/structured_data/test_catalog_dual_key_isolation.py` (new)

- [ ] **Step 1: 写集成测试**

```python
# test_catalog_dual_key_isolation.py
@pytest.mark.asyncio
async def test_two_catalogs_same_entity_type_isolated(db_session):
    """两个 Catalog 使用相同 entity_type=bill 时，语义模型、问数结果和审计 catalog_id 均正确隔离。"""
    # 1. 建 2 个 catalog (education + park)
    # 2. 各自建 semantic_model (entity_type=bill, 不同 column_mapping)
    # 3. 各自上传不同 dataset_rows
    # 4. QueryService.ask(catalog_id=education, entity_type=bill) -> 返回 education 的数据
    # 5. QueryService.ask(catalog_id=park, entity_type=bill) -> 返回 park 的数据
    # 6. 验证 audit_log catalog_id 分别正确
```

- [ ] **Step 2: 跑测试 + commit**

```bash
pytest tests/contexts/structured_data/test_catalog_dual_key_isolation.py -v -W error
git commit -m "test(structured-data): REQ-057 两 Catalog 同 entity_type 隔离集成测试 (AC-5)"
```

---

## Task 3: entity_type 策略文档统一 + REQ-054 AC 修正

**Files:**
- Modify: `docs/01-product-planning/05-requirements/REQ-054-platform-database-catalog.md`
- Modify: `docs/01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`

- [ ] **Step 1: REQ-054 AC 修正** - 按真实验证层级重写 AC-1~AC-10 + Delivery Record 补 PR #421/#422/#424

- [ ] **Step 2: entity_type 策略统一** - Requirement/Spec/Plan 中"白名单"改为"动态发现"

- [ ] **Step 3: REQ-057 Status -> 🟢 Done + Delivery Record**

- [ ] **Step 4: backlog + current-work + work-log 同步**

- [ ] **Step 5: 跑门禁 + commit**

```bash
python3 scripts/check-engineering-docs
git commit -m "docs(closeout): REQ-057 实施完成 + REQ-054 AC 修正 + entity_type 策略统一"
```

---

## Self-Review

1. **AC-1**: adapter registry 按 config.type 路由 3 种类型；未知类型返回稳定错误
2. **AC-2**: DirectDB 接入 QueryService 路径可达（通过 factory）
3. **AC-3**: MCP 不返回 [] 伪装成功；抛 CapabilityUnavailableError
4. **AC-4**: entity_type 策略在 Requirement/Spec/Plan/Backlog/API/前端/migration 一致（动态发现）
5. **AC-5**: 两 Catalog 同 entity_type 隔离测试
6. **AC-6**: REQ-054 AC 按真实验证层级重写

---

## Execution Handoff

Plan complete. 3 tasks, estimated 2-3 subagent rounds.

**Two execution options:**
1. **Subagent-Driven (recommended)** - Fresh subagent per task + review between tasks
2. **Inline Execution** - Execute in this session
