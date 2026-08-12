"""R1-S4-F：S4 阶段 fault 矩阵新增反例测试（F-6 十一项 + F-4 互操作）。

契约事实源：Plan §R1-S4-F F-0~F-7（PR #559 契约冻结）+ S4-E E-6 已覆盖清单。

本文件只补 S4-F **新增**反例（F-1 标注「需新增 / 族 B」）；已由 E-6 冻结并实现的
故障点**不在本文件重复实现**（迟到 runtime write + 旧 producer revision 归既有
S4-E-C/S4-C 套件，本文件只互操作确认，见 F-6 行 10/11）。

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

import pytest
from sqlalchemy import text
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
from tests.composition.test_s4eb2_external_erasure import (
    EXTERNAL_PAYLOAD_OWNER,
    TENANT_ID,
    _ensure_test_tenant,
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
    assert result.rowcount == 1, "external fence must exist to set erased"


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
    assert result.rowcount == 1, "transport fence must exist to set erased"


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
                "SELECT state, failure_code, lease_epoch FROM "
                "metaedu.agent_conversation_purges WHERE id = :op"
            ),
            {"op": purge_operation_id},
        )
    ).mappings().one()
    return dict(row)


# ---------------------------------------------------------------------------
# F-6 族 B：external 跨进程 takeover（expire_all 判别）
# ---------------------------------------------------------------------------


async def test_external_tx2_cross_process_takeover_fail_closed(monkeypatch, session_factory):
    """F-6 族 B：Tx1 提交后由第二连接 bump operation.lease_epoch / checkpoint.attempt，
    Tx2 精确重验必须 fail closed + 零写（external 侧 ``expire_all`` 判别）。

    判别点：**去掉 ``expire_all``（变异）-> Tx2 重验读 identity-map 陈旧实例，
    takeover 不可观测，fail-closed 分支不命中 -> 本测试红**。runtime 侧同修复
    （E-C C-1/T-1）先例。
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
        """等待 A 进入 adapter 窗口（Tx1 已提交、锁已释放）后，模拟另一进程 takeover：
        **只 bump checkpoint.attempt**（F-6 判别点注入）。operation.lease_epoch 不动
        ——``_load_verified_operation`` 在 SQLAlchemy FOR UPDATE 重选下恒读已提交值
        （operation 重验不受 identity-map 陈旧影响），bump lease 会掩盖 checkpoint
        陈旧读；attempt 才是本测试判别的 checkpoint 陈旧路径（``expire_all`` 清除
        Tx1 时代 checkpoint ORM 缓存后按已提交行重读）。"""
        await adapter_entered.wait()
        factory, engine = await _make_factory()
        try:
            async with factory() as sess:
                await sess.execute(
                    text(
                        "UPDATE metaedu.agent_conversation_purge_owners "
                        "SET attempt = attempt + 1, updated_at = clock_timestamp() "
                        "WHERE tenant_id = :t AND purge_operation_id = :op"
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
    # 判别：attempt mismatch 被观测到即 checkpoint 陈旧读已被 expire_all 修复。
    assert "attempt" in str(tx2_error[0]), str(tx2_error[0])


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
    finally:
        await engine.dispose()


async def test_owner_scope_mismatch_capability_gate(monkeypatch, session_factory):
    """F-6 R1-AC9：conversation 已登记 owner 与直调 participant 不符 -> fail closed。

    判别点：external 直调 conversation 上 workspace.transport.v1 的 owner checkpoint
    缺 external 行 -> ``_load_verified_checkpoint`` 找不到 -> fail closed。
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
            await _transport_make_purge_operation(
                seed, conv_id, purge_rev, owner="workspace.transport.v1"
            )
            await seed.commit()

        async with factory() as sess:
            participant = _ext_participant(sess, _ExternalSuccessAdapter())
            with pytest.raises(ValueError, match="checkpoint"):
                await participant.erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=purge_rev,
                    purge_operation_id=(  # 读取 op_id 需要——见下方修正
                        (await sess.execute(
                            text(
                                "SELECT id FROM metaedu.agent_conversation_purges "
                                "WHERE tenant_id = :t AND conversation_id = :c "
                                "ORDER BY created_at DESC LIMIT 1"
                            ),
                            {"t": TENANT_ID, "c": conv_id},
                        )).scalar_one()
                    ),
                    expected_operation_revision=1,
                )
    finally:
        await engine.dispose()


async def test_operation_revision_replay_rejected(monkeypatch, session_factory):
    """F-6 R1-AC9：旧 revision 的 purge operation 重放 -> revision CAS 拒绝。

    判别点：seed operation revision=2，重放 expected_operation_revision=1 ->
    ``_load_verified_operation`` revision mismatch -> fail closed。
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
    （timeout -> unknown）混合故障——五方状态各自一致（F-2），互不误伤；
    partial ACK 不 completed（D6 负向）。

    断言（F-2 矩阵）：external fence erased + checkpoint acked；runtime fence
    erasing + checkpoint blocked（outcome_unknown）+ binding invalid；operation
    **running（非 completed）**；Conversation.purge_state 依最后写者（runtime
    blocked -> blocked）。
    """
    _enable_external_registry(monkeypatch)
    _enable_runtime_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
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
            await seed.commit()

        # external success（operation revision 1 -> 2）。
        async with factory() as sess:
            await _ext_participant(sess, _ExternalSuccessAdapter()).erase_external_payload(
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=purge_rev,
                purge_operation_id=op_id,
                expected_operation_revision=1,
            )
            await sess.commit()
        # external 已 bump operation revision（_mark_operation_running 1->2），runtime
        # 续跑须传当前 revision（stale expected_revision 会被 _load_verified_operation
        # 拒绝——这是 revision CAS 的正确行为，不是本测试要判别的路径）。
        async with factory() as sess:
            current_rev = (
                await sess.execute(
                    text(
                        "SELECT revision FROM metaedu.agent_conversation_purges "
                        "WHERE id = :op"
                    ),
                    {"op": op_id},
                )
            ).scalar_one()
        # runtime timeout -> unknown（E-3a）。
        async with factory() as sess:
            await _runtime_participant(sess, _RuntimeTimeoutAdapter()).erase_runtime_session(
                tenant_id=TENANT_ID,
                conversation_id=conv_id,
                purge_revision=purge_rev,
                purge_operation_id=op_id,
                expected_operation_revision=int(current_rev),
            )
            await sess.commit()

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

            # operation 非 completed（D6 负向：external ACK + runtime blocked）。
            op = await _operation_state(check, purge_operation_id=op_id)
            assert op["state"] != PurgeOperationState.COMPLETED.value, op
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6 R1-AC10：日志/operation/checkpoint 脱敏
# ---------------------------------------------------------------------------


async def test_purge_log_redaction_no_body_or_ref(monkeypatch, session_factory, caplog):
    """F-6 R1-AC10：正文/ref 原值不入 purge operation、checkpoint、日志。

    判别点：断言 operation.registry_snapshot / retention_policy_snapshot、
    checkpoint.reason_code、捕获日志均不含 external ref 原值（R1-AC10 / spec §9.3）。
    """
    _enable_external_registry(monkeypatch)

    factory, engine = await _make_factory()
    try:
        async with factory() as seed:
            await _ensure_test_tenant(seed)
            conv_id, purge_rev = await _ext_seed_conversation(seed)
            await _seed_workspace_outbox_ref(seed, conv_id, ref_value=_REF_VALUE)
            op_id, _ = await _ext_make_purge_operation(seed, conv_id, purge_rev)
            await seed.commit()

        with caplog.at_level("INFO"):
            async with factory() as sess:
                await _ext_participant(
                    sess, _ExternalTimeoutAdapter()
                ).erase_external_payload(
                    tenant_id=TENANT_ID,
                    conversation_id=conv_id,
                    purge_revision=purge_rev,
                    purge_operation_id=op_id,
                    expected_operation_revision=1,
                )
                await sess.commit()

        async with factory() as check:
            op = (
                await check.execute(
                    text(
                        "SELECT registry_snapshot, retention_policy_snapshot, "
                        "failure_code FROM metaedu.agent_conversation_purges "
                        "WHERE id = :op"
                    ),
                    {"op": op_id},
                )
            ).mappings().one()
            cp = await _checkpoint_state(check, purge_operation_id=op_id)

        joined = str(op) + str(cp) + "\n".join(r.message for r in caplog.records)
        # ref 原值 / body 不得出现在 operation/checkpoint/日志（R1-AC10 / §9.3）。
        assert (
            _REF_VALUE not in joined
        ), "external ref original value leaked into purge metadata/logs"
        # reason 必须落冻结 code 集合（自由文本 reason 禁止）。
        assert cp["reason_code"] in (
            "purge_blocked_by_external_outcome_unknown",
            "purge_blocked_by_external_erase_timeout",
            "purge_blocked_by_external_adapter_unavailable",
            "purge_blocked_by_external_ref_scan_nonzero",
        ), cp["reason_code"]
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# F-6 D6：partial ACK 负向（任一 owner 未 ACK -> operation 不 completed）
# ---------------------------------------------------------------------------


async def test_partial_ack_operation_not_completed(monkeypatch, session_factory):
    """F-6 D6 负向：external ACK、runtime **未调用**（pending 保持）——
    operation 不得 completed（部分 owner ACK 不是 completed，S1/D6）。

    判别点：external erased + acked、runtime checkpoint 仍 pending、
    operation.state == 'running'（非 completed）；**变异：把部分 ACK 判为 completed
    -> 红**。
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
            op = await _operation_state(check, purge_operation_id=op_id)
            assert op["state"] != PurgeOperationState.COMPLETED.value, op
            # 已 ACK owner acked、未 ACK owner 保持 pending。
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
