"""Unit tests for SubjectResolver + DdTaskService (REQ-046 Slice 1, AC-1).

Covers the subject-anchoring flow with a fake MCP invocation service and an
in-memory task repository (no DB, no HTTP):

- resolve: 简称/品牌名 -> QCC ``get_company_by_query`` -> candidate list; full
  registered name / credit code short-circuits to a single high-confidence
  candidate; no-match returns empty (user must refine keywords).
- resolve never returns raw subject to any audit surface (digests only happen
  inside the MCP invocation layer — out of scope here).
- confirm: records the chosen candidate and advances the task to
  subject_confirmed (tenant-isolated).
- AC-1: the resolver only *queries* the anchoring tool; risk/shareholder
  tools are never reachable here (the runner gate is tested separately).
"""
from __future__ import annotations

import uuid

import pytest

from app.contexts.due_diligence.application.dd_task_service import (
    DdTaskNotFoundError,
    DdTaskService,
)
from app.contexts.due_diligence.application.subject_resolver import (
    SubjectResolver,
)
from app.contexts.due_diligence.domain.dd_task import DdTask
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationError,
)


class _FakeInvocation:
    """Records calls; returns scripted results keyed by tool_name."""

    def __init__(self, results: dict[str, object]) -> None:
        self._results = results
        self.calls: list[dict] = []

    async def invoke(self, *, tenant_id, server_code, tool_name, params, caller):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "server_code": server_code,
                "tool_name": tool_name,
                "params": params,
                "caller": caller,
            }
        )
        result = self._results.get(tool_name)
        if isinstance(result, Exception):
            raise result
        return result or {}


class _InMemoryTaskRepo:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, DdTask] = {}

    async def create(self, task: DdTask) -> DdTask:
        self._rows[task.id] = task
        return task

    async def get_by_id(self, tenant_id, task_id):
        task = self._rows.get(task_id)
        return task if task and task.tenant_id == tenant_id else None

    async def list_by_tenant(self, tenant_id):
        return [t for t in self._rows.values() if t.tenant_id == tenant_id]

    async def save(self, task: DdTask) -> DdTask:
        self._rows[task.id] = task
        return task


def _caller(role: str = "admin") -> InvocationCaller:
    return InvocationCaller(caller_type="http_api", role=role, user_id=uuid.uuid4())


def _service(invocation) -> DdTaskService:
    repo = _InMemoryTaskRepo()
    resolver = SubjectResolver(invocation)
    return DdTaskService(repo, resolver)


# ---- resolve: 候选主体锚定 ----


@pytest.mark.asyncio
async def test_resolve_short_name_returns_candidates():
    # 真实 QCC 契约：返回 content[0].text 为 JSON，企业数组在 企业信息，
    # 字段 企业名称 / 统一社会信用代码。
    import json as _json

    inner = {
        "企业信息": [
            {"企业名称": "阿里巴巴(中国)有限公司", "统一社会信用代码": "91A"},
            {"企业名称": "阿里巴巴网络技术有限公司", "统一社会信用代码": "91B"},
        ]
    }
    invocation = _FakeInvocation(
        {
            "get_company_by_query": {
                "content": [{"type": "text", "text": _json.dumps(inner, ensure_ascii=False)}]
            }
        }
    )
    service = _service(invocation)
    tenant_id = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_id, title="背调", subject_query="阿里巴巴", by=uuid.uuid4()
    )
    candidates = await service.resolve_subject(
        tenant_id=tenant_id, task_id=task.id, caller=_caller()
    )
    assert [c.company_name for c in candidates] == [
        "阿里巴巴(中国)有限公司",
        "阿里巴巴网络技术有限公司",
    ]
    assert [c.credit_code for c in candidates] == ["91A", "91B"]
    # 调用了 qcc 锚定工具,按真实 QCC 契约传 searchKey
    assert invocation.calls[0]["tool_name"] == "get_company_by_query"
    assert invocation.calls[0]["params"] == {"searchKey": "阿里巴巴"}
    assert invocation.calls[0]["server_code"] == "qcc"


@pytest.mark.asyncio
async def test_resolve_no_match_returns_empty():
    import json as _json

    inner = {"企业信息": []}
    invocation = _FakeInvocation(
        {
            "get_company_by_query": {
                "content": [{"type": "text", "text": _json.dumps(inner, ensure_ascii=False)}]
            }
        }
    )
    service = _service(invocation)
    tenant_id = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_id, title="背调", subject_query="不存在公司xyz", by=uuid.uuid4()
    )
    candidates = await service.resolve_subject(
        tenant_id=tenant_id, task_id=task.id, caller=_caller()
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_resolve_propagates_invocation_error():
    invocation = _FakeInvocation(
        {"get_company_by_query": MCPInvocationError("tool_error", "qcc 失败")}
    )
    service = _service(invocation)
    tenant_id = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_id, title="背调", subject_query="x", by=uuid.uuid4()
    )
    with pytest.raises(MCPInvocationError):
        await service.resolve_subject(
            tenant_id=tenant_id, task_id=task.id, caller=_caller()
        )


# ---- confirm: 确认候选 -> subject_confirmed ----


@pytest.mark.asyncio
async def test_confirm_subject_advances_state():
    invocation = _FakeInvocation({})
    service = _service(invocation)
    tenant_id = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_id, title="背调", subject_query="阿里巴巴", by=uuid.uuid4()
    )
    confirmed = await service.confirm_subject(
        tenant_id=tenant_id,
        task_id=task.id,
        company_name="阿里巴巴(中国)有限公司",
        credit_code="91A",
        by=uuid.uuid4(),
    )
    assert confirmed.status == "subject_confirmed"
    assert confirmed.confirmed_subject == {
        "company_name": "阿里巴巴(中国)有限公司",
        "credit_code": "91A",
    }


@pytest.mark.asyncio
async def test_confirm_requires_existing_task_in_tenant():
    invocation = _FakeInvocation({})
    service = _service(invocation)
    with pytest.raises(DdTaskNotFoundError):
        await service.confirm_subject(
            tenant_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            company_name="x",
            credit_code=None,
            by=uuid.uuid4(),
        )


# ---- 任务容器 CRUD + 租户隔离 ----


@pytest.mark.asyncio
async def test_create_and_get_task():
    invocation = _FakeInvocation({})
    service = _service(invocation)
    tenant_id = uuid.uuid4()
    by = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_id, title="园区入驻背调", subject_query="某企业", by=by
    )
    assert task.status == "subject_pending"
    assert task.created_by == by
    fetched = await service.get_task(tenant_id=tenant_id, task_id=task.id)
    assert fetched.id == task.id


@pytest.mark.asyncio
async def test_tenant_isolation():
    invocation = _FakeInvocation({})
    service = _service(invocation)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    task = await service.create_task(
        tenant_id=tenant_a, title="背调", subject_query="某企业", by=uuid.uuid4()
    )
    with pytest.raises(DdTaskNotFoundError):
        await service.get_task(tenant_id=tenant_b, task_id=task.id)
    listed_b = await service.list_tasks(tenant_id=tenant_b)
    assert listed_b == []
