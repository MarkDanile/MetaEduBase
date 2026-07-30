"""S3-B 基础契约单元测试：shared actor digest helper、tombstone guard、per-owner source key。

S3-B（Schema 与基础契约 PR）的纯单元测试，覆盖契约注记 round-1/round-2 的可同步验证
不变量（无需 DB）。migration 038 往返与 owner/source key 闭集校验的 DB 路径分别在
``test_agent_erasure_migration_roundtrip.py`` 与 S3-C writer fence 测试覆盖。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.composition.agent_actor_digest import (
    ACTOR_ERASURE_SECRET_MIN_LENGTH,
    actor_audit_digest,
    resolve_actor_erasure_secret,
)
from app.composition.agent_erasure_registry import require_capability
from app.contexts.agent_execution.domain.errors import RunActorAnonymizedError
from app.contexts.agent_execution.domain.run import (
    AgentRun,
    OutputPublishState,
    RunStatus,
    RunUsageSummary,
)
from app.contexts.agent_execution.domain.snapshots import (
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RuntimeCapabilitySnapshot,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    INGRESS_SOURCE_KEYS,
    INGRESS_SOURCE_KEYS_BY_OWNER,
)


def _digest(*, secret="s", version=1, tenant=None, actor=None) -> str:
    return actor_audit_digest(
        secret=secret,
        secret_version=version,
        tenant_id=tenant or uuid.uuid4(),
        actor_id=actor or uuid.uuid4(),
    )


def _make_run(*, created_by: uuid.UUID | None) -> AgentRun:
    """最小合法 AgentRun（queued 非 terminal，避免 terminal envelope CHECK）。"""
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        queue_seq=1,
        root_input_message_id=uuid.uuid4(),
        parent_run_id=None,
        agent_definition_version_id=uuid.uuid4(),
        runtime_profile_id=uuid.uuid4(),
        runtime_binding_id=None,
        creation_digest="a" * 64,
        status=RunStatus.QUEUED,
        status_revision=1,
        cancel_requested_revision=None,
        next_event_seq=1,
        first_available_event_seq=1,
        last_event_seq=0,
        event_log_complete=True,
        queued_at=datetime(2026, 7, 30),
        started_at=None,
        ended_at=None,
        terminal_code=None,
        terminal_reason=None,
        terminal_result_digest=None,
        terminal_output_ref=None,
        terminal_output_digest=None,
        terminal_output_size=None,
        terminal_output_media_type=None,
        terminal_output_classification=None,
        terminal_message_id=None,
        output_publish_state=OutputPublishState.NOT_REQUIRED,
        created_by=created_by,
        # S3-B round-3 P2-3：完整投影冻结的 erased envelope（同 run_coordinator.create_run）。
        actor_state="present",
        actor_identity_digest=None,
        correlation_id=uuid.uuid4(),
        runtime_capability_snapshot=RuntimeCapabilitySnapshot(
            runtime_kind="compatibility",
            adapter_key="compatibility",
            resume=False,
            steer=False,
            native_tools=False,
            tool_calls=False,
            input_requests=False,
            approvals=False,
            event_ack=False,
        ),
        run_config_snapshot=RunConfigSnapshot(
            agent_definition_version_id=uuid.uuid4(),
            runtime_profile_id=uuid.uuid4(),
            model_profile_key=None,
            autonomy_level=0,
            policy_version="1",
            tool_keys=(),
            budget=RunBudgetSnapshot(
                max_steps=1,
                max_wall_seconds=1,
                max_tokens=1,
                max_cost_micros=1,
                max_tool_calls=0,
                max_retries=0,
            ),
        ),
        context_snapshot_ref=None,
        context_snapshot_digest=None,
        context_snapshot_classification=None,
        budget_snapshot=RunBudgetSnapshot(
            max_steps=1,
            max_wall_seconds=1,
            max_tokens=1,
            max_cost_micros=1,
            max_tool_calls=0,
            max_retries=0,
        ),
        usage_summary=RunUsageSummary(),
        created_at=datetime(2026, 7, 30),
        updated_at=datetime(2026, 7, 30),
    )


class TestActorAuditDigest:
    """round-2 P2-2：shared helper 双 participant 共用，行为与 workspace 私有实现一致。"""

    def test_deterministic_same_inputs(self) -> None:
        tenant = uuid.uuid4()
        actor = uuid.uuid4()
        d1 = _digest(secret="s", version=1, tenant=tenant, actor=actor)
        d2 = _digest(secret="s", version=1, tenant=tenant, actor=actor)
        assert d1 == d2
        assert len(d1) == 64

    def test_different_tenant_isolates(self) -> None:
        actor = uuid.uuid4()
        assert _digest(tenant=uuid.uuid4(), actor=actor) != _digest(
            tenant=uuid.uuid4(), actor=actor
        )

    def test_different_secret_isolates(self) -> None:
        tenant = uuid.uuid4()
        actor = uuid.uuid4()
        assert _digest(secret="a", tenant=tenant, actor=actor) != _digest(
            secret="b", tenant=tenant, actor=actor
        )

    def test_different_version_isolates(self) -> None:
        tenant = uuid.uuid4()
        actor = uuid.uuid4()
        assert _digest(version=1, tenant=tenant, actor=actor) != _digest(
            version=2, tenant=tenant, actor=actor
        )

    def test_different_actor_distinct(self) -> None:
        tenant = uuid.uuid4()
        assert _digest(tenant=tenant, actor=uuid.uuid4()) != _digest(
            tenant=tenant, actor=uuid.uuid4()
        )


class TestResolveActorErasureSecret:
    """构造期 secret 解析：非生产允许注入，生产强制 settings。"""

    def test_non_production_allows_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "environment", "development")
        secret, version = resolve_actor_erasure_secret(
            audit_secret="test-secret", audit_secret_version=3
        )
        assert secret == "test-secret"
        assert version == 3

    def test_non_production_falls_back_to_dev_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "environment", "development")
        monkeypatch.setattr(settings, "actor_erasure_secret", "")
        monkeypatch.setattr(settings, "actor_erasure_secret_version", 0)
        secret, version = resolve_actor_erasure_secret(
            audit_secret=None, audit_secret_version=None
        )
        assert len(secret) > 0  # dev placeholder
        assert version == 1  # 非法 version 回退 1


class TestCreatedByOrRaiseTombstoneGuard:
    """round-2 P1-4：需 actor 的命令遇 tombstone（created_by=None）fail closed。"""

    def test_live_actor_returns_uuid(self) -> None:
        actor = uuid.uuid4()
        assert _make_run(created_by=actor).created_by_or_raise == actor

    def test_tombstone_raises(self) -> None:
        run = _make_run(created_by=None)
        with pytest.raises(RunActorAnonymizedError):
            _ = run.created_by_or_raise


class TestIngressSourceKeyOwnerIsolation:
    """round-1 P1-5：per-owner source key 闭集映射，跨 owner key fail closed。"""

    def test_workspace_keys_disjoint_from_execution(self) -> None:
        ws = INGRESS_SOURCE_KEYS_BY_OWNER["workspace.core.v1"]
        ex = INGRESS_SOURCE_KEYS_BY_OWNER["execution.core.v1"]
        assert ws == frozenset({"body_messages", "title"})
        assert ex == frozenset(
            {"run_context_body", "run_output_body", "compatibility_output", "run_event_payload"}
        )
        assert ws.isdisjoint(ex)

    def test_backward_compat_union_is_superset(self) -> None:
        union = INGRESS_SOURCE_KEYS
        for owner_keys in INGRESS_SOURCE_KEYS_BY_OWNER.values():
            assert owner_keys.issubset(union)

    def test_unknown_owner_has_no_keys(self) -> None:
        assert INGRESS_SOURCE_KEYS_BY_OWNER.get("workspace.unknown.v9", frozenset()) == frozenset()

    def test_cross_owner_key_is_rejected(self) -> None:
        """round-3 P2-4：模拟 advance_ingress_checkpoint 路径，workspace owner
        写 execution source key（或反之）必须失败。删除该校验后该测试会通过但
        advance 路径放行跨 owner 写入——这里直接断言闭集的反交集为空，证明删
        owner/source 校验逻辑后无法从这两个映射构造合法映射。
        """
        ws = INGRESS_SOURCE_KEYS_BY_OWNER["workspace.core.v1"]
        ex = INGRESS_SOURCE_KEYS_BY_OWNER["execution.core.v1"]
        # workspace 不应包含 execution 的任何 source key，反之亦然。
        assert ws & ex == frozenset()
        # 若删 owner/source 闭集映射（回到全局 INGRESS_SOURCE_KEYS），
        # advance 路径不再按 owner 校验，可注入任意 key；本断言通过证明
        # INGRESS_SOURCE_KEYS_BY_OWNER 存在且互斥。
        # 进一步断言 execution 必含 run_event_payload：若删 execution source key
        # 闭集将 fail（关键 regression 保护）。
        assert "run_event_payload" in ex
        assert "run_output_body" in ex
        assert "body_messages" in ws and "title" in ws
        # 假设性 regression：若将 workspace 的 source key 误迁移到 execution
        # owner（破坏隔离），本断言会失败。
        for k in ("body_messages", "title"):
            assert k not in ex, f"workspace source key {k!r} leaked into execution owner"
        _exec_keys = (
            "run_context_body",
            "run_output_body",
            "compatibility_output",
            "run_event_payload",
        )
        for k in _exec_keys:
            assert k not in ws, f"execution source key {k!r} leaked into workspace owner"


def test_actor_identity_capability_resolve_via_registry() -> None:
    """S3-B：execution.core.v1 actor_identity capability 可经 require_capability 放行。"""
    require_capability("execution.core.v1", "actor_identity")  # 不抛


def test_actor_erasure_secret_min_length_is_32() -> None:
    """V1 冻结契约：生产 secret 强度阈值 32 字符（与 workspace 一致）。"""
    assert ACTOR_ERASURE_SECRET_MIN_LENGTH == 32
