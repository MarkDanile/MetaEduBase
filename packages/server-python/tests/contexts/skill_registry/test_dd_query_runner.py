"""DD internal-query runner adapter (REQ-046 PR-5 / Slice 4).

The SkillRunner ``internal_query`` step channel needs a production
``query_runner`` that resolves the active semantic model and delegates to the
REQ-052 ``QueryService``. This pins the adapter contract:
- resolves the active semantic model for ``(tenant, entity_type)`` in the
  configured single DD catalog (settings ``dd_internal_query_catalog_id``).
- ambiguous (multiple active) or missing catalog -> fail-closed (never query
  the wrong dataset).
- missing semantic model -> ``ok=False`` (runner surfaces a tool_error).
- success -> the runner-facing dict carries a real ``audit_id`` (AC-4/AC-6).
All collaborators mocked — no DB, no LLM, no network.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.contexts.skill_registry.application import dd_query_runner as mod

pytestmark = pytest.mark.asyncio


def _semantic_model(entity_type: str = "bill"):
    sm = MagicMock()
    sm.entity_type = entity_type
    sm.version = "v1"
    sm.dataset_id = uuid.uuid4()
    sm.data_source_config = {"type": "imported_dataset"}
    return sm


def _patch_repo(monkeypatch, *, models=None, raise_exc=None):
    repo = MagicMock()
    if raise_exc is not None:
        repo.get_active_by_catalog_and_entity_type = AsyncMock(side_effect=raise_exc)
    else:
        repo.get_active_by_catalog_and_entity_type = AsyncMock(
            side_effect=lambda **kw: models.get(kw["entity_type"])
        )
    monkeypatch.setattr(mod, "SemanticModelRepository", MagicMock(return_value=repo))
    return repo


def _query_service(result):
    qs = MagicMock()
    bound = MagicMock()
    bound.ask = AsyncMock(return_value=result)
    qs.with_session = MagicMock(return_value=bound)
    return qs, bound


def _make(monkeypatch, *, catalog_id: str | None = None, query_result=None, models=None):
    cid = catalog_id if catalog_id is not None else str(uuid.uuid4())
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", cid)
    repo = _patch_repo(monkeypatch, models=models or {})
    qs, bound = _query_service(query_result or {"ok": True, "audit_id": uuid.uuid4()})
    # 默认主体可解析出一个 客户ID,使既有"成功路径"用例成立。
    session = _scalar_session("CUST-001")
    runner = mod.build_dd_internal_query_runner(qs, session)
    return runner, repo, bound


async def test_resolves_model_in_configured_catalog_and_runs(monkeypatch):
    sm = _semantic_model("bill")
    customer = _customer_model()
    runner, repo, bound = _make(
        monkeypatch,
        query_result={"ok": True, "audit_id": uuid.uuid4()},
        models={"bill": sm, "customer": customer},
    )
    # 主体可解析(客户ID)才会真正问数 — AC-8 单企业语义。
    out = await runner(
        question="ACME 欠费", entity_type="bill", subject={"company_name": "ACME"},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    assert isinstance(out["audit_id"], uuid.UUID)
    # repo queried with the configured catalog + entity_type
    entity_types = [
        c.kwargs["entity_type"]
        for c in repo.get_active_by_catalog_and_entity_type.await_args_list
    ]
    assert "bill" in entity_types and "customer" in entity_types
    bound.ask.assert_awaited_once()


async def test_missing_semantic_model_returns_ok_false(monkeypatch):
    runner, _, bound = _make(monkeypatch, models={})
    out = await runner(
        question="q", entity_type="bill", subject={}, caller=MagicMock(role="admin"),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is False
    assert "audit_id" not in out or out.get("audit_id") is None
    bound.ask.assert_not_awaited()


async def test_ambiguous_semantic_model_fails_closed(monkeypatch):
    """Multiple active models for (catalog, entity_type) -> raise, never query."""
    runner, repo, _ = _make(monkeypatch)
    repo.get_active_by_catalog_and_entity_type = AsyncMock(
        side_effect=Exception("MultipleResultsFound")
    )
    with pytest.raises(Exception, match="MultipleResultsFound"):
        await runner(
            question="q", entity_type="bill", subject={}, caller=MagicMock(role="admin"),
            tenant_id=uuid.uuid4(),
        )


async def test_missing_catalog_config_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", "")
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    runner = mod.build_dd_internal_query_runner(qs, MagicMock())
    with pytest.raises(RuntimeError, match="DD_INTERNAL_QUERY_CATALOG_ID"):
        await runner(
            question="q", entity_type="bill", subject={}, caller=MagicMock(role="admin"),
            tenant_id=uuid.uuid4(),
        )
    bound.ask.assert_not_awaited()


# ---------------------------------------------------------------------------
# REQ-046 AC-8: 主体 -> 关系键过滤(中文数据集无 company_name 列)
# ---------------------------------------------------------------------------


def _scalar_session(value):
    """Session stub whose ``scalar`` returns ``value`` (subject 客户ID lookup)."""
    session = MagicMock()
    session.scalar = AsyncMock(return_value=value)
    session.scalars = AsyncMock(return_value=_ScalarResult([]))
    session.execute = AsyncMock(return_value=_ExecResult([]))
    return session


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecResult(_ScalarResult):
    """``session.execute`` result stub — ``.all()`` yields row tuples."""


def _customer_model():
    sm = _semantic_model("customer")
    sm.dataset_id = uuid.uuid4()
    return sm


async def test_bill_scopes_by_resolved_customer_id(monkeypatch):
    """bill 有 客户ID 列:解析主体 -> confirmed_filters 强制 eq 过滤。"""
    customer = _customer_model()
    bill = _semantic_model("bill")
    bill.dataset_id = uuid.uuid4()
    models = {"customer": customer, "bill": bill}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = _scalar_session("CUST-001")
    repo = _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="欠费", entity_type="bill",
        subject={"company_name": "上汽集团", "credit_code": None},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    # customer 语义模型被解析用于主体查找
    entity_types = [
        c.kwargs["entity_type"]
        for c in repo.get_active_by_catalog_and_entity_type.await_args_list
    ]
    assert "customer" in entity_types and "bill" in entity_types
    # ask 收到 客户ID 强制过滤
    ask_kwargs = bound.ask.await_args.kwargs
    assert ask_kwargs["confirmed_filters"] == {
        "客户ID": {"op": "eq", "value": "CUST-001"}
    }


async def test_lease_term_scopes_by_contract_ids_via_contract(monkeypatch):
    """lease_term 无 客户ID:客户ID -> 合同ID(经 contract) -> in 过滤。"""
    customer = _customer_model()
    contract = _semantic_model("contract")
    contract.dataset_id = uuid.uuid4()
    lease = _semantic_model("lease_term")
    lease.dataset_id = uuid.uuid4()
    models = {"customer": customer, "contract": contract, "lease_term": lease}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = MagicMock()
    # scalar: customer -> 客户ID;scalars: contract -> 合同ID 列表
    session.scalar = AsyncMock(return_value="CUST-001")
    session.scalars = AsyncMock(return_value=_ScalarResult(["HT-1", "HT-2"]))
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="租约到期", entity_type="lease_term",
        subject={"company_name": "上汽集团", "credit_code": None},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    ask_kwargs = bound.ask.await_args.kwargs
    assert ask_kwargs["confirmed_filters"] == {
        "合同ID": {"op": "in", "value": ["HT-1", "HT-2"]}
    }


async def test_unresolvable_subject_fails_closed(monkeypatch):
    """customer 数据集查不到主体 -> ok=False,绝不过滤落空查全表。"""
    customer = _customer_model()
    bill = _semantic_model("bill")
    models = {"customer": customer, "bill": bill}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = _scalar_session(None)  # 主体解析不到 客户ID
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="欠费", entity_type="bill",
        subject={"company_name": "不存在公司", "credit_code": None},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is False
    bound.ask.assert_not_awaited()


async def test_no_matching_contracts_fails_closed(monkeypatch):
    """主体存在但无任何合同 -> lease_term ok=False(不查全园区租约)。"""
    customer = _customer_model()
    contract = _semantic_model("contract")
    lease = _semantic_model("lease_term")
    models = {"customer": customer, "contract": contract, "lease_term": lease}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = MagicMock()
    session.scalar = AsyncMock(return_value="CUST-001")
    session.scalars = AsyncMock(return_value=_ScalarResult([]))  # 无合同
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="租约到期", entity_type="lease_term",
        subject={"company_name": "上汽集团", "credit_code": None},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is False
    bound.ask.assert_not_awaited()


async def test_exact_name_hit_skips_fuzzy(monkeypatch):
    """信用代码未中但注册名精确命中 -> 用该 客户ID,不再 fuzzy。"""
    customer = _customer_model()
    bill = _semantic_model("bill")
    bill.dataset_id = uuid.uuid4()
    models = {"customer": customer, "bill": bill}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = MagicMock()
    # scalar:#1 credit code -> None;#2 exact name -> 命中
    session.scalar = AsyncMock(side_effect=[None, "CU0329"])
    session.scalars = AsyncMock(return_value=_ScalarResult([]))
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="欠费", entity_type="bill",
        subject={"company_name": "上海汽车集团股份有限公司", "credit_code": "91310000132260250X"},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    ask_kwargs = bound.ask.await_args.kwargs
    assert ask_kwargs["confirmed_filters"] == {"客户ID": {"op": "eq", "value": "CU0329"}}


async def test_unique_fuzzy_name_hit_resolves(monkeypatch):
    """精确名未中,fuzzy 唯一命中 -> 用该 客户ID。"""
    customer = _customer_model()
    bill = _semantic_model("bill")
    bill.dataset_id = uuid.uuid4()
    models = {"customer": customer, "bill": bill}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = MagicMock()
    # scalar:#1 credit -> None,#2 exact -> None;execute fuzzy -> 唯一候选
    session.scalar = AsyncMock(side_effect=[None, None])
    session.execute = AsyncMock(return_value=_ExecResult([("CU0343", "上汽集团股份有限公司")]))
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="欠费", entity_type="bill",
        subject={"company_name": "上海汽车集团股份有限公司", "credit_code": "91310000132260250X"},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    ask_kwargs = bound.ask.await_args.kwargs
    assert ask_kwargs["confirmed_filters"] == {"客户ID": {"op": "eq", "value": "CU0343"}}


async def test_ambiguous_fuzzy_fails_closed(monkeypatch):
    """fuzzy 多个不同 客户ID -> fail-closed(不猜主体)。"""
    customer = _customer_model()
    bill = _semantic_model("bill")
    models = {"customer": customer, "bill": bill}
    qs, bound = _query_service({"ok": True, "audit_id": uuid.uuid4()})
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[None, None])
    session.execute = AsyncMock(return_value=_ExecResult(
        [("CU0329", "上海汽车集团股份有限公司"), ("CU0343", "上汽集团股份有限公司")]
    ))
    _patch_repo(monkeypatch, models=models)
    monkeypatch.setattr(settings, "dd_internal_query_catalog_id", str(uuid.uuid4()))
    runner = mod.build_dd_internal_query_runner(qs, session)

    out = await runner(
        question="欠费", entity_type="bill",
        subject={"company_name": "上海汽车集团股份有限公司", "credit_code": "91310000132260250X"},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is False
    bound.ask.assert_not_awaited()
