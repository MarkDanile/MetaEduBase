# REQ-056 Implementation Plan: 智能问数真实执行闭环与 AI Chat 生产接线

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭 REQ-052 的 3 个生产缺口（ImportedDataset 未接 JsonbQueryBuilder / AI Chat 未注入 QueryService / Catalog 双键路由）+ 跑 10 个真实业务样例完成 AC-7。

**Architecture:** 复用 REQ-052 已建 JsonbQueryBuilder / AIChatService / QueryService 骨架，修 3 个集成点 + 加审计 fail-closed + 真实 DB 回归样例。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy 2.x async + pytest + alembic + pydantic v2（已有 REQ-052/054 基础设施）

## Global Constraints

- 不破坏 REQ-052 / REQ-054 已有 210 backend tests + 144 frontend tests
- pytest 必须在 packages/server-python/ 下跑（PG 通过 ssh tunnel 可用）
- ruff 0 / check-engineering-docs 0
- AI Chat 注入 user_id / role / tenant_id **必须来自认证用户**（current_user），不得用随机 UUID 代替
- 审计写入失败默认 fail-closed，禁止吞异常后继续提交
- 不重做 AI Chat 会话持久化 / Agent runtime（V2 范围）

---

## File Structure

### 后端新建
- `tests/contexts/structured_data/test_imported_dataset_filtering_e2e.py` — DB 集成测试（"过滤前后结果不同"）
- `tests/contexts/structured_data/test_audit_fail_closed.py` — 审计 fail-closed 测试
- `tests/contexts/knowledge/test_ai_chat_query_service_integration.py` — AI Chat 注入 QueryService 测试
- `tests/contexts/knowledge/test_ai_chat_catalog_dual_key.py` — (catalog_id, entity_type) 双键测试
- `tests/real_world/req056_business_samples.py` — 10 个真实业务样例回归

### 后端修改
- `app/contexts/structured_data/infrastructure/imported_dataset_adapter.py` — 调用 JsonbQueryBuilder
- `app/contexts/knowledge/application/ai_chat_service.py` — 注入 QueryService + catalog_id + user_id
- `app/contexts/knowledge/interfaces/api/ai_router.py` — `/ai/chat/evidence` 传认证 user + request-bound QueryService
- `app/contexts/structured_data/application/query_service.py` — 审计 fail-closed

### 无新增 alembic（复用 REQ-054 的 012-019 迁移）

---

## Task 1: ImportedDatasetAdapter 接 JsonbQueryBuilder

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/imported_dataset_adapter.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_imported_dataset_filtering_e2e.py` (new)

**Interfaces:**
- Consumes: `JsonbQueryBuilder.build(query_plan, semantic_model, tenant_id) -> Select` (已有)
- Produces: 完整 SQLAlchemy statement（带 filters + time_range + limit），由 adapter 执行 fetch

- [ ] **Step 1: 写失败测试（DB 集成）**

```python
# test_imported_dataset_filtering_e2e.py
import pytest
from app.contexts.structured_data.infrastructure.imported_dataset_adapter import ImportedDatasetAdapter
from app.contexts.structured_data.domain.semantic_model import SemanticModel
import uuid

@pytest.mark.asyncio
async def test_filters_change_results(db_session, sample_dataset_with_rows):
    # sample_dataset_with_rows: 5 rows with company_name in {A, A, B, B, C}
    adapter = ImportedDatasetAdapter(db_session)
    sm = SemanticModel(dataset_id=sample_dataset_with_rows["id"], entity_type="bill")
    
    # 无过滤 -> 5 行
    res_all = await adapter.query(
        query_plan={"limit": 100},
        semantic_model=sm,
        tenant_id=sample_dataset_with_rows["tenant_id"],
        user_role="employee",
    )
    assert len(res_all) == 5
    
    # 过滤 company_name=A -> 2 行
    res_filtered = await adapter.query(
        query_plan={"limit": 100, "filters": {"company_name": {"op": "eq", "value": "A"}}},
        semantic_model=sm,
        tenant_id=sample_dataset_with_rows["tenant_id"],
        user_role="employee",
    )
    assert len(res_filtered) == 2
    assert all(r["company_name"] == "A" for r in res_filtered)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd packages/server-python && pytest tests/contexts/structured_data/test_imported_dataset_filtering_e2e.py -v`
Expected: FAIL (adapter currently doesn't apply filters)

- [ ] **Step 3: 修改 ImportedDatasetAdapter.query 使用 JsonbQueryBuilder**

```python
# imported_dataset_adapter.py
from app.contexts.structured_data.infrastructure.jsonb_query_builder import JsonbQueryBuilder

class ImportedDatasetAdapter(DataSourceAdapter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._builder = JsonbQueryBuilder(session)
    
    async def query(self, query_plan, semantic_model, tenant_id, user_role) -> list[dict]:
        stmt = self._builder.build(query_plan, semantic_model, tenant_id)
        if stmt is None:
            return []
        result = await self._session.execute(stmt)
        return [row for row, in result.all()]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/contexts/structured_data/test_imported_dataset_filtering_e2e.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/server-python/app/contexts/structured_data/infrastructure/imported_dataset_adapter.py packages/server-python/tests/contexts/structured_data/test_imported_dataset_filtering_e2e.py
git commit -m "feat(structured-data): REQ-056 Task 1 ImportedDatasetAdapter 接 JsonbQueryBuilder (filters + time_range + limit)"
```

---

## Task 2: AI Chat 注入 request-bound QueryService + 真实 user_id/role/tenant_id

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` (chat 方法签名 + 实际注入 query_service)
- Modify: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py` (`/chat/evidence` 传 user_id/role/tenant_id)
- Test: `packages/server-python/tests/contexts/knowledge/test_ai_chat_query_service_integration.py` (new)

**Interfaces:**
- Consumes: `QueryService.ask(...)` (REQ-052 已有, REQ-054 Task 6 加了 catalog_id)
- Produces: AIChatService.chat 实际调用 QueryService.ask 而不是降级分支

- [ ] **Step 1: 写失败测试**

```python
# test_ai_chat_query_service_integration.py
import pytest
from app.contexts.knowledge.application.ai_chat_service import AIChatService
from app.contexts.knowledge.application.evidence_fusion import RRFFusion
# REQ-046 Task 4: 真实 LLM mock 返回 tool_call
@pytest.mark.asyncio
async def test_ai_chat_evidence_calls_query_service_with_auth_user():
    # Mock LLM 返回 query_internal_data tool_call
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value=json.dumps({
        "choices": [{"message": {
            "tool_calls": [{"id": "1", "type": "function",
                            "function": {"name": "query_internal_data",
                                          "arguments": json.dumps({"question": "test", "entity_hint": "bill"})}}]
        }}]
    }))
    
    mock_qs = AsyncMock()
    mock_qs.ask = AsyncMock(return_value={
        "ok": True, "result_rows": [{"amount": 100}], "summary": "test", "duration_ms": 10
    })
    
    service = AIChatService(
        chunk_retriever=...,
        evidence_fusion=RRFFusion(),
        llm=mock_llm,
        query_service=mock_qs,
    )
    auth_user = {"id": uuid.UUID("00000000-0000-0000-0000-000000000099"),
                 "tenant_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                 "role": "manager"}
    
    await service.chat(ChatRequest(message="test"), current_user=auth_user)
    
    # 验证 QueryService.ask 被调用，user_id 是认证用户 ID（不是随机 UUID）
    mock_qs.ask.assert_awaited_once()
    call_kwargs = mock_qs.ask.await_args.kwargs
    assert call_kwargs["user_id"] == auth_user["id"]
    assert call_kwargs["role"] == "manager"
    assert call_kwargs["tenant_id"] == auth_user["tenant_id"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/contexts/knowledge/test_ai_chat_query_service_integration.py -v`
Expected: FAIL (current_user not passed, fallback to random UUID)

- [ ] **Step 3: 修改 AIChatService.chat 接受 current_user 参数**

```python
# ai_chat_service.py
async def chat(
    self,
    request: ChatRequest,
    *,
    current_user: dict | None = None,  # NEW
) -> ServiceChatResponse:
    user_id = current_user["id"] if current_user else uuid.uuid4()
    role = current_user.get("role", "employee") if current_user else "employee"
    tenant_id = current_user["tenant_id"] if current_user else get_tenant_id()
    # ... in tool_call branch:
    tool_result = await self.query_service.ask(
        question=...,
        user_id=user_id,
        role=role,
        tenant_id=tenant_id,
        # ... existing args
    )
```

- [ ] **Step 4: 修改 ai_router.py /chat/evidence 传 current_user**

```python
# ai_router.py
result = await service.chat(
    ServiceChatRequest(message=data.message, ...),
    current_user=_current_user,  # NEW
)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/contexts/knowledge/test_ai_chat_query_service_integration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/server-python/app/contexts/knowledge/application/ai_chat_service.py packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py packages/server-python/tests/contexts/knowledge/test_ai_chat_query_service_integration.py
git commit -m "feat(knowledge): REQ-056 Task 2 AIChatService 注入 request-bound QueryService + 真实 user_id"
```

---

## Task 3: AI Chat catalog_id 双键路由 (catalog_id, entity_type)

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` (query_internal_data tool 传 catalog_id)
- Test: `packages/server-python/tests/contexts/knowledge/test_ai_chat_catalog_dual_key.py` (new)

**Interfaces:**
- Consumes: `QueryService.ask(catalog_id=..., entity_type=..., ...)` (REQ-054 Task 6 已有)
- Produces: AI Chat tool_call 显式传 catalog_id（从系统上下文或工具参数）

- [ ] **Step 1: 写失败测试**

```python
# test_ai_chat_catalog_dual_key.py
@pytest.mark.asyncio
async def test_ai_chat_routes_to_correct_catalog_with_dual_entity_type():
    # 2 个 catalog 都有 bill entity_type
    # AI Chat 问 "园区 bill" -> 路由到园区 catalog 的 semantic_model
    # AI Chat 问 "教育 bill" -> 路由到教育 catalog 的 semantic_model
    ...
    mock_qs.ask.assert_awaited_with(catalog_id="park_uuid", entity_type="bill", ...)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/contexts/knowledge/test_ai_chat_catalog_dual_key.py -v`
Expected: FAIL (current tool_call schema doesn't include catalog_id)

- [ ] **Step 3: 更新 query_internal_data tool 声明 + 解析 catalog_id**

```python
# ai_chat_service.py - tool definition
_QUERY_INTERNAL_DATA_TOOL = {
    "type": "function",
    "function": {
        "name": "query_internal_data",
        "description": "查询内部结构化数据...",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "entity_hint": {"type": "string", "enum": ["customer", "contract", "lease", "bill", "ticket"]},
                "catalog_id": {"type": "string", "description": "数据库 ID；不填时用默认"}  # NEW
            },
            "required": ["question"]
        }
    }
}

# In tool_call handler:
catalog_id = args.get("catalog_id") or self._default_catalog_id(current_user)
tool_result = await self.query_service.ask(
    question=args["question"],
    catalog_id=uuid.UUID(catalog_id),
    entity_type=args["entity_hint"],
    ...
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/contexts/knowledge/test_ai_chat_catalog_dual_key.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/server-python/app/contexts/knowledge/application/ai_chat_service.py packages/server-python/tests/contexts/knowledge/test_ai_chat_catalog_dual_key.py
git commit -m "feat(knowledge): REQ-056 Task 3 AIChat query_internal_data 工具加 catalog_id 双键路由"
```

---

## Task 4: 审计 fail-closed（QueryService 任何阶段失败 → 不返回敏感数据）

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/application/query_service.py` (audit 失败时 fail-closed)
- Test: `packages/server-python/tests/contexts/structured_data/test_audit_fail_closed.py` (new)

**Interfaces:**
- Consumes: 现有 _audit 方法
- Produces: audit 写入失败时抛错（不返回结果）

- [ ] **Step 1: 写失败测试**

```python
# test_audit_fail_closed.py
@pytest.mark.asyncio
async def test_audit_failure_does_not_return_results():
    # Mock audit_repo.log_query 抛异常
    # QueryService.ask 应该 propagate exception，不返回 result_rows
    ...
    with pytest.raises(Exception):
        await query_service.ask(...)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/contexts/structured_data/test_audit_fail_closed.py -v`
Expected: FAIL (current code may swallow exception and return results)

- [ ] **Step 3: 修改 _audit 方法保证 fail-closed**

```python
# query_service.py
async def _audit(self, session, *, semantic_model, ..., audit_repo) -> None:
    try:
        log = QueryAuditLogModel(...)
        session.add(log)
        await session.flush()
    except Exception as e:
        logger.error("REQ-056: audit write failed; aborting query", exc_info=e)
        raise  # fail-closed: 不返回结果
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/contexts/structured_data/test_audit_fail_closed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/server-python/app/contexts/structured_data/application/query_service.py packages/server-python/tests/contexts/structured_data/test_audit_fail_closed.py
git commit -m "feat(structured-data): REQ-056 Task 4 QueryService 审计 fail-closed (异常时不返回结果)"
```

---

## Task 5: 10 个真实业务样例 + 端到端验收 (AC-6 + AC-7)

**Files:**
- New: `packages/server-python/tests/real_world/req056_business_samples.py`
- Modify: `docs/01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md` (Status Reopen → Done)
- Modify: `docs/01-product-planning/05-requirements/REQ-056-...md` (Delivery Record + Status → Done)
- Modify: `docs/01-product-planning/04-backlog.md` (REQ-052 + REQ-056 状态)
- Modify: `docs/03-engineering-governance/current-work.md` (workbench)

**Interfaces:**
- Consumes: 真实 dev DB + API + AI Chat
- Produces: 10 个业务样例 + 端到端命令 + 响应证据 + 审计行证据

- [ ] **Step 1: 创建 10 个业务样例 fixture + 端到端测试**

```python
# tests/real_world/req056_business_samples.py
"""
REQ-056 AC-6 + AC-7: 10 个真实业务样例 + 端到端验收

10 个样例覆盖:
- 成功 (3): bill 总额、合同到期、客户数
- 空结果 (2): 未来日期过滤、未知客户
- 权限不足 (2): employee 看薪资、auditor 看账单明细
- 字段缺失 (1): 上传 CSV 缺日期列
- 企业过滤 (1): "江苏神码" 单个企业
- 时间过滤 (1): "过去 3 年"
- 多 catalog (1): 园区 vs 教育 bill 双键
"""

@pytest.mark.asyncio
async def test_sample_01_bill_total(client, auth_headers, sample_bill_data):
    """成功: 园区 bill 总额"""
    ...

# 10 个类似 test
```

- [ ] **Step 2: 跑 10 个样例确认全绿**

Run: `pytest tests/real_world/req056_business_samples.py -v`
Expected: 10/10 passed

- [ ] **Step 3: 端到端验收（curl + 真实 API）**

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

# 2. curl POST /ask (API 端到端)
curl -X POST http://localhost:8000/api/v1/data-query/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"catalog_id":"...","entity_type":"bill","question":"...","business_purpose":"..."}'

# 3. 验证 query_audit_log 写入
psql -h localhost -U metaedu -d metaedu -c \
  "SELECT business_purpose, question, result_count FROM metaedu.query_audit_log ORDER BY created_at DESC LIMIT 1"

# 4. AI Chat 端到端
curl -X POST http://localhost:8000/api/v1/ai/chat/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"园区 bill 总额"}'
```

记录命令 + 响应摘要 + 审计行证据到 `tests/real_world/req056_business_samples.py` docstring。

- [ ] **Step 4: 状态同步**

- `docs/01-product-planning/05-requirements/REQ-052-...md`: Status 🟢 Done → ⚪ Reopen → 🟢 Done
- `docs/01-product-planning/05-requirements/REQ-056-...md`: Status 🔵 Ready → 🟢 Done + Delivery Record
- `docs/01-product-planning/04-backlog.md`: REQ-052 状态 + REQ-056 状态同步
- `docs/03-engineering-governance/current-work.md`: TASK card 处理（REQ-056 done 后归档）
- `docs/03-engineering-governance/work-log.md`: +1 index row

- [ ] **Step 5: 跑全套测试 + 质量门禁**

```bash
cd packages/server-python
pytest tests/ -v -W error 2>&1 | tail -5
python -m ruff check app/ tests/
python3 scripts/check-engineering-docs
```

Expected: all green, ruff 0, docs 0

- [ ] **Step 6: Commit + Push + PR**

```bash
git add -A
git commit -m "feat: REQ-056 实施完成 (5 Task — 3 个生产缺口关闭 + 10 真实样例 + AC-7 端到端)"
git push -u origin feat/req-056-impl
gh pr create --base main --head feat/req-056-impl \
  --title "feat: REQ-056 智能问数真实执行闭环 (5 Task + 10 真实业务样例)"
gh pr merge --squash --delete-branch
```

---

## Self-Review

After completing all 5 tasks, verify:

1. **AC-1**: ImportedDatasetAdapter 通过 JsonbQueryBuilder 执行过滤/时间范围/limit
2. **AC-2**: 过滤后结果与无过滤不同 (DB 集成测试)
3. **AC-3**: /ai/chat/evidence 注入 request-bound QueryService + 真实 user_id
4. **AC-4**: AI Chat 按 (catalog_id, entity_type) 双键路由
5. **AC-5**: 审计失败 fail-closed (异常时不返回结果)
6. **AC-6**: 10 个真实业务样例全绿
7. **AC-7**: 真实 API + AI Chat 端到端有证据
8. **AC-8**: 文档状态一致（REQ-052 重新 Done + REQ-056 Done）

---

## Verification

End-to-end verification:

```bash
# 1. 全套测试
cd packages/server-python
pytest tests/ -v -W error

# 2. 真实 dev DB 跑 10 个样例
pytest tests/real_world/req056_business_samples.py -v

# 3. 端到端 curl (需 dev.sh 启动)
./dev.sh && ./dev.sh init-db
# ... 端到端命令（Task 5 Step 3）

# 4. 质量门禁
ruff check && python3 scripts/check-engineering-docs
```

---

## Execution Handoff

Plan complete and saved to `docs/02-delivery-plans/02-plans/2026-07-16-req-056-intelligent-data-query-production-closure.md`. 5 tasks, estimated 3-5 subagent rounds.

**Two execution options:**

1. **Subagent-Driven (recommended)** - Fresh subagent per task + review between tasks
2. **Inline Execution** - Execute in this session using executing-plans

Which approach?
