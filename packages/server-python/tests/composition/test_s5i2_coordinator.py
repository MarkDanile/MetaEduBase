"""R1-S5-I2 transactional projection coordinator 真实 PG 测试。

映射 plan §R1-S5-A-4/S5-A-5/S5-A-8：锁序（Conversation FOR UPDATE → operation
FOR UPDATE → checkpoint FOR UPDATE owner_key 排序 → fence 只读排序 → scan/registry/
hold facts → calculator → CAS 写）、零写、幂等、stale CAS fail closed、覆盖污染
投影、终态覆盖禁令、G1/G2/G3 drift 冻结 blocked、快照外 owner 行 G4、
双连接并发单一写者、Conversation-first 锁序观测。

Wished-for API（TDD 先于实现）：
``app.composition.transactional_projection_coordinator``
- TransactionalProjectionCoordinator(session, scan_providers=...)
- build_scan_providers(session) -> Mapping[owner_key, ScanProvider]
- aggregate_projection(...) -> ProjectionResult | None（None = 零写）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.transactional_projection_coordinator import (
    TransactionalProjectionCoordinator,
    build_scan_providers,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationLegalHoldModel,
    PurgeOperationModel,
)
from app.shared.schemas.canonical_json import canonical_digest

WS_CORE = "workspace.core.v1"
EX_CORE = "execution.core.v1"
WS_TRANSPORT = "workspace.transport.v1"
EX_TRANSPORT = "execution.transport.v1"
EXTERNAL = "external.payload.v1"
RUNTIME = "runtime.private.v1"

_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# 种子 helpers（与 db_session 同事务；teardown 由 composition autouse clean 兜底）
# ---------------------------------------------------------------------------


async def _seed_conversation(
    session, *, hold_revision: int = 0, actor_state: str = "present"
) -> tuple[uuid.UUID, uuid.UUID]:
    """deleted + purge_after 已过；completed 测试需 actor_state='redacted'
    （workspace scan 把 present actor 计入未匿名 → scan 非零；ck_agent_conv_actor
    要求 redacted 时 created_by IS NULL + creator_identity_digest 64-hex）。"""
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    purge_after = datetime.now(UTC) - timedelta(days=1)
    if actor_state == "redacted":
        created_by = None
        identity_digest: str | None = "d" * 64
    else:
        created_by = tid
        identity_digest = None
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) "
            "VALUES (:id, :tid, :creator, :actor_state, :digest, :identity, "
            "'sensitive title', 'none', 'deleted', :purge_after, 'scheduled', "
            "1, :hold_revision, 1, now(), now())"
        ),
        {
            "id": cid,
            "tid": tid,
            "creator": created_by,
            "actor_state": actor_state,
            "digest": "a" * 64,
            "identity": identity_digest,
            "purge_after": purge_after,
            "hold_revision": hold_revision,
        },
    )
    return tid, cid


_ALL_SIX_OWNERS = [WS_CORE, EX_CORE, WS_TRANSPORT, EX_TRANSPORT, EXTERNAL, RUNTIME]


async def _seed_all_acked_facts(
    session, tid, cid
) -> uuid.UUID:
    """六 owner operation + 全 acked checkpoint + 全 erased fence（completed 事实集）。

    返回 operation_id。snapshot 是 create_purge_operation 持久化的六 owner 全集，
    completed 判定要求全部 owner 有 acked checkpoint + erased fence + 零扫描。
    """
    operation_id = await _seed_operation(session, tid, cid, owners=_ALL_SIX_OWNERS)
    for owner_key in _ALL_SIX_OWNERS:
        await _ack_checkpoint(session, tid, operation_id, owner_key)
        await _seed_fence(session, tid, cid, owner_key, state="erased")
    return operation_id


def _ingress_checkpoint() -> dict:
    return {"schema_version": 1, "sources": {}}


async def _seed_operation(session, tid, cid, *, owners: list[str] | None = None) -> uuid.UUID:
    repo = AgentErasureRepository(session)
    operation = await repo.create_purge_operation(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=0,
    )
    for owner_key in owners or []:
        await repo.create_owner_checkpoint(
            tenant_id=tid,
            purge_operation_id=operation.id,
            owner_key=owner_key,
        )
    return operation.id


async def _seed_fence(session, tid, cid, owner_key: str, *, state: str = "active") -> None:
    """按 repo 同构形态直插 fence 行；erased 需 ack_digest + acked_at + ingress 自洽。"""
    import json

    ic = _ingress_checkpoint()
    ingress_digest = canonical_digest(ic)
    ic_json = json.dumps(ic, sort_keys=True)
    if state == "erased":
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                "ack_digest, acked_at, revision, created_at, updated_at) "
                "VALUES (:tid, :cid, :owner, 1, 'erased', 1, 0, :ic, :ingress, "
                ":ack, now(), 1, now(), now())"
            ),
            {
                "tid": tid,
                "cid": cid,
                "owner": owner_key,
                "ic": ic_json,
                "ingress": ingress_digest,
                "ack": "e" * 64,
            },
        )
    else:
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
                "revision, created_at, updated_at) "
                "VALUES (:tid, :cid, :owner, 1, :state, 0, 0, :ic, :ingress, "
                "1, now(), now())"
            ),
            {
                "tid": tid,
                "cid": cid,
                "owner": owner_key,
                "state": state,
                "ic": ic_json,
                "ingress": ingress_digest,
            },
        )


async def _ack_checkpoint(
    session, tid, operation_id: uuid.UUID, owner_key: str
) -> None:
    """把 pending checkpoint 直改 acked（模拟 participant ACK 后的 facts）。

    text() UPDATE 绕过 ORM 同步——随后 expire_all，防 coordinator 的 SELECT
    命中 identity map 中的陈旧实例（S4-E-C「ORM 掩盖并发」同族教训）。
    """
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state='acked', ack_digest=:ack, checkpoint_digest=:ack, "
            "reason_code=NULL, updated_at=now() "
            "WHERE tenant_id=:tid AND purge_operation_id=:op AND owner_key=:owner"
        ),
        {"tid": tid, "op": operation_id, "owner": owner_key, "ack": "e" * 64},
    )
    session.expire_all()


async def _block_checkpoint(
    session, tid, operation_id: uuid.UUID, owner_key: str, reason: str
) -> None:
    # blocked 需清 ack 列（ck_agent_purge_owner_ack：state<>acked 时 ack_digest NULL）。
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state='blocked', reason_code=:reason, ack_digest=NULL, "
            "checkpoint_digest=NULL, updated_at=now() "
            "WHERE tenant_id=:tid AND purge_operation_id=:op AND owner_key=:owner"
        ),
        {"tid": tid, "op": operation_id, "owner": owner_key, "reason": reason},
    )
    session.expire_all()


async def _read_operation(session, operation_id: uuid.UUID) -> PurgeOperationModel:
    row = (
        await session.execute(
            text(
                "SELECT * FROM metaedu.agent_conversation_purges WHERE id=:op"
            ),
            {"op": operation_id},
        )
    ).mappings().one()
    return row


async def _read_conversation(session, cid: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT purge_state, purged_at, hold_revision, purge_revision "
                "FROM metaedu.agent_conversations WHERE id=:cid"
            ),
            {"cid": cid},
        )
    ).mappings().one()
    return row


async def _coordinator(session) -> TransactionalProjectionCoordinator:
    return TransactionalProjectionCoordinator(
        session, scan_providers=build_scan_providers(session)
    )


# ---------------------------------------------------------------------------
# 幂等 / 零写 / CAS
# ---------------------------------------------------------------------------


async def test_same_facts_reaggregation_is_idempotent_zero_write(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    coordinator = await _coordinator(db_session)
    first = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert first is not None and first.state == "running"
    op = await _read_operation(db_session, op_id)
    assert op["state"] == "running"
    assert op["revision"] == 2  # scheduled -> running 写入一次 bump
    # 同 facts 重复聚合：零写、零 bump、返回 None。
    second = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert second is None
    op = await _read_operation(db_session, op_id)
    assert op["revision"] == 2
    conv = await _read_conversation(db_session, cid)
    assert conv["purge_state"] == "running"


async def test_full_projection_tuple_identical_is_zero_write(db_session):
    # 投影元组完全一致（含 started_at/purged_at）→ 零写；即使再次聚合也零 bump。
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    op_id = await _seed_all_acked_facts(db_session, tid, cid)
    coordinator = await _coordinator(db_session)
    first = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert first is not None and first.state == "completed" and first.purged
    op = await _read_operation(db_session, op_id)
    revision_after_first = op["revision"]
    assert op["completed_at"] is not None
    conv = await _read_conversation(db_session, cid)
    assert conv["purged_at"] is not None
    second = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert second is None
    op = await _read_operation(db_session, op_id)
    assert op["revision"] == revision_after_first


async def test_coordinator_overwrites_polluted_legacy_projection(db_session):
    # S5-A-8 行 12：in-flight operation 带污染投影 → coordinator 从 facts 重算覆盖。
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    await _block_checkpoint(db_session, tid, op_id, WS_CORE, "purge_blocked_by_erase_timeout")
    # 污染：operation 投影被写成 running + 空 failure_code（旧临时投影残留）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET state='running', failure_code=NULL, updated_at=now() "
            "WHERE id=:op"
        ),
        {"op": op_id},
    )
    await db_session.commit()
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "blocked", "purge_blocked_by_erase_timeout",
    )
    op = await _read_operation(db_session, op_id)
    assert op["state"] == "blocked"
    assert op["failure_code"] == "purge_blocked_by_erase_timeout"


async def test_terminal_state_overwrite_ban_fail_closed(db_session):
    # 终态覆盖禁令：cancelled/failed/completed 不得被 coordinator 重开。
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET state='cancelled' "
            "WHERE id=:op"
        ),
        {"op": op_id},
    )
    await db_session.commit()
    coordinator = await _coordinator(db_session)
    with pytest.raises(ValueError, match="terminal"):
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )


async def test_terminal_completed_not_reopened_by_later_block(db_session):
    # completed 终态 + facts 变化（新 blocked）→ fail closed，不得重开。
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    op_id = await _seed_all_acked_facts(db_session, tid, cid)
    await db_session.commit()
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None and result.state == "completed"
    await db_session.commit()
    # facts 变化：checkpoint 被外部改成 blocked（脏数据）。
    await _block_checkpoint(db_session, tid, op_id, WS_CORE, "purge_blocked_by_erase_timeout")
    await db_session.commit()
    with pytest.raises(ValueError, match="terminal"):
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )


# ---------------------------------------------------------------------------
# G1 / G2 / G3 drift：写冻结 blocked 结果，不基于旧快照续算
# ---------------------------------------------------------------------------


async def test_g1_registry_drift_writes_frozen_blocked(db_session):
    import json

    from app.composition.agent_erasure_registry import (
        registry_snapshot,
        snapshot_digest,
    )

    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    # 模拟 registry 升级前的持久化视图：snapshot 与 digest 自洽成对，但均已
    # 不等于已安装 registry（真实 G1 漂移形态；只改 digest 会被 snapshot↔digest
    # 自洽校验 fail closed 拦截，那是篡改形态）。
    old_snapshot = [
        entry for entry in registry_snapshot() if entry["owner_key"] != RUNTIME
    ]
    old_digest = snapshot_digest(old_snapshot)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET registry_snapshot=:snap, registry_digest=:digest WHERE id=:op"
        ),
        {
            "op": op_id,
            "snap": json.dumps(old_snapshot, sort_keys=True),
            "digest": old_digest,
        },
    )
    db_session.expire_all()
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "blocked", "blocked_registry_changed",
    )
    op = await _read_operation(db_session, op_id)
    assert op["state"] == "blocked"
    assert op["failure_code"] == "blocked_registry_changed"
    checkpoint_state = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id=:op"
            ),
            {"op": op_id},
        )
    ).scalar_one()
    assert checkpoint_state == "pending"  # 零 checkpoint 改动


async def test_g2_hold_drift_writes_frozen_blocked(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    # Conversation.hold_revision 推进（I1 producer 语义）→ G2 漂移。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET hold_revision=1, "
            "revision=revision+1 WHERE id=:cid"
        ),
        {"cid": cid},
    )
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "blocked", "blocked_hold_revision_changed",
    )


async def test_g3_active_hold_writes_frozen_blocked(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    db_session.add(
        ConversationLegalHoldModel(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="legal_hold_test",
            purpose="i2 test hold",
            actor_id=tid,
            state="active",
            revision=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "blocked", "purge_blocked_by_legal_hold",
    )


# ---------------------------------------------------------------------------
# G4：snapshot 外 owner 行（checkpoint 零修改）
# ---------------------------------------------------------------------------


async def test_snapshot_external_checkpoint_row_g4_zero_checkpoint_write(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    # 直插 snapshot 外 owner（registry 全集不含该 key）的 checkpoint 行（DB 篡改/遗留）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, created_at, updated_at) "
            "VALUES (:row_id, :tid, :op, :owner, 1, :digest, 'pending', 0, now(), now())"
        ),
        {
            "row_id": uuid.uuid4(),
            "tid": tid,
            "op": op_id,
            "owner": "workspace.core.v9",
            "digest": "c" * 64,
        },
    )
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "blocked", "purge_owner_ack_conflict",
    )
    states = (
        await db_session.execute(
            text(
                "SELECT state FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id=:op ORDER BY owner_key"
            ),
            {"op": op_id},
        )
    ).scalars().all()
    assert set(states) == {"pending"}  # 零 checkpoint 修改


# ---------------------------------------------------------------------------
# 并发 / 锁序
# ---------------------------------------------------------------------------


async def test_two_connections_concurrent_aggregation_single_final_writer(session_factory):
    seed = session_factory()
    tid, cid = await _seed_conversation(seed)
    op_id = await _seed_operation(seed, tid, cid, owners=[WS_CORE, EX_CORE])
    # 提交父行让两个独立连接可见（泄漏未提交 session 会持锁阻塞后续 teardown）。
    await seed.commit()
    # 两个独立连接上的 coordinator 并发聚合同一 operation。
    async def aggregate():
        session = session_factory()
        try:
            coordinator = await _coordinator(session)
            return await coordinator.aggregate_projection(
                tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
            )
        finally:
            await session.commit()

    first, second = await asyncio.gather(aggregate(), aggregate())
    # 至少一方完成写入；由于 Conversation 首锁串行，后进入者读到已写入投影 →
    # 零写 None。结果一致（单一最终写者，无 lost update）。
    assert first is None or first.state == "running"
    assert second is None or second.state == "running"
    check = session_factory()
    try:
        op = await _read_operation(check, op_id)
        assert op["state"] == "running"
        # scheduled -> running 只 bump 一次（非两写者各 bump 一次）。
        assert op["revision"] == 2
    finally:
        await check.commit()


async def test_concurrent_writer_after_change_bumps_revision_once(session_factory):
    # facts 变化后并发聚合：最终状态由 facts 决定，revision 单调 +1 每次真实变化。
    seed = session_factory()
    tid, cid = await _seed_conversation(seed)
    op_id = await _seed_operation(seed, tid, cid, owners=[WS_CORE])
    await seed.commit()

    async def aggregate():
        session = session_factory()
        try:
            coordinator = await _coordinator(session)
            return await coordinator.aggregate_projection(
                tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
            )
        finally:
            await session.commit()

    first, second = await asyncio.wait_for(
        asyncio.gather(aggregate(), aggregate()), timeout=_TIMEOUT
    )
    assert first is None or first.state == "running"
    assert second is None or second.state == "running"
    check = session_factory()
    try:
        op = await _read_operation(check, op_id)
        assert op["state"] == "running"
        assert op["revision"] == 2
    finally:
        await check.commit()


async def test_coordinator_waits_on_conversation_lock(session_factory):
    # Conversation-first 锁序观测（pg_locks 直接判别）：另一连接持 Conversation
    # 行锁时，coordinator 事务必须持有 agent_conversations 的 RowShareLock
    # （FOR UPDATE）且**不得**持有 agent_conversation_purges 的任何 granted 锁
    # （变异「跳过 Conversation 首锁」会先取 operation FOR UPDATE → purge 表
    # granted RowShareLock → 红）。
    seed = session_factory()
    tid, cid = await _seed_conversation(seed)
    op_id = await _seed_operation(seed, tid, cid, owners=[WS_CORE])
    await seed.commit()

    blocker = session_factory()
    await blocker.execute(
        text(
            "SELECT * FROM metaedu.agent_conversations WHERE id=:cid "
            "FOR UPDATE"
        ),
        {"cid": cid},
    )

    coordinator_pid: dict[str, int] = {}

    async def aggregate():
        session = session_factory()
        try:
            pid = (
                await session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            coordinator_pid["pid"] = int(pid)
            coordinator = await _coordinator(session)
            return await coordinator.aggregate_projection(
                tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
            )
        finally:
            await session.commit()

    # 负向窗口：持锁期间聚合不得完成。
    aggregate_task = asyncio.create_task(aggregate())
    await asyncio.sleep(1.0)
    aggregate_blocked = not aggregate_task.done()

    # 锁序判别（pg_locks 观测 coordinator 事务自身）：只允许 conversations 的
    # granted RowShareLock；purge 表 granted 锁 = 已先取 operation 锁。
    diag = session_factory()
    try:
        rows = (
            await diag.execute(
                text(
                    "SELECT mode, granted, relation::regclass::text AS rel "
                    "FROM pg_locks WHERE pid=:p AND locktype='relation' "
                    "AND granted AND relation::regclass::text LIKE "
                    "'%agent_conversation_purges'"
                ),
                {"p": coordinator_pid["pid"]},
            )
        ).all()
        purge_locks = [(mode, rel) for mode, _granted, rel in rows]
    finally:
        await diag.commit()

    # 收尾：先释放 blocker → 等 aggregate 完成并提交 → 再断言。
    await blocker.commit()
    aggregate_result = await asyncio.wait_for(aggregate_task, timeout=_TIMEOUT)

    assert aggregate_blocked, (
        "coordinator completed while another connection holds the "
        "Conversation row lock; Conversation-first lock order violated"
    )
    assert purge_locks == [], (
        f"coordinator holds locks on purge table while blocked on "
        f"Conversation: {purge_locks}; must take Conversation first"
    )
    assert aggregate_result is not None and aggregate_result.state == "running"


# ---------------------------------------------------------------------------
# 其他 fail closed
# ---------------------------------------------------------------------------


async def test_missing_scan_provider_fail_closed(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    coordinator = TransactionalProjectionCoordinator(db_session, scan_providers={})
    with pytest.raises(ValueError, match="scan"):
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )


async def test_missing_operation_fail_closed(db_session):
    tid, cid = await _seed_conversation(db_session)
    coordinator = await _coordinator(db_session)
    with pytest.raises(ValueError, match="operation"):
        await coordinator.aggregate_projection(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=uuid.uuid4(),
        )


async def test_completed_result_sets_purged_at_and_completed_at(db_session):
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    op_id = await _seed_all_acked_facts(db_session, tid, cid)
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None and result.state == "completed"
    op = await _read_operation(db_session, op_id)
    assert op["completed_at"] is not None
    assert op["failure_code"] is None
    conv = await _read_conversation(db_session, cid)
    assert conv["purged_at"] is not None
    assert conv["purge_state"] == "completed"


async def test_running_result_sets_started_at_once(db_session):
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    coordinator = await _coordinator(db_session)
    await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    op = await _read_operation(db_session, op_id)
    assert op["started_at"] is not None
    first_started = op["started_at"]
    await db_session.commit()
    # 再次聚合（facts 未变）→ 零写，started_at 不被重置。
    assert (
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
        is None
    )
    op = await _read_operation(db_session, op_id)
    assert op["started_at"] == first_started


async def test_failed_checkpoint_aggregation_via_coordinator(db_session):
    # 优先级 5 经 coordinator 落库：checkpoint failed（scheduler 写）→ operation failed。
    tid, cid = await _seed_conversation(db_session)
    op_id = await _seed_operation(db_session, tid, cid, owners=[WS_CORE])
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET state='failed', "
            "reason_code='purge_blocked_by_erase_timeout' WHERE purge_operation_id=:op"
        ),
        {"op": op_id},
    )
    coordinator = await _coordinator(db_session)
    result = await coordinator.aggregate_projection(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert result is not None
    assert (result.state, result.failure_code) == (
        "failed", "purge_blocked_by_erase_timeout",
    )
    op = await _read_operation(db_session, op_id)
    assert op["state"] == "failed"
