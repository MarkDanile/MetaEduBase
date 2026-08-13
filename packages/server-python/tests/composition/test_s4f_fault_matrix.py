"""R1-S4-F：S4 阶段 fault 矩阵新增反例测试（F-6 十一项 + F-4 互操作）。

契约事实源：Plan §R1-S4-F F-0~F-7（PR #559 契约冻结）+ S4-E E-6 已覆盖清单。

本文件只补 S4-F **新增**反例（F-1 标注「需新增 / 族 B」）；已由 E-6 冻结并实现的
故障点**不在本文件重复实现**——迟到 runtime write + 旧 producer revision（F-6 行
10/11）由既有 S4-E-C/S4-C 套件承载，本 PR 通过全 composition 回归做互操作确认。

**生产修复（同 commit 最小改动，镜像 runtime E-C 先例）**：
- ``external_ref_erasure_participant`` Tx2 起点 ``expire_all()``——跨进程 takeover
  可观测（F-6「external 跨进程 takeover」）。
- ``external_ref_erasure_participant`` / ``transport_erasure_participant``
  erased-fence 重放加 ``fence.purge_revision == purge_revision`` 门禁（F-6「跨
  purge 实例 erased-fence 重放」）。

反例 → 判别点映射：
- 跨 tenant 伪造 ACK / owner scope mismatch / operation revision 重放（R1-AC9）。
- 跨 purge 实例 erased-fence 重放（族 B，external + transport 各一）。
- external 跨进程 takeover（族 B，真实双连接 + expire_all 判别）。
- 跨 Conversation 同一 object 双删（幂等重放 adapter，distinct delete==1）。
- 混合多族故障五方一致 + partial ACK 负向（F-4/D6）。
- 日志/operation/checkpoint 脱敏（R1-AC10）。

故障场景全部真实 PostgreSQL（spec §6 全局验证命令；SQLite/mock 只覆盖纯状态转换）。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.agent_erasure_registry import OwnerDefinition
from app.composition.external_object_adapter import ExternalEraseSuccess
from app.composition.runtime_erasure_participant import RUNTIME_PRIVATE_OWNER
from app.contexts.agent_workspace.domain import PurgeOperationState, PurgeOwnerState
from app.contexts.agent_workspace.infrastructure.workspace_transport_erasure_participant import (
    WorkspaceTransportErasureParticipant,
)
from tests.composition.test_s4da_transport_participant_matrix import (
    _make_purge_operation as _transport_make_purge_operation,
)

# --- 复用已合并测试 helper（禁止重复实现已有覆盖）------------------------------
from tests.composition.test_s4da_transport_participant_matrix import (
    _seed_deleted_expired_conversation as _transport_seed_conversation,
)
from tests.composition.test_s4da_transport_participant_matrix import (
    _seed_transport_outbox,
)
from tests.composition.test_s4eb2_external_erasure import (
    EXTERNAL_PAYLOAD_OWNER,
    TENANT_ID,
    _ensure_test_tenant,
    _seed_external_ledger_ref,
    _seed_workspace_outbox_ref,
)
from tests.composition.test_s4eb2_external_erasure import (
    _make_purge_operation as _ext_make_purge_operation,
)
from tests.composition.test_s4eb2_external_erasure import (
    _participant as _ext_participant,
)
from tests.composition.test_s4eb2_external_erasure import (
    _seed_deleted_expired_conversation as _ext_seed_conversation,
)
from tests.composition.test_s4eb2_external_erasure import (
    _SuccessAdapter as _ExternalSuccessAdapter,
)
from tests.composition.test_s4eb2_external_erasure import (
    _TimeoutAdapter as _ExternalTimeoutAdapter,
)
from tests.composition.test_s4ec_runtime_conformance import (
    _FailedAdapter as _RuntimeFailedAdapter,
)
from tests.composition.test_s4ec_runtime_conformance import (
    _make_purge_operation as _runtime_make_purge_operation,
)
from tests.composition.test_s4ec_runtime_conformance import (
    _participant as _runtime_participant,
)
from tests.composition.test_s4ec_runtime_conformance import (
    _seed_runtime_binding,
)
from tests.composition.test_s4ec_runtime_conformance import (
    _TimeoutAdapter as _RuntimeTimeoutAdapter,
)
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio

_REF_VALUE = "obj://staging/object/s4f"
_RUNTIME_REF = "pi://session/s4f"
WORKSPACE_TRANSPORT_OWNER = "workspace.transport.v1"

# F-6 R1-AC10 脱敏 sentinel（批次 C 契约重写）：external ref 是 ledger 必要身份
# 例外（可判别——ref_value 保留）；正文/runtime ref 是可判别 sentinel（真实种入源
# 数据，不得流入 operation/checkpoint/fence）。CoT/secret 结构性不可达（spec §9.3
# 不落库）、日志结构性无（S4 无 logger），不做 caplog/sentinel 假判别。
_BODY_SENTINEL = "BODY_SECRET_MARKER_9f8a7b6c"
_EXTERNAL_REF_SENTINEL = "obj://staging/sentinel-ext-ref-4d2e"
_RUNTIME_REF_SENTINEL = "pi://session/sentinel-runtime-7c3f"


def _enable_external_registry(monkeypatch) -> None:
    """external.payload.v1 临时翻 True 验证 erase 主体（E-4 registry 断言分离）。

    生产 registry 保持 False；本 helper 是现有 ``_external_registry_enabled``
    （yield fixture，不能直接调用）的无 yield 副本，测试作用域内 monkeypatch 生效。
    """
    import app.composition.agent_erasure_registry as registry_module

    originals = registry_module._OWNER_DEFINITIONS

    def _enable(owner: OwnerDefinition):
        if owner.owner_key == EXTERNAL_PAYLOAD_OWNER:
            return OwnerDefinition(
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                capabilities=owner.capabilities,
                erase_available=True,
            )
        return owner

    enabled = tuple(_enable(o) for o in originals)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(
        registry_module, "_OWNERS_BY_KEY", {o.owner_key: o for o in enabled}
    )


def _enable_runtime_registry(monkeypatch) -> None:
    """runtime.private.v1 临时翻 True（同上，镜像 ``_runtime_registry_enabled``）。"""
    import app.composition.agent_erasure_registry as registry_module

    originals = registry_module._OWNER_DEFINITIONS

    def _enable(owner: OwnerDefinition):
        if owner.owner_key == RUNTIME_PRIVATE_OWNER:
            return OwnerDefinition(
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                capabilities=owner.capabilities,
                erase_available=True,
            )
        return owner

    enabled = tuple(_enable(o) for o in originals)
    monkeypatch.setattr(registry_module, "_OWNER_DEFINITIONS", enabled)
    monkeypatch.setattr(
        registry_module, "_OWNERS_BY_KEY", {o.owner_key: o for o in enabled}
    )


async def _make_factory():
    """独立 session_factory（并发 / 测试体内 commit / rollback 时机自控）。"""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory, engine


async def _seed_second_tenant(session: AsyncSession) -> uuid.UUID:
    """第二个 tenant（跨 tenant 反例用）。"""
    tenant_b = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, 'shared', true, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": tenant_b,
            "name": "s4f-tenant-b",
            "school_name": "s4f school b",
            "now": now,
        },
    )
    await session.flush()
    return tenant_b


async def _seed_erased_external_fence(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    purge_revision: int,
) -> None:
    """把 external fence 置为 erased + 指定 purge_revision（模拟旧 purge 实例终态）。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences "
            "SET state = 'erased', purge_revision = :r, ack_digest = :ad, "
            "  acked_at = :now, revision = revision + 1, updated_at = :now "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {
            "t": tenant_id,
            "c": conversation_id,
            "o": EXTERNAL_PAYLOAD_OWNER,
            "r": purge_revision,
            "ad": "d" * 64,
            "now": now,
        },
    )
    assert cast(CursorResult, result).rowcount == 1, "external fence must exist to set erased"


async def _seed_erasing_external_fence(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    purge_revision: int,
) -> None:
    """把 external fence 置为 erasing + 指定 purge_revision（模拟 op1 中段）。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences "
            "SET state = 'erasing', purge_revision = :r, "
            "  revision = revision + 1, updated_at = :now "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {
            "t": tenant_id,
            "c": conversation_id,
            "o": EXTERNAL_PAYLOAD_OWNER,
            "r": purge_revision,
            "now": now,
        },
    )
    assert cast(CursorResult, result).rowcount == 1, "external fence must exist to set erasing"


async def _seed_erased_transport_fence(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner: str,
    purge_revision: int,
) -> None:
    """把 transport fence 置为 erased + 指定 purge_revision（旧 purge 实例终态）。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences "
            "SET state = 'erased', purge_revision = :r, ack_digest = :ad, "
            "  acked_at = :now, revision = revision + 1, updated_at = :now "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {
            "t": tenant_id,
            "c": conversation_id,
            "o": owner,
            "r": purge_revision,
            "ad": "d" * 64,
            "now": now,
        },
    )
    assert cast(CursorResult, result).rowcount == 1, "transport fence must exist to set erased"


async def _checkpoint_state(
    session: AsyncSession, *, purge_operation_id: uuid.UUID
) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT state, attempt, reason_code FROM "
                "metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op"
            ),
            {"op": purge_operation_id},
        )
    ).mappings().one()
    return dict(row)


async def _operation_state(
    session: AsyncSession, *, purge_operation_id: uuid.UUID
) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT state, failure_code, lease_epoch, revision FROM "
                "metaedu.agent_conversation_purges WHERE id = :op"
            ),
            {"op": purge_operation_id},
        )
    ).mappings().one()
    return dict(row)


async def _snapshot_purge(
    session: AsyncSession,
    *,
    conv_id: uuid.UUID,
    op_id: uuid.UUID,
    owner_key: str,
) -> dict:
    """F-6 零变更判别力：捕获 operation + Conversation + fence + checkpoint + source
    状态（前后快照比对，覆盖身份与状态列，非仅显式 rollback 后"当然没写"）。"""
    op = await _operation_state(session, purge_operation_id=op_id)
    conv_row = (
        await session.execute(
            text(
                "SELECT state, purge_state, purged_at, revision FROM "
                "metaedu.agent_conversations WHERE tenant_id=:t AND id=:c"
            ),
            {"t": TENANT_ID, "c": conv_id},
        )
    ).mappings().one()
    fence_row = (
        await session.execute(
            text(
                "SELECT state, revision, purge_revision, ack_digest FROM "
                "metaedu.agent_erasure_fences "
                "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
            ),
            {"t": TENANT_ID, "c": conv_id, "o": owner_key},
        )
    ).mappings().one_or_none()
    cp_row = (
        await session.execute(
            text(
                "SELECT state, attempt, reason_code, checkpoint_digest, ack_digest "
                "FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id=:op AND owner_key=:o"
            ),
            {"op": op_id, "o": owner_key},
        )
    ).mappings().one_or_none()
    # source：outbox / binding / ledger 身份与状态列（可能不存在则 None）。
    outbox_row = (
        await session.execute(
            text(
                "SELECT id, payload_ref, payload_inline, status FROM "
                "metaedu.agent_workspace_outbox WHERE tenant_id=:t AND conversation_id=:c"
            ),
            {"t": TENANT_ID, "c": conv_id},
        )
    ).mappings().one_or_none()
    binding_row = (
        await session.execute(
            text(
                "SELECT id, runtime_session_ref, status FROM "
                "metaedu.agent_runtime_session_bindings WHERE conversation_id=:c"
            ),
            {"c": conv_id},
        )
    ).mappings().one_or_none()
    ledger_row = (
        await session.execute(
            text(
                "SELECT id, ref_value, erase_state, blocked_reason FROM "
                "metaedu.agent_external_object_refs WHERE tenant_id=:t AND conversation_id=:c"
            ),
            {"t": TENANT_ID, "c": conv_id},
        )
    ).mappings().one_or_none()
    return {
        "operation": op,
        "conversation": dict(conv_row),
        "fence": dict(fence_row) if fence_row else None,
        "checkpoint": dict(cp_row) if cp_row else None,
        "source_outbox": dict(outbox_row) if outbox_row else None,
        "source_binding": dict(binding_row) if binding_row else None,
        "source_ledger": dict(ledger_row) if ledger_row else None,
    }


async def _current_operation_revision(
    session: AsyncSession, *, op_id: uuid.UUID
) -> int:
    return int(
        (
            await session.execute(
                text(
                    "SELECT revision FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).scalar_one()
    )


async def _run_erase_with_retry(*, op_id: uuid.UUID, erase_fn) -> None:
    """S5 风格 owner-walk：并发下每 owner 的 ``_record_blocked`` 会 bump operation
    revision，``_mark_operation_running`` 的 revision CAS 冲突时重读当前 revision
    重试（F-2a「asyncio.gather 并发」需要；S5 顺序处理 owner 时同机制）。"""
    for _ in range(10):
        f, e = await _make_factory()
        try:
            async with f() as sess:
                rev = await _current_operation_revision(sess, op_id=op_id)
                try:
                    await erase_fn(sess, rev)
                    await sess.commit()
                    return
                except ValueError as exc:
                    if "revision" not in str(exc):
                        raise
                    await sess.rollback()  # revision CAS miss -> 重读重试
        finally:
            await e.dispose()
    raise AssertionError("concurrent erase revision-CAS retry exhausted")


async def _erase_external_concurrent(
    *,
    conv_id: uuid.UUID,
    op_id: uuid.UUID,
    purge_rev: int,
    adapter: object,
) -> None:
    """在独立 session 跑 external erase（F-6 行 5 / F-2a 并发 gather 用）。"""

    async def _call(sess, rev):
        await _ext_participant(sess, adapter).erase_external_payload(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=rev,
        )

    await _run_erase_with_retry(op_id=op_id, erase_fn=_call)


async def _erase_runtime_concurrent(
    *,
    conv_id: uuid.UUID,
    op_id: uuid.UUID,
    purge_rev: int,
    adapter: object,
) -> None:
    """同 ``_erase_external_concurrent``，runtime 侧。"""

    async def _call(sess, rev):
        await _runtime_participant(sess, adapter).erase_runtime_session(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=rev,
        )

    await _run_erase_with_retry(op_id=op_id, erase_fn=_call)


async def _erase_transport_concurrent(
    *,
    conv_id: uuid.UUID,
    op_id: uuid.UUID,
    purge_rev: int,
) -> None:
    """同 ``_erase_external_concurrent``，workspace.transport.v1 侧（真实调用
    ``WorkspaceTransportErasureParticipant.erase_transport_owner``，不冒充）。"""

    async def _call(sess, rev):
        await WorkspaceTransportErasureParticipant(sess).erase_transport_owner(
            tenant_id=TENANT_ID,
            conversation_id=conv_id,
            purge_revision=purge_rev,
            purge_operation_id=op_id,
            expected_operation_revision=rev,
        )

    await _run_erase_with_retry(op_id=op_id, erase_fn=_call)


async def _seed_multi_owner_operation(
    session: AsyncSession,
    *,
    conv_id: uuid.UUID,
    purge_rev: int,
    owner_keys: tuple[str, ...],
) -> uuid.UUID:
    """种 running/rev2 的 purge operation + 各 owner pending checkpoint（F-6 多 owner）。

    operation 预置 running + revision=2（S5 已标 running 再分发 owner），各 owner 以
    expected_operation_revision=2 调用无 revision-CAS 竞态；返回 operation_id。
    """
    from app.composition.agent_erasure_registry import capability_digest as _cd
    from app.composition.agent_erasure_registry import registry_digest as _rd
    from tests.composition.test_s4eb2_external_erasure import (
        _registry_snapshot_json as _ext_snapshot,
    )

    op_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purges "
            "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
            "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
            "hold_revision_snapshot, lease_epoch, scheduled_at, started_at, revision, "
            "created_at, updated_at) "
            "VALUES (:id, :t, :c, :r, 'running', :rd, :rs, :rps, :rpd, "
            "0, 0, :now, :now, 2, :now, :now)"
        ),
        {
            "id": op_id,
            "t": TENANT_ID,
            "c": conv_id,
            "r": purge_rev,
            "rd": _rd(),
            "rs": _ext_snapshot(),
            "rps": '{"conversation_recovery_days": 30}',
            "rpd": "e" * 64,
            "now": now,
        },
    )
    for owner_key in owner_keys:
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_conversation_purge_owners "
                "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
                "capability_digest, state, attempt, created_at, updated_at) "
                "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "t": TENANT_ID,
                "op": op_id,
                "o": owner_key,
                "cd": _cd(owner_key),
                "now": now,
            },
        )
    await session.flush()
    return op_id


# ---------------------------------------------------------------------------
# F-6 族 B：external 跨进程 takeover（expire_all 判别）
# ---------------------------------------------------------------------------


_TAKEOVER_BUMPS = (
    # (bump_kind, 期望命中 Tx2 检查的错误子串)
    ("attempt", "attempt"),
    ("checkpoint_digest", "intent"),
    ("lease_epoch", "lease"),
)


@pytest.mark.parametrize(("bump_kind", "expected_substr"), _TAKEOVER_BUMPS)
async def test_external_tx2_cross_process_takeover_fail_closed(
    monkeypatch, session_factory, bump_kind, expected_substr
):
    """F-6 族 B：Tx1 提交后由第二连接篡改**单一**字段（attempt / checkpoint_digest /
    lease_epoch），Tx2 精确重验（E-2a）必须独立命中对应检查并 fail closed + 零写。

    每项独立篡改，避免前一检查遮蔽后一检查（external Tx2 检查顺序：fence -> attempt
    -> intent digest -> ``_load_verified_operation`` lease）；每项断言 ledger 保持
    registered + receipt NULL、source ref 未清、fence/checkpoint 保持 Tx1 窗口态
    （erasing），禁止终态写入。判别点：去掉 ``expire_all`` -> Tx2 读 identity-map
    陈旧实例、篡改不可观测 -> 本测试红（E-2a stale-identity）。
    """
    _enable_external_registry(monkeypatch)

    async with session_factory() as seed:
        await _ensure_test_tenant(seed)
        conv_id, purge_rev = await _ext_seed_conversation(seed)
        await _seed_workspace_outbox_ref(seed, conv_id)
        op_id, _ = await _ext_make_purge_operation(seed, conv_id, purge_rev)
        await seed.commit()

    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    class _TakeoverAdapter(_ExternalSuccessAdapter):
        """Tx1 提交后进入 adapter 窗口：set entered、等 release（Tx2 前暂停）。"""

        async def delete_object(self, **kwargs):
            self.calls += 1
            adapter_entered.set()
            await adapter_release.wait()
            return ExternalEraseSuccess(
                adapter_receipt_evidence=f"ev:{kwargs['idempotency_key'][:16]}"
            )

    tx2_error: list[Exception] = []

    async def _run_erase_a():
        factory, engine = await _make_factory()
        try:
            async with factory() as sess:
                participant = _ext_participant(sess, _TakeoverAdapter())
                try:
                    await participant.erase_external_payload(
                        tenant_id=TENANT_ID,
                        conversation_id=conv_id,
                        purge_revision=purge_rev,
                        purge_operation_id=op_id,
                        expected_operation_revision=1,
                    )
                except ValueError as exc:
                    tx2_error.append(exc)
        finally:
            await engine.dispose()

    async def _takeover_bump():
        """等待 A 进入 adapter 窗口（Tx1 已提交、锁已释放）后，第二连接篡改**单一**
        字段模拟另一进程 takeover。"""
        await adapter_entered.wait()
        factory, engine = await _make_factory()
        try:
            async with factory() as sess:
                if bump_kind == "attempt":
                    await sess.execute(
                        text(
                            "UPDATE metaedu.agent_conversation_purge_owners "
                            "SET attempt = attempt + 1, updated_at = clock_timestamp() "
                            "WHERE tenant_id = :t AND purge_operation_id = :op"
                        ),
                        {"t": TENANT_ID, "op": op_id},
                    )
                elif bump_kind == "checkpoint_digest":
                    await sess.execute(
                        text(
                            "UPDATE metaedu.agent_conversation_purge_owners "
                            "SET checkpoint_digest = :d, updated_at = clock_timestamp() "
                            "WHERE tenant_id = :t AND purge_operation_id = :op"
                        ),
                        {"t": TENANT_ID, "op": op_id, "d": "f" * 64},
                    )
                elif bump_kind == "lease_epoch":
                    await sess.execute(
                        text(
                            "UPDATE metaedu.agent_conversation_purges "
                            "SET lease_epoch = lease_epoch + 5, updated_at = clock_timestamp() "
                            "WHERE tenant_id = :t AND id = :op"
                        ),
                        {"t": TENANT_ID, "op": op_id},
                    )
                await sess.commit()
        finally:
            await engine.dispose()
        adapter_release.set()

    await asyncio.gather(_run_erase_a(), _takeover_bump())

    assert tx2_error, (
        "external Tx2 must fail closed on cross-process takeover; "
        "if this assertion fires, `expire_all` was removed/moved (E-2a stale-identity bug)"
    )
    # 判别：该篡改字段独立命中对应 Tx2 检查（非被前一检查遮蔽）。
    assert expected_substr in str(tx2_error[0]), (
        f"expected {expected_substr!r} in error, got {tx2_error[0]}"
    )

    # F-6 行 5「fail closed + 零写」：ledger 保持 registered + receipt NULL、source
    # ref 未清、fence/checkpoint 保持 Tx1 窗口态（erasing），禁止终态写入。
    async with session_factory() as check:
        fence_state = (
            await check.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
                ),
                {"t": TENANT_ID, "c": conv_id, "o": EXTERNAL_PAYLOAD_OWNER},
            )
        ).scalar_one()
        assert fence_state == "erasing", fence_state
        cp = await _checkpoint_state(check, purge_operation_id=op_id)
        assert cp["state"] == PurgeOwnerState.ERASING.value, cp
        ledger = (
            await check.execute(
                text(
                    "SELECT erase_state, receipt_digest FROM "
                    "metaedu.agent_external_object_refs "
                    "WHERE tenant_id=:t AND conversation_id=:c"
                ),
                {"t": TENANT_ID, "c": conv_id},
            )
        ).mappings().one()
        assert ledger["erase_state"] == "registered", ledger
        assert ledger["receipt_digest"] is None, ledger
        # source ref 未清（Tx2 在清 ref 前 raise）。B2 seed 用 aggregate_id 链接
        # conversation（outbox 的 conversation_id 列为 NULL）。
        src_ref = (
            await check.execute(
                text(
                    "SELECT payload_ref FROM metaedu.agent_workspace_outbox "
                    "WHERE tenant_id=:t AND aggregate_id=:c AND aggregate_type='conversation'"
                ),
                {"t": TENANT_ID, "c": conv_id},
            )
        ).scalar_one()
        assert src_ref is not None, "source ref must not be cleared on failed Tx2"


# ---------------------------------------------------------------------------
# F-6 族 B：跨 purge 实例 erased-fence 重放拒绝（external + transport）
# ---------------------------------------------------------------------------


async def test_erased_fence_cross_purge_instance_rejected_external(monkeypatch, session_factory):
    """F-6 族 B：op1 已 erased fence（purge_revision=1）+ op2 pending checkpoint
    （purge_revision=2）——op2 重放不得用 op1 的 ack_digest 修复 pending。

    判别点：**去掉 external erased-fence ``fence.purge_revision == purge_revision``
    门禁（变异）-> op2 的 pending checkpoint 被置 ACKED（跨 purge 实例 ack 摘要
    污染），不 raise -> 本测试红**。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, _ = await _ext_seed_conversation(seed)  # purge_revision=1 baseline
            await _seed_erased_external_fence(
                seed,
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=1,
            )
            # op2：purge_revision=2 + pending external checkpoint（rev 2 的新 purge）。
            op2_id, _ = await _ext_make_purge_operation(seed, conv_id, 2)
            await seed.commit()

        async with factory() as sess:
            participant = _ext_participant(sess, _ExternalSuccessAdapter())
            with pytest.raises(ValueError, match="cross-purge-instance"):
                await participant.erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=2,
                    purge_operation_id=op2_id,
                    expected_operation_revision=1,
                )

        # op2 拒绝且 pending 不修复（门禁在 repair 之前，零 ACK 修复）。
        async with factory() as check:
            cp = await _checkpoint_state(check, purge_operation_id=op2_id)
            assert cp["state"] == PurgeOwnerState.PENDING.value, cp
            op = await _operation_state(check, purge_operation_id=op2_id)
            assert op["state"] == PurgeOperationState.SCHEDULED.value, op
    finally:
        await engine.dispose()


async def test_erased_fence_cross_purge_instance_rejected_transport(session_factory):
    """F-6 族 B：同前，transport 侧（workspace.transport.v1）。

    判别点：**去掉 transport 基类 erased-fence ``purge_revision`` 门禁（变异）->
    op2 的 pending checkpoint 被修复 -> 不 raise -> 本测试红**。transport registry
    （workspace.transport.v1）为 True，无需 monkeypatch。
    """
    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, _ = await _transport_seed_conversation(
                seed, owner="workspace.transport.v1"
            )
            await _seed_erased_transport_fence(
                seed,
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                owner="workspace.transport.v1",
                purge_revision=1,
            )
            op2_id, _ = await _transport_make_purge_operation(
                seed, conv_id, 2, owner="workspace.transport.v1"
            )
            await seed.commit()

        async with factory() as sess:
            participant = WorkspaceTransportErasureParticipant(sess)
            with pytest.raises(ValueError, match="cross-purge-instance"):
                await participant.erase_transport_owner(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=2,
                    purge_operation_id=op2_id,
                    expected_operation_revision=1,
                )

        async with factory() as check:
            cp = await _checkpoint_state(check, purge_operation_id=op2_id)
            assert cp["state"] == PurgeOwnerState.PENDING.value, cp
            op = await _operation_state(check, purge_operation_id=op2_id)
            assert op["state"] == PurgeOperationState.SCHEDULED.value, op
    finally:
        await engine.dispose()


async def test_external_erasing_fence_second_purge_instance_rejected(
    monkeypatch, session_factory
):
    """族 A（并发面 P1-1）：external fence 已 erasing（op1 中段）时 op2（rev2）不得
    进入 adapter 窗口——ERASING 分支 same-purge-instance 门禁（镜像 runtime
    ``:594-606``；E-6「重复删除」串行化契约）。

    判别点：**去掉 external ERASING 分支 ``fence.purge_revision == purge_revision``
    门禁（变异）-> op2 穿透进入 adapter 窗口、adapter.delete_object 被调用（重复
    外部副作用）-> 本测试红（adapter.calls==0 不成立）**。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, _ = await _ext_seed_conversation(seed)
            # op1 中段：external fence 已 erasing + purge_revision=1。
            await _seed_erasing_external_fence(
                seed,
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=1,
            )
            await _seed_workspace_outbox_ref(seed, conv_id)
            # op2：purge_revision=2 + pending checkpoint。
            op2_id, _ = await _ext_make_purge_operation(seed, conv_id, 2)
            await seed.commit()

        adapter = _ExternalSuccessAdapter()
        async with factory() as sess:
            participant = _ext_participant(sess, adapter)
            with pytest.raises(ValueError, match="same-instance gate"):
                await participant.erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=2,
                    purge_operation_id=op2_id,
                    expected_operation_revision=1,
                )
        # op2 不得进入 adapter 窗口（重复外部副作用为 0）——门禁在窗口准入点之前。
        assert adapter.calls == 0, (
            "second purge instance must not enter the adapter window; "
            "if this fires, the ERASING same-purge-instance gate was removed"
        )
        # op2 checkpoint 仍 pending（未推进 erasing）。
        async with factory() as check:
            cp = await _checkpoint_state(check, purge_operation_id=op2_id)
            assert cp["state"] == PurgeOwnerState.PENDING.value, cp
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6 R1-AC9：跨 tenant / owner scope mismatch / operation revision 重放
# ---------------------------------------------------------------------------


async def test_cross_tenant_forged_ack_fail_closed(monkeypatch, session_factory):
    """F-6 R1-AC9：tenant A 的 operation 在 tenant B 的 conversation 上重放 -> 拒绝。

    判别点：``_load_verified_operation`` 按 (tenant_id, purge_operation_id) 查询，
    跨 tenant 伪造 ACK -> operation 未找到 -> fail closed，零终态写入。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            # tenant A（TENANT_ID）：conversation + external fence + ref + op。
            conv_a, purge_rev = await _ext_seed_conversation(seed)
            await _seed_workspace_outbox_ref(seed, conv_a)
            op_a, _ = await _ext_make_purge_operation(seed, conv_a, purge_rev)
            # tenant B：独立 conversation + external fence（owner 同 external）。
            tenant_b = await _seed_second_tenant(seed)
            conv_b = uuid.uuid4()
            now = datetime.now(UTC).replace(tzinfo=None)
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_conversations "
                    "(id, tenant_id, created_by, creation_digest, creator_identity_digest, "
                    "state, title, title_source, next_message_seq, next_run_queue_seq, "
                    "last_activity_at, purge_state, purge_revision, purged_at, "
                    "purge_after, deleted_at, created_at, updated_at, revision, "
                    "hold_revision, actor_state) "
                    "VALUES (:id, :t, NULL, :cd, :cid, 'deleted', :title, 'user', "
                    "1, 1, :now, 'scheduled', 1, NULL, :pa, :da, :now, :now, 3, "
                    "0, 'redacted')"
                ),
                {
                    "id": conv_b,
                    "t": tenant_b,
                    "cd": "c" * 64,
                    "cid": "d" * 64,
                    "title": "s4f tenant-b conversation",
                    "now": now,
                    "pa": now,
                    "da": now,
                },
            )
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now)"
                ),
                {
                    "t": tenant_b,
                    "c": conv_b,
                    "o": EXTERNAL_PAYLOAD_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            await seed.commit()

        async with factory() as sess:
            participant = _ext_participant(sess, _ExternalSuccessAdapter())
            # 用 tenant B 的 conversation + tenant A 的 operation 重放。
            with pytest.raises(ValueError):
                await participant.erase_external_payload(
                    tenant_id=tenant_b,
                    conversation_id=conv_b,
                    purge_revision=1,
                    purge_operation_id=op_a,
                    expected_operation_revision=1,
                )

        # F-6 行 1「断言零变更」：tenant-B 侧 fence 仍 active、无新增 checkpoint
        # （operation 身份/tenant scope fail closed 且事务回滚，无持久化写）。
        async with factory() as check:
            fence_b = (
                await check.execute(
                    text(
                        "SELECT state FROM metaedu.agent_erasure_fences "
                        "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
                    ),
                    {"t": tenant_b, "c": conv_b, "o": EXTERNAL_PAYLOAD_OWNER},
                )
            ).scalar_one()
            assert fence_b == "active", fence_b
            # tenant-A 的 op_a 在 tenant-B 不得产生 checkpoint（跨 tenant 零写）。
            op_a_cp = (
                await check.execute(
                    text(
                        "SELECT count(*) FROM "
                        "metaedu.agent_conversation_purge_owners "
                        "WHERE tenant_id = :t AND purge_operation_id = :op"
                    ),
                    {"t": tenant_b, "op": op_a},
                )
            ).scalar_one()
            assert op_a_cp == 0, f"cross-tenant forged ACK wrote checkpoint, count={op_a_cp}"
    finally:
        await engine.dispose()


async def test_owner_scope_mismatch_capability_gate(monkeypatch, session_factory):
    """F-6 R1-AC9：conversation 已登记 owner 与直调 participant 不符 -> fail closed。

    判别点：external 直调 conversation 上 workspace.transport.v1 的 owner checkpoint
    缺 external 行 -> ``_load_verified_checkpoint`` 找不到 -> fail closed。**零变更
    判别力**：异常前无持久化副作用——external fence 未被创建、operation 仍 scheduled/
    rev1、transport checkpoint 仍 pending（前后快照一致；Tx1 的 fence 创建/推进/mark
    running 均回滚，不落库）。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _transport_seed_conversation(
                seed, owner="workspace.transport.v1"
            )
            # purge operation 只登记 transport owner checkpoint（external 无 checkpoint）。
            op_id, _ = await _transport_make_purge_operation(
                seed, conv_id, purge_rev, owner="workspace.transport.v1"
            )
            await seed.commit()

        # 前后快照（external owner 维度）。
        async with factory() as before_sess:
            before = await _snapshot_purge(
                before_sess, conv_id=conv_id, op_id=op_id,
                owner_key=EXTERNAL_PAYLOAD_OWNER,
            )

        async with factory() as sess:
            participant = _ext_participant(sess, _ExternalSuccessAdapter())
            with pytest.raises(ValueError, match="checkpoint"):
                await participant.erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=purge_rev,
                    purge_operation_id=op_id,
                    expected_operation_revision=1,
                )
            await sess.rollback()  # 失败路径显式回滚（S5 调用方回滚语义）

        async with factory() as after_sess:
            after = await _snapshot_purge(
                after_sess, conv_id=conv_id, op_id=op_id,
                owner_key=EXTERNAL_PAYLOAD_OWNER,
            )
        assert before == after, (
            f"owner scope mismatch must leave zero persistent side effect;\n"
            f"before={before}\nafter={after}"
        )
    finally:
        await engine.dispose()


async def test_operation_revision_replay_rejected(monkeypatch, session_factory):
    """F-6 R1-AC9：旧 revision 的 purge operation 重放 -> revision CAS 拒绝。

    判别点：seed operation revision=2，重放 expected_operation_revision=1 ->
    ``_load_verified_operation`` revision mismatch -> fail closed。**零变更判别力**：
    异常前无持久化副作用——operation revision 不变、external fence 保持 active、
    checkpoint 保持 pending（前后快照一致）。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            op_id, _ = await _ext_make_purge_operation(seed, conv_id, purge_rev)
            # 直接推进 operation revision 到 2（模拟已执行过一轮）。
            await seed.execute(
                text(
                    "UPDATE metaedu.agent_conversation_purges "
                    "SET revision = 2, updated_at = clock_timestamp() "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
            await seed.commit()

        async with factory() as before_sess:
            before = await _snapshot_purge(
                before_sess, conv_id=conv_id, op_id=op_id,
                owner_key=EXTERNAL_PAYLOAD_OWNER,
            )

        async with factory() as sess:
            participant = _ext_participant(sess, _ExternalSuccessAdapter())
            with pytest.raises(ValueError, match="revision"):
                await participant.erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=purge_rev,
                    purge_operation_id=op_id,
                    expected_operation_revision=1,  # 旧 revision -> CAS 拒绝
                )
            await sess.rollback()  # 失败路径显式回滚

        async with factory() as after_sess:
            after = await _snapshot_purge(
                after_sess, conv_id=conv_id, op_id=op_id,
                owner_key=EXTERNAL_PAYLOAD_OWNER,
            )
        assert before == after, (
            f"stale revision replay must leave zero persistent side effect;\n"
            f"before={before}\nafter={after}"
        )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6：跨 Conversation 同一 object 双删（幂等重放 adapter，distinct delete==1）
# ---------------------------------------------------------------------------


async def test_cross_conversation_same_object_double_delete_once(monkeypatch, session_factory):
    """F-6：同一 external object ref 出现在两个 conversation，两 purge 并发。

    两 conversation 共用 idempotency key（ref_scheme+ref_value+adapter，不含
    conversation）+ **共享 adapter store 幂等去重**——仅对幂等重放 adapter 保证
    distinct delete==1（F-6 限定，receipt-lookup-only adapter 归 adapter 层）。

    判别点：``delete_object`` 每 conversation 各调用一次（总 2），但真实外部删除
    （distinct key）== 1；共享 store 二次调用返回缓存 evidence（幂等重放）。
    """
    _enable_external_registry(monkeypatch)

    # 共享 adapter store：key -> evidence（幂等去重）+ 真实删除计数（跨实例共享）。
    shared_store: dict[str, str] = {}
    shared_deletes: list[int] = [0]

    class _SharedDedupAdapter(_ExternalSuccessAdapter):
        """幂等重放 adapter：同 key 二次调用不重复删（共享 key→evidence store）。"""

        def __init__(self, store: dict[str, str], deletes: list[int]) -> None:
            super().__init__()
            self.store = store
            self.deletes = deletes

        async def delete_object(self, **kwargs):
            self.calls += 1
            key = kwargs["idempotency_key"]
            if key in self.store:
                # 幂等重放：对象已删除，返回缓存 evidence（不再产生副作用）。
                return ExternalEraseSuccess(
                    adapter_receipt_evidence=self.store[key]
                )
            self.store[key] = f"ev:{key[:16]}"
            self.deletes[0] += 1
            return ExternalEraseSuccess(
                adapter_receipt_evidence=self.store[key]
            )

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv1, rev1 = await _ext_seed_conversation(seed)
            conv2, rev2 = await _ext_seed_conversation(seed)
            # 同一 ref_value 出现在两个 conversation（各自 outbox + ledger registered）。
            await _seed_workspace_outbox_ref(seed, conv1, ref_value=_REF_VALUE)
            await _seed_workspace_outbox_ref(seed, conv2, ref_value=_REF_VALUE)
            op1, _ = await _ext_make_purge_operation(seed, conv1, rev1)
            op2, _ = await _ext_make_purge_operation(seed, conv2, rev2)
            await seed.commit()

        errors: list[Exception] = []

        async def _erase_one(conv_id, op_id, rev):
            f, e = await _make_factory()
            try:
                async with f() as sess:
                    participant = _ext_participant(
                        sess, _SharedDedupAdapter(shared_store, shared_deletes)
                    )
                    try:
                        await participant.erase_external_payload(
                            tenant_id=TENANT_ID,
                            conversation_id=conv_id,
                            purge_revision=rev,
                            purge_operation_id=op_id,
                            expected_operation_revision=1,
                        )
                    except ValueError as exc:
                        errors.append(exc)
            finally:
                await e.dispose()

        await asyncio.gather(
            _erase_one(conv1, op1, rev1),
            _erase_one(conv2, op2, rev2),
        )

        assert not errors, [str(e) for e in errors]
        # 每个 conversation 的 erase 都调用了一次 adapter（总 2），但真实外部删除
        # （distinct key）== 1——共享 store 幂等去重。
        assert shared_deletes[0] == 1, (
            f"cross-conversation same-object double delete must produce exactly 1 "
            f"distinct external side effect, got {shared_deletes[0]}"
        )

        # 两个 conversation 均达成 erased + ref 清除。
        async with factory() as check:
            for conv_id in (conv1, conv2):
                leftover = (
                    await check.execute(
                        text(
                            "SELECT count(*) FROM metaedu.agent_external_object_refs "
                            "WHERE tenant_id = :t AND conversation_id = :c "
                            "AND erase_state <> 'erased'"
                        ),
                        {"t": TENANT_ID, "c": conv_id},
                    )
                ).scalar_one()
                assert leftover == 0, f"conversation {conv_id} has non-erased refs"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6/F-4：混合多族故障五方一致 + partial ACK 负向（D6）
# ---------------------------------------------------------------------------


async def test_mixed_multi_family_faults_five_party_consistent(monkeypatch, session_factory):
    """F-4/F-6：同一 conversation 内 external（success -> erased）+ runtime
    （timeout -> unknown）混合故障——各 owner 的 checkpoint/fence/ledger/binding 各自
    一致（owner-scoped），互不误伤。

    断言（owner-scoped，架构裁决后不断 operation/Conversation 聚合）：
    external fence erased + checkpoint acked + external ledger erased；runtime fence
    erasing + checkpoint blocked（`outcome_unknown`）+ binding invalid。
    operation/Conversation 的聚合是 S5 reducer 职责（临时投影，不断言）。
    执行按 F-6 行 5 冻结的 ``asyncio.gather`` 并发；operation 预置 running/revision=2
    （S5 已标 running 再分发 owner），两 owner 均以 expected_revision=2 跑，无
    revision-CAS 竞态。
    """
    _enable_external_registry(monkeypatch)
    _enable_runtime_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            # external ref（workspace outbox -> ledger registered）+ runtime binding
            # 同一 conversation（external erase 实际清除 1 个 ref，ledger 落 erased）。
            await _seed_workspace_outbox_ref(seed, conv_id)
            # runtime fence + binding（同一 conversation）。
            now = datetime.now(UTC).replace(tzinfo=None)
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now) ON CONFLICT DO NOTHING"
                ),
                {
                    "t": TENANT_ID,
                    "c": conv_id,
                    "o": RUNTIME_PRIVATE_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            await _seed_runtime_binding(seed, conv_id, ref_value=_RUNTIME_REF)
            # external op（含 external + runtime 两个 owner checkpoint）。
            op_id = uuid.uuid4()
            from app.composition.agent_erasure_registry import capability_digest as _cd
            from app.composition.agent_erasure_registry import registry_digest as _rd
            from tests.composition.test_s4eb2_external_erasure import (
                _registry_snapshot_json as _ext_snapshot,
            )

            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_conversation_purges "
                    "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
                    "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
                    "hold_revision_snapshot, lease_epoch, scheduled_at, revision, "
                    "created_at, updated_at) "
                    "VALUES (:id, :t, :c, :r, 'scheduled', :rd, :rs, :rps, :rpd, "
                    "0, 0, :now, 1, :now, :now)"
                ),
                {
                    "id": op_id,
                    "t": TENANT_ID,
                    "c": conv_id,
                    "r": purge_rev,
                    "rd": _rd(),
                    "rs": _ext_snapshot(),
                    "rps": '{"conversation_recovery_days": 30}',
                    "rpd": "e" * 64,
                    "now": now,
                },
            )
            for owner_key in (EXTERNAL_PAYLOAD_OWNER, RUNTIME_PRIVATE_OWNER):
                await seed.execute(
                    text(
                        "INSERT INTO metaedu.agent_conversation_purge_owners "
                        "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
                        "capability_digest, state, attempt, created_at, updated_at) "
                        "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": TENANT_ID,
                        "op": op_id,
                        "o": owner_key,
                        "cd": _cd(owner_key),
                        "now": now,
                    },
                )
            # operation 预置 running + revision=2（模拟 S5 已把 operation 标 running
            # 后再分发 owner）——两 owner 均以 expected_revision=2 跑，_mark_operation_running
            # 对已 running 不 bump，**无 revision-CAS 竞态**（避免并发下重试回滚 op
            # 状态；F-6 行 5 并发用 asyncio.gather，Deterministic）。
            await seed.execute(
                text(
                    "UPDATE metaedu.agent_conversation_purges "
                    "SET state = 'running', revision = 2, started_at = :now, "
                    "updated_at = :now WHERE id = :op"
                ),
                {"op": op_id, "now": now},
            )
            await seed.commit()

        # F-6 行 5 冻结「asyncio.gather 并发」：external（success -> erased）+ runtime
        # （timeout -> unknown）并发驱动；operation 预置 running/rev2，两 owner 都以
        # expected_operation_revision=2 调用（Conversation 行锁使 Tx1 入口串行化，
        # 无 revision-CAS 竞态、无重试）。最终 op blocked：external ACK 不改 op 状态
        # （_ack_owner_checkpoint 只要求 running/blocked 可 ACK），runtime blocked 是
        # 最后写——无论 ACK/block 顺序均收敛 blocked。
        await asyncio.gather(
            _erase_external_concurrent(
                conv_id=conv_id,
                op_id=op_id,
                purge_rev=purge_rev,
                adapter=_ExternalSuccessAdapter(),
            ),
            _erase_runtime_concurrent(
                conv_id=conv_id,
                op_id=op_id,
                purge_rev=purge_rev,
                adapter=_RuntimeTimeoutAdapter(),
            ),
        )

        async with factory() as check:
            # external：fence erased + checkpoint acked。
            ext_fence = (
                await check.execute(
                    text(
                        "SELECT state, ack_digest FROM metaedu.agent_erasure_fences "
                        "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
                    ),
                    {"t": TENANT_ID, "c": conv_id, "o": EXTERNAL_PAYLOAD_OWNER},
                )
            ).mappings().one()
            assert ext_fence["state"] == "erased" and ext_fence["ack_digest"] is not None
            ext_cp = (
                await check.execute(
                    text(
                        "SELECT state FROM metaedu.agent_conversation_purge_owners "
                        "WHERE purge_operation_id=:op AND owner_key=:o"
                    ),
                    {"op": op_id, "o": EXTERNAL_PAYLOAD_OWNER},
                )
            ).scalar_one()
            assert ext_cp == PurgeOwnerState.ACKED.value

            # runtime：fence erasing + checkpoint blocked + binding invalid。
            rt_fence = (
                await check.execute(
                    text(
                        "SELECT state FROM metaedu.agent_erasure_fences "
                        "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
                    ),
                    {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
                )
            ).scalar_one()
            assert rt_fence == "erasing"
            rt_cp = (
                await check.execute(
                    text(
                        "SELECT state, reason_code FROM "
                        "metaedu.agent_conversation_purge_owners "
                        "WHERE purge_operation_id=:op AND owner_key=:o"
                    ),
                    {"op": op_id, "o": RUNTIME_PRIVATE_OWNER},
                )
            ).mappings().one()
            assert rt_cp["state"] == PurgeOwnerState.BLOCKED.value
            assert rt_cp["reason_code"] == "purge_blocked_by_runtime_outcome_unknown"
            binding = (
                await check.execute(
                    text(
                        "SELECT status FROM metaedu.agent_runtime_session_bindings "
                        "WHERE conversation_id = :c AND runtime_session_ref IS NOT NULL"
                    ),
                    {"c": conv_id},
                )
            ).scalars().first()
            assert binding == "invalid"

            # owner-scoped 断言（架构裁决后：不断 operation.failure_code/Conversation
            # 聚合——那是 S5 reducer 职责；只断各 owner 的 checkpoint/fence/ledger/binding）：
            # external ledger：external success 后全部 erased（receipt 留证）。
            ext_ledger = (
                await check.execute(
                    text(
                        "SELECT count(*) FROM metaedu.agent_external_object_refs "
                        "WHERE tenant_id=:t AND conversation_id=:c AND erase_state='erased'"
                    ),
                    {"t": TENANT_ID, "c": conv_id},
                )
            ).scalar_one()
            assert ext_ledger == 1, f"external ledger must be erased, got {ext_ledger}"
    finally:
        await engine.dispose()


async def test_three_owner_mixed_faults_owner_scoped(
    monkeypatch, session_factory
):
    """F-6 三 owner 混合故障 + **同源互操作**（架构裁决后：只断 owner-scoped，不断
    operation.failure_code/Conversation 聚合——那是 S5 reducer 职责）。

    external（timeout -> outcome_unknown）+ runtime（failed -> adapter_unavailable）
    + transport（ref-bearing -> purge_owner_unavailable）三族并发，其中 **external 与
    transport 真实处理同一 workspace outbox payload_ref**（经 `_seed_workspace_outbox_ref`
    注册到 external ledger，非「另一条 RunEvent ref」冒充同源）。

    断言（owner-scoped，逐 owner）：
    - external checkpoint blocked + reason=`purge_blocked_by_external_outcome_unknown`、
      external ledger `unknown`（timeout 不清 source ref）；
    - runtime checkpoint blocked + reason=`purge_blocked_by_runtime_adapter_unavailable`、
      binding `invalid`；
    - transport checkpoint blocked + reason=`purge_owner_unavailable`（ref-bearing 前置
      命中，fence 保持 active）。
    **不断** operation.failure_code 聚合（临时投影，归 S5）。
    """
    _enable_external_registry(monkeypatch)
    _enable_runtime_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)  # external fence
            now = datetime.now(UTC).replace(tzinfo=None)
            # runtime fence + binding（同一 conversation）。
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now) ON CONFLICT DO NOTHING"
                ),
                {
                    "t": TENANT_ID,
                    "c": conv_id,
                    "o": RUNTIME_PRIVATE_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            # transport fence（同一 conversation）。
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now) ON CONFLICT DO NOTHING"
                ),
                {
                    "t": TENANT_ID,
                    "c": conv_id,
                    "o": WORKSPACE_TRANSPORT_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            # runtime binding（runtime 的清除对象）。
            await _seed_runtime_binding(seed, conv_id, ref_value=_RUNTIME_REF)
            # 同源 outbox：workspace outbox payload_ref（设 conversation_id scope 列，
            # 使 transport 的 ref-bearing 前置可见）**同时**按 B1 lifecycle 注册到
            # external ledger——external（清 ledger）与 transport（ref-bearing 前置）
            # 真实处理同一 source/ref。
            outbox_id = await _seed_transport_outbox(
                seed, conversation_id=conv_id, side="workspace",
                payload_ref=_REF_VALUE,
            )
            await _seed_external_ledger_ref(
                seed, conversation_id=conv_id, source_table="agent_workspace_outbox",
                source_row_id=outbox_id, ref_value=_REF_VALUE,
            )
            op_id = await _seed_multi_owner_operation(
                seed,
                conv_id=conv_id,
                purge_rev=purge_rev,
                owner_keys=(
                    EXTERNAL_PAYLOAD_OWNER,
                    RUNTIME_PRIVATE_OWNER,
                    WORKSPACE_TRANSPORT_OWNER,
                ),
            )
            await seed.commit()

        # 三族并发，各注入不同 reason 的故障（真实 PG + asyncio.gather）。
        await asyncio.gather(
            _erase_external_concurrent(
                conv_id=conv_id, op_id=op_id, purge_rev=purge_rev,
                adapter=_ExternalTimeoutAdapter(),  # timeout -> outcome_unknown
            ),
            _erase_runtime_concurrent(
                conv_id=conv_id, op_id=op_id, purge_rev=purge_rev,
                adapter=_RuntimeFailedAdapter(),  # failed -> adapter_unavailable
            ),
            _erase_transport_concurrent(
                conv_id=conv_id, op_id=op_id, purge_rev=purge_rev,
                # ref-bearing -> purge_owner_unavailable
            ),
        )

        async with factory() as check:
            # checkpoint.reason_code 逐 owner 精确（owner-specific）。
            async def _cp(owner_key):
                return (
                    (
                        await check.execute(
                            text(
                                "SELECT state, reason_code FROM "
                                "metaedu.agent_conversation_purge_owners "
                                "WHERE purge_operation_id=:op AND owner_key=:o"
                            ),
                            {"op": op_id, "o": owner_key},
                        )
                    ).mappings().one()
                )

            ext_cp = await _cp(EXTERNAL_PAYLOAD_OWNER)
            rt_cp = await _cp(RUNTIME_PRIVATE_OWNER)
            tp_cp = await _cp(WORKSPACE_TRANSPORT_OWNER)
            assert ext_cp["state"] == PurgeOwnerState.BLOCKED.value
            assert ext_cp["reason_code"] == "purge_blocked_by_external_outcome_unknown"
            assert rt_cp["state"] == PurgeOwnerState.BLOCKED.value
            assert rt_cp["reason_code"] == "purge_blocked_by_runtime_adapter_unavailable"
            assert tp_cp["state"] == PurgeOwnerState.BLOCKED.value
            assert tp_cp["reason_code"] == "purge_owner_unavailable"

            # 同源互操作断言（owner-scoped）：
            # ① external ledger 落 unknown（timeout 可能已生效），source ref 未清。
            ledger = (
                await check.execute(
                    text(
                        "SELECT erase_state, ref_value FROM "
                        "metaedu.agent_external_object_refs "
                        "WHERE tenant_id=:t AND conversation_id=:c"
                    ),
                    {"t": TENANT_ID, "c": conv_id},
                )
            ).mappings().one()
            assert ledger["erase_state"] == "unknown", ledger
            assert ledger["ref_value"] == _REF_VALUE, ledger
            src_ref = (
                await check.execute(
                    text(
                        "SELECT payload_ref FROM metaedu.agent_workspace_outbox "
                        "WHERE tenant_id=:t AND conversation_id=:c"
                    ),
                    {"t": TENANT_ID, "c": conv_id},
                )
            ).scalar_one()
            assert src_ref == _REF_VALUE, "timeout must not clear source ref"
            # ② runtime binding 落 invalid（ref 保留）。
            binding = (
                await check.execute(
                    text(
                        "SELECT status FROM metaedu.agent_runtime_session_bindings "
                        "WHERE conversation_id=:c AND runtime_session_ref IS NOT NULL"
                    ),
                    {"c": conv_id},
                )
            ).scalars().first()
            assert binding == "invalid", binding
            # ③ transport fence 保持 active（ref-bearing 前置在 fence→erasing 之前）。
            tp_fence = (
                await check.execute(
                    text(
                        "SELECT state FROM metaedu.agent_erasure_fences "
                        "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"
                    ),
                    {"t": TENANT_ID, "c": conv_id, "o": WORKSPACE_TRANSPORT_OWNER},
                )
            ).scalar_one()
            assert tp_fence == "active", tp_fence
    finally:
        await engine.dispose()


async def test_external_transport_same_source_receipt_then_replay(monkeypatch, session_factory):
    """F-6 同源互操作**正序列**（P2-1 补强）：external 与 transport 处理同一 workspace
    outbox payload_ref（registered 到 external ledger），三段顺序：

    1. transport 先跑（ref-bearing）-> `purge_owner_unavailable` blocked，源行零修改；
    2. external success -> 写 ledger erased+receipt 再清同一 source ref 转 suppressed；
    3. transport replay -> `count_ref_bearing_outbox_rows` 归 0 -> 放行 -> ACK。

    证明「先删 external object 取 receipt，再清 transport DB ref（D5）」后 transport
    可重跑 ACK，且两步互斥（receipt 前 transport 零修改 blocked、receipt 后放行）。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            # external fence（ext_seed_conversation）+ transport fence 同 conversation。
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            now = datetime.now(UTC).replace(tzinfo=None)
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now) ON CONFLICT DO NOTHING"
                ),
                {
                    "t": TENANT_ID, "c": conv_id, "o": WORKSPACE_TRANSPORT_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            # 同源 outbox ref（conversation_id scope + payload_ref）+ ledger registered。
            outbox_id = await _seed_transport_outbox(
                seed, conversation_id=conv_id, side="workspace", payload_ref=_REF_VALUE,
            )
            await _seed_external_ledger_ref(
                seed, conversation_id=conv_id, source_table="agent_workspace_outbox",
                source_row_id=outbox_id, ref_value=_REF_VALUE,
            )
            op_id = await _seed_multi_owner_operation(
                seed, conv_id=conv_id, purge_rev=purge_rev,
                owner_keys=(EXTERNAL_PAYLOAD_OWNER, WORKSPACE_TRANSPORT_OWNER),
            )
            await seed.commit()

        # ① transport 先跑：ref-bearing 前置 -> blocked，源行零修改。
        async with factory() as sess:
            rev = await _current_operation_revision(sess, op_id=op_id)
            await WorkspaceTransportErasureParticipant(sess).erase_transport_owner(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=rev,
            )
            await sess.commit()
        async with factory() as check:
            tp_cp = (
                (await check.execute(
                    text("SELECT state, reason_code FROM metaedu.agent_conversation_purge_owners "
                         "WHERE purge_operation_id=:op AND owner_key=:o"),
                    {"op": op_id, "o": WORKSPACE_TRANSPORT_OWNER},
                )).mappings().one()
            )
            assert tp_cp["state"] == PurgeOwnerState.BLOCKED.value
            assert tp_cp["reason_code"] == "purge_owner_unavailable"
            src = (
                (await check.execute(
                    text("SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                         "WHERE tenant_id=:t AND conversation_id=:c"),
                    {"t": TENANT_ID, "c": conv_id},
                )).mappings().one()
            )
            assert src["payload_ref"] == _REF_VALUE  # transport 前置零修改

        # ② external success：写 erased+receipt 再清同一 source ref。
        async with factory() as sess:
            rev = await _current_operation_revision(sess, op_id=op_id)
            await _ext_participant(sess, _ExternalSuccessAdapter()).erase_external_payload(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=rev,
            )
            await sess.commit()
        async with factory() as check:
            ledger = (
                (await check.execute(
                    text(
                        "SELECT erase_state, receipt_digest FROM "
                        "metaedu.agent_external_object_refs "
                        "WHERE tenant_id=:t AND conversation_id=:c"
                    ),
                    {"t": TENANT_ID, "c": conv_id},
                )).mappings().one()
            )
            assert ledger["erase_state"] == "erased"
            assert ledger["receipt_digest"] is not None
            src = (
                (await check.execute(
                    text("SELECT payload_ref, status FROM metaedu.agent_workspace_outbox "
                         "WHERE tenant_id=:t AND conversation_id=:c"),
                    {"t": TENANT_ID, "c": conv_id},
                )).mappings().one()
            )
            assert src["payload_ref"] is None  # external receipt 后清 ref
            assert src["status"] == "suppressed"

        # ③ transport replay：ref-bearing 归 0 -> 放行 -> ACK。
        async with factory() as sess:
            rev = await _current_operation_revision(sess, op_id=op_id)
            await WorkspaceTransportErasureParticipant(sess).erase_transport_owner(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=rev,
            )
            await sess.commit()
        async with factory() as check:
            tp_cp = (
                (await check.execute(
                    text("SELECT state FROM metaedu.agent_conversation_purge_owners "
                         "WHERE purge_operation_id=:op AND owner_key=:o"),
                    {"op": op_id, "o": WORKSPACE_TRANSPORT_OWNER},
                )).scalar_one()
            )
            assert tp_cp == PurgeOwnerState.ACKED.value
    finally:
        await engine.dispose()
# F-6 R1-AC10：日志/operation/checkpoint 脱敏
# ---------------------------------------------------------------------------


async def test_external_redaction_ref_identity_only(monkeypatch, session_factory):
    """F-6 R1-AC10（external 真实路径）：external ref sentinel 穿过 external participant
    —— operation/checkpoint/fence 不含 ref sentinel；external ledger 仅允许 ref_value
    身份例外（E-1 唯一事实源）；reason 落冻结 code 集合。"""
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            await _seed_workspace_outbox_ref(seed, conv_id, ref_value=_EXTERNAL_REF_SENTINEL)
            op_id, _ = await _ext_make_purge_operation(seed, conv_id, purge_rev)
            await seed.commit()

        async with factory() as sess:
            await _ext_participant(sess, _ExternalTimeoutAdapter()).erase_external_payload(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=1,
            )
            await sess.commit()

        async with factory() as check:
            op = (
                (await check.execute(
                    text("SELECT failure_code FROM metaedu.agent_conversation_purges WHERE id=:op"),
                    {"op": op_id},
                )).mappings().one()
            )
            cp = await _checkpoint_state(check, purge_operation_id=op_id)
            fence = (
                (await check.execute(
                    text("SELECT ingress_digest FROM metaedu.agent_erasure_fences "
                         "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"),
                    {"t": TENANT_ID, "c": conv_id, "o": EXTERNAL_PAYLOAD_OWNER},
                )).mappings().one()
            )
            ledger = (
                (await check.execute(
                    text("SELECT ref_value, blocked_reason FROM metaedu.agent_external_object_refs "
                         "WHERE tenant_id=:t AND conversation_id=:c"),
                    {"t": TENANT_ID, "c": conv_id},
                )).mappings().one()
            )

        assert _EXTERNAL_REF_SENTINEL not in str(op) + str(cp) + str(fence)
        assert ledger["ref_value"] == _EXTERNAL_REF_SENTINEL  # 身份例外
        # ledger blocked_reason 落冻结 code 集合（禁自由文本 reason）。
        assert ledger["blocked_reason"] in (
            "outcome_unknown",
            "erase_timeout",
            "adapter_unavailable",
            "unknown_scheme",
            None,
        ), ledger["blocked_reason"]
        assert cp["reason_code"] in (
            "purge_blocked_by_external_outcome_unknown",
            "purge_blocked_by_external_erase_timeout",
            "purge_blocked_by_external_adapter_unavailable",
            "purge_blocked_by_external_ref_scan_nonzero",
        ), cp["reason_code"]
    finally:
        await engine.dispose()


async def test_transport_redaction_no_body_in_metadata(session_factory):
    """F-6 R1-AC10（transport 真实路径）：正文 sentinel 穿过 transport participant
    （outbox inline body）——transport 清除正文后 operation/checkpoint/fence 不含 body
    sentinel；outbox 正文被清除（转 suppressed）。"""
    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _transport_seed_conversation(
                seed, owner=WORKSPACE_TRANSPORT_OWNER,
            )
            await _seed_transport_outbox(
                seed, conversation_id=conv_id, side="workspace",
                payload_inline={"body": _BODY_SENTINEL},
            )
            op_id, _ = await _transport_make_purge_operation(
                seed, conv_id, purge_rev, owner=WORKSPACE_TRANSPORT_OWNER,
            )
            await seed.commit()

        async with factory() as sess:
            await WorkspaceTransportErasureParticipant(sess).erase_transport_owner(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=1,
            )
            await sess.commit()

        async with factory() as check:
            op = (
                (await check.execute(
                    text("SELECT failure_code FROM metaedu.agent_conversation_purges WHERE id=:op"),
                    {"op": op_id},
                )).mappings().one()
            )
            cp = await _checkpoint_state(check, purge_operation_id=op_id)
            fence = (
                (await check.execute(
                    text("SELECT ack_digest FROM metaedu.agent_erasure_fences "
                         "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"),
                    {"t": TENANT_ID, "c": conv_id, "o": WORKSPACE_TRANSPORT_OWNER},
                )).mappings().one()
            )
            outbox = (
                (await check.execute(
                    text("SELECT payload_inline, status FROM metaedu.agent_workspace_outbox "
                         "WHERE tenant_id=:t AND conversation_id=:c"),
                    {"t": TENANT_ID, "c": conv_id},
                )).mappings().one()
            )

        assert _BODY_SENTINEL not in str(op) + str(cp) + str(fence)
        assert outbox["payload_inline"] is None  # 正文被清除
        assert outbox["status"] == "suppressed"
    finally:
        await engine.dispose()


async def test_runtime_redaction_no_ref_in_metadata(monkeypatch, session_factory):
    """F-6 R1-AC10（runtime 真实路径）：runtime ref sentinel 穿过 runtime participant
    （binding runtime_session_ref）——operation/checkpoint/fence 不含 runtime ref
    sentinel；binding 落 invalid（timeout 保留 ref）。"""
    _enable_runtime_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            now = datetime.now(UTC).replace(tzinfo=None)
            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                    "revision, created_at, updated_at) "
                    "VALUES (:t, :c, :o, 1, 'active', 1, 0, '{}'::jsonb, "
                    ":ed, 1, :now, :now) ON CONFLICT DO NOTHING"
                ),
                {
                    "t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER,
                    "ed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "now": now,
                },
            )
            await _seed_runtime_binding(seed, conv_id, ref_value=_RUNTIME_REF_SENTINEL)
            op_id, _ = await _runtime_make_purge_operation(seed, conv_id, purge_rev)
            await seed.commit()

        async with factory() as sess:
            await _runtime_participant(sess, _RuntimeTimeoutAdapter()).erase_runtime_session(
                tenant_id=TENANT_ID, conversation_id=conv_id, purge_revision=purge_rev,
                purge_operation_id=op_id, expected_operation_revision=1,
            )
            await sess.commit()

        async with factory() as check:
            op = (
                (await check.execute(
                    text("SELECT failure_code FROM metaedu.agent_conversation_purges WHERE id=:op"),
                    {"op": op_id},
                )).mappings().one()
            )
            cp = await _checkpoint_state(check, purge_operation_id=op_id)
            fence = (
                (await check.execute(
                    text("SELECT ingress_digest FROM metaedu.agent_erasure_fences "
                         "WHERE tenant_id=:t AND conversation_id=:c AND owner_key=:o"),
                    {"t": TENANT_ID, "c": conv_id, "o": RUNTIME_PRIVATE_OWNER},
                )).mappings().one()
            )
            binding = (
                (await check.execute(
                    text("SELECT status FROM metaedu.agent_runtime_session_bindings "
                         "WHERE conversation_id=:c AND runtime_session_ref IS NOT NULL"),
                    {"c": conv_id},
                )).scalars().first()
            )

        assert _RUNTIME_REF_SENTINEL not in str(op) + str(cp) + str(fence)
        assert binding == "invalid"  # timeout 保留 ref
        assert cp["reason_code"] == "purge_blocked_by_runtime_outcome_unknown", cp
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6 D6：partial ACK 负向（任一 owner 未 ACK -> operation 不 completed）
# ---------------------------------------------------------------------------


async def test_partial_ack_operation_not_completed(monkeypatch, session_factory):
    """F-6 D6 负向（owner-scoped）：external ACK、runtime **未调用**（pending 保持）。

    架构裁决后：completed 正向判定归 S5，本测试只断 owner-scoped——external checkpoint
    acked + runtime checkpoint 仍 pending（部分 owner ACK 不构成该 owner 的 acked）。
    **不断** operation.completed（S5 reducer 职责）。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            await _seed_workspace_outbox_ref(seed, conv_id)
            # op 同时登记 external + runtime 两个 owner checkpoint。
            op_id = uuid.uuid4()
            now = datetime.now(UTC).replace(tzinfo=None)
            from app.composition.agent_erasure_registry import capability_digest as _cd
            from app.composition.agent_erasure_registry import registry_digest as _rd
            from tests.composition.test_s4eb2_external_erasure import (
                _registry_snapshot_json as _ext_snapshot,
            )

            await seed.execute(
                text(
                    "INSERT INTO metaedu.agent_conversation_purges "
                    "(id, tenant_id, conversation_id, purge_revision, state, registry_digest, "
                    "registry_snapshot, retention_policy_snapshot, retention_policy_digest, "
                    "hold_revision_snapshot, lease_epoch, scheduled_at, revision, "
                    "created_at, updated_at) "
                    "VALUES (:id, :t, :c, :r, 'scheduled', :rd, :rs, :rps, :rpd, "
                    "0, 0, :now, 1, :now, :now)"
                ),
                {
                    "id": op_id,
                    "t": TENANT_ID,
                    "c": conv_id,
                    "r": purge_rev,
                    "rd": _rd(),
                    "rs": _ext_snapshot(),
                    "rps": '{"conversation_recovery_days": 30}',
                    "rpd": "e" * 64,
                    "now": now,
                },
            )
            for owner_key in (EXTERNAL_PAYLOAD_OWNER, RUNTIME_PRIVATE_OWNER):
                await seed.execute(
                    text(
                        "INSERT INTO metaedu.agent_conversation_purge_owners "
                        "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
                        "capability_digest, state, attempt, created_at, updated_at) "
                        "VALUES (:id, :t, :op, :o, 1, :cd, 'pending', 0, :now, :now)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": TENANT_ID,
                        "op": op_id,
                        "o": owner_key,
                        "cd": _cd(owner_key),
                        "now": now,
                    },
                )
            await seed.commit()

        # 只跑 external（runtime 保持 pending）。
        async with factory() as sess:
            await _ext_participant(sess, _ExternalSuccessAdapter()).erase_external_payload(
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=purge_rev,
                purge_operation_id=op_id,
                expected_operation_revision=1,
            )
            await sess.commit()

        async with factory() as check:
            # 已 ACK owner acked、未 ACK owner 保持 pending（owner-scoped）。
            states = (
                (await check.execute(
                    text(
                        "SELECT owner_key, state FROM "
                        "metaedu.agent_conversation_purge_owners "
                        "WHERE purge_operation_id = :op ORDER BY owner_key"
                    ),
                    {"op": op_id},
                ))
                .mappings()
                .all()
            )
            by_owner = {r["owner_key"]: r["state"] for r in states}
            assert by_owner[EXTERNAL_PAYLOAD_OWNER] == PurgeOwnerState.ACKED.value
            assert by_owner[RUNTIME_PRIVATE_OWNER] == PurgeOwnerState.PENDING.value
    finally:
        await engine.dispose()
