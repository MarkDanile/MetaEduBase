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
    session = MagicMock()
    runner = mod.build_dd_internal_query_runner(qs, session)
    return runner, repo, bound


async def test_resolves_model_in_configured_catalog_and_runs(monkeypatch):
    sm = _semantic_model("bill")
    runner, repo, bound = _make(
        monkeypatch, query_result={"ok": True, "audit_id": uuid.uuid4()}, models={"bill": sm}
    )
    out = await runner(
        question="ACME 欠费", entity_type="bill", subject={"company_name": "ACME"},
        caller=MagicMock(role="admin", user_id=uuid.uuid4()),
        tenant_id=uuid.uuid4(),
    )
    assert out["ok"] is True
    assert isinstance(out["audit_id"], uuid.UUID)
    # repo queried with the configured catalog + entity_type
    kw = repo.get_active_by_catalog_and_entity_type.await_args.kwargs
    assert uuid.UUID(kw["catalog_id"].hex) == uuid.UUID(settings.dd_internal_query_catalog_id)
    assert kw["entity_type"] == "bill"
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
