"""R1-S1 schema / CAS / 并发 fence 唯一性 / backfill 真实 PostgreSQL 验证。

覆盖：
- 034 upgrade/downgrade/upgrade 往返与四张 coordination 表、新列、新 CHECK。
- tenant 复合键与 CAS。
- tombstone expand-only：正常未擦除写路径仍受强约束，tombstone 状态可表达。
- 并发创建同一 fence 的唯一性（真实 PostgreSQL）。
- baseline fence backfill 的幂等、分批、重启与 fail-closed。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_backfill import backfill_baseline_fences
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    UnknownOwnerError,
    capability_digest,
    owner_registry,
    registry_digest,
)
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from tests.conftest import TEST_DB_URL

SERVER_ROOT = Path(__file__).resolve().parents[2]
COORD_TABLES = {
    "agent_erasure_fences",
    "agent_conversation_purges",
    "agent_conversation_purge_owners",
    "agent_conversation_legal_holds",
}


def _db_url() -> str:
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _existing_coord_tables() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name = ANY($1::text[])",
            list(COORD_TABLES),
        )
        return {row["table_name"] for row in rows}
    finally:
        await connection.close()


async def _column_nullable(table: str, column: str) -> str:
    connection = await asyncpg.connect(_db_url())
    try:
        return await connection.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name=$1 AND column_name=$2",
            table,
            column,
        )
    finally:
        await connection.close()


async def _column_exists(table: str, column: str) -> bool:
    connection = await asyncpg.connect(_db_url())
    try:
        return bool(
            await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='metaedu' AND table_name=$1 AND column_name=$2)",
                table,
                column,
            )
        )
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# 迁移与 schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_034_coordination_tables_and_tombstone_columns_exist():
    assert await _existing_coord_tables() == COORD_TABLES
    # Conversation.hold_revision / Message.body_state / CompatibilityOutput.payload_state
    assert await _column_nullable("agent_conversations", "hold_revision") == "NO"
    assert await _column_nullable("agent_messages", "body_state") == "NO"
    assert (
        await _column_nullable("agent_compatibility_outputs", "payload_state") == "NO"
    )
    # tombstone expand：CompatibilityOutput 正文列放宽为 nullable。
    assert await _column_nullable("agent_compatibility_outputs", "reply_text") == "YES"
    assert (
        await _column_nullable("agent_compatibility_outputs", "response_envelope")
        == "YES"
    )


@pytest.mark.asyncio
async def test_purge_operation_stores_registry_snapshot_and_owner_capability():
    """PurgeOperation 必须保存排序 owner 列表（registry_snapshot）而不只是 digest；
    owner checkpoint 必须记录 owner_version 与 capability_digest，代码升级后可重建
    某次 ACK 对应的 owner capability（Spec §4 / §5）。"""
    assert await _column_exists("agent_conversation_purges", "registry_snapshot")
    assert await _column_exists("agent_conversation_purge_owners", "owner_version")
    assert await _column_exists("agent_conversation_purge_owners", "capability_digest")


@pytest.mark.asyncio
async def test_message_actor_tombstone_columns_exist():
    """Message actor tombstone：redacted 可清除 author_id，并保留不可逆
    actor_identity_digest（Spec §4 workspace.core.v1 actor_identity capability）。"""
    assert await _column_exists("agent_messages", "actor_identity_digest")


@pytest.mark.asyncio
async def test_conversation_actor_tombstone_columns_exist():
    """Conversation actor tombstone（评审 P1.2）：redacted 可清除 created_by，
    并保留不可逆 creator_identity_digest 与 actor_state（Spec §7.1）。"""
    assert await _column_exists("agent_conversations", "actor_state")
    assert await _column_exists("agent_conversations", "creator_identity_digest")
    # created_by 放宽为 nullable 以支持 redacted 清除。
    assert await _column_nullable("agent_conversations", "created_by") == "YES"


# ---------------------------------------------------------------------------
# 真实 PostgreSQL：fence / CAS / 并发 / tombstone
# ---------------------------------------------------------------------------


async def _insert_conversation(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> uuid.UUID:
    conversation_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, state, title_source, "
            " next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            " purge_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tenant, :actor, :digest, 'active', 'none', 1, 1, "
            " now(), 'not_scheduled', 0, 1, now(), now())"
        ),
        {
            "id": conversation_id,
            "tenant": tenant_id,
            "actor": uuid.uuid4(),
            "digest": "a" * 64,
        },
    )
    await session.flush()
    return conversation_id


async def _make_conversation(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    conversation_id = await _insert_conversation(db_session, tenant_id=tenant_id)
    return tenant_id, conversation_id


async def _make_conversation_with_tenant(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    return await _insert_conversation(db_session, tenant_id=tenant_id)


async def _make_purge_operation(
    db_session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, object]:
    """建立 tenant/conversation + 一个 purge operation，供 owner-checkpoint 反例复用。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    return tenant_id, conversation_id, purge


@pytest.mark.asyncio
async def test_fence_create_and_get_for_update(db_session):
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    fence = await repo.create_fence(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
    )
    assert fence.state is ErasureFenceState.ACTIVE
    assert fence.owner_version == 1
    assert len(fence.ingress_digest) == 64

    locked = await repo.get_fence_for_update(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
    )
    assert locked is not None
    assert locked.conversation_id == conversation_id


@pytest.mark.asyncio
async def test_fence_unknown_owner_fails_closed(db_session):
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    with pytest.raises(UnknownOwnerError):
        await repo.create_fence(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.unknown.v9",
        )


@pytest.mark.asyncio
async def test_fence_cas_conflict_and_erased_requires_ack(db_session):
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    fence = await repo.create_fence(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="execution.core.v1",
    )
    # erased 必须带 ack_digest
    with pytest.raises(ValueError):
        await repo.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
            expected_state=ErasureFenceState.ACTIVE,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=1,
            hold_revision=0,
            ack_digest=None,
        )
    # 错误 expected_revision -> CAS 冲突
    with pytest.raises(ValueError):
        await repo.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
            expected_state=ErasureFenceState.ACTIVE,
            expected_revision=fence.revision + 99,
            new_state=ErasureFenceState.ERASING,
            purge_revision=1,
            hold_revision=0,
        )
    # 正常 CAS：active -> erasing -> erased
    erasing = await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="execution.core.v1",
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASING,
        purge_revision=1,
        hold_revision=0,
    )
    erased = await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="execution.core.v1",
        expected_state=ErasureFenceState.ERASING,
        expected_revision=erasing.revision,
        new_state=ErasureFenceState.ERASED,
        purge_revision=1,
        hold_revision=0,
        ack_digest="b" * 64,
    )
    assert erased.state is ErasureFenceState.ERASED
    assert erased.ack_digest == "b" * 64
    assert erased.acked_at is not None


@pytest.mark.asyncio
async def test_multiple_active_legal_holds_are_detected(db_session):
    """同一 Conversation 可存在多个 active hold；has_active_legal_hold 必须用
    EXISTS 语义返回 True，不得因多行抛 MultipleResultsFound。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    actor = uuid.uuid4()
    await repo.create_legal_hold(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason_code="court-order",
        purpose="litigation hold",
        actor_id=actor,
    )
    await repo.create_legal_hold(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason_code="regulatory",
        purpose="regulator request",
        actor_id=actor,
    )
    assert (
        await repo.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        is True
    )


@pytest.mark.asyncio
async def test_fence_transition_fails_closed_on_stale_owner_version(db_session):
    """DB fence 的 owner_version 与已安装 registry 版本不一致时，transition 必须
    fail closed（registry 变化 -> 不允许继续推进旧版本 fence）。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    fence = await repo.create_fence(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
    )
    # 模拟 registry 升级前留下的旧版本 fence：直接把 DB 行 version 改成非当前值。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET owner_version = 99 "
            "WHERE tenant_id = :t AND conversation_id = :c "
            "AND owner_key = 'workspace.core.v1'"
        ),
        {"t": tenant_id, "c": conversation_id},
    )
    await db_session.flush()
    with pytest.raises(OwnerRegistryChangedError):
        await repo.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
            expected_state=ErasureFenceState.ACTIVE,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASING,
            purge_revision=1,
            hold_revision=0,
        )


@pytest.mark.asyncio
async def test_fence_transition_rejects_fencing_token_regression(db_session):
    """反例（round4 复审 F1）：purge_revision/hold_revision 是单调 fencing token
    （Spec §5.1/§6.2），CAS transition 不得把 token 回退到更小的值——否则持有旧
    revision 的暂停 writer 会被错误放行，威胁 R1-AC3。等值合法（重试复用同 token）。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    fence = await repo.create_fence(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
    )
    erasing = await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASING,
        purge_revision=5,
        hold_revision=3,
    )
    assert erasing.purge_revision == 5
    assert erasing.hold_revision == 3
    # purge_revision 回退 -> fail closed
    with pytest.raises(ValueError):
        await repo.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
            expected_state=ErasureFenceState.ERASING,
            expected_revision=erasing.revision,
            new_state=ErasureFenceState.ACTIVE,
            purge_revision=1,
            hold_revision=3,
        )
    # hold_revision 回退 -> fail closed
    with pytest.raises(ValueError):
        await repo.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
            expected_state=ErasureFenceState.ERASING,
            expected_revision=erasing.revision,
            new_state=ErasureFenceState.ACTIVE,
            purge_revision=5,
            hold_revision=0,
        )
    # 等值/递增合法：推进到 erased（带 ack）。
    erased = await repo.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key="workspace.core.v1",
        expected_state=ErasureFenceState.ERASING,
        expected_revision=erasing.revision,
        new_state=ErasureFenceState.ERASED,
        purge_revision=6,
        hold_revision=3,
        ack_digest="c" * 64,
    )
    assert erased.state is ErasureFenceState.ERASED
    assert erased.purge_revision == 6
    assert erased.hold_revision == 3


@pytest.mark.asyncio
async def test_fence_state_transition_table_4x4(db_session):
    """反例（round5 复审 P1）：fence 状态机必须有显式转移表，不能只校验 token 单调。

    允许：active→erasing、erasing→erased/blocked、blocked→erasing。
    拒绝：erasing/erased→active（重新开放 writer）、active→erased（绕过 erasing
    fencing）、erased→任意、blocked→active（绕过 erasing fencing）。
    合法推进（erasing→erased/blocked）仍要求 purge_revision>=1（purge fencing token）。
    """
    repo = AgentErasureRepository(db_session)
    S = ErasureFenceState  # noqa: N806

    async def _make() -> tuple[uuid.UUID, uuid.UUID]:
        return await _make_conversation(db_session)

    async def _drive(tenant_id, conversation_id, path):
        """沿 path 驱动 fence；fence 不存在则先建 active（同 owner 唯一，复用已存在行）。
        path 元素为 (new_state, purge_rev, hold_rev, ack)。"""
        existing = await repo.get_fence_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id, owner_key="workspace.core.v1"
        )
        if existing is None:
            existing = await repo.create_fence(
                tenant_id=tenant_id, conversation_id=conversation_id, owner_key="workspace.core.v1"
            )
        state, revision = existing.state, existing.revision
        for new_state, purge_rev, hold_rev, ack in path:
            result = await repo.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key="workspace.core.v1",
                expected_state=state,
                expected_revision=revision,
                new_state=new_state,
                purge_revision=purge_rev,
                hold_revision=hold_rev,
                ack_digest=ack,
            )
            state, revision = new_state, result.revision
        return state, revision

    async def _expect_reject(
        tenant_id,
        conversation_id,
        from_state,
        from_revision,
        new_state,
        purge_rev,
        hold_rev,
        ack=None,
    ):
        with pytest.raises(ValueError):
            await repo.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key="workspace.core.v1",
                expected_state=from_state,
                expected_revision=from_revision,
                new_state=new_state,
                purge_revision=purge_rev,
                hold_revision=hold_rev,
                ack_digest=ack,
            )

    # --- from=active：仅 active→erasing 合法（其余三边均拒）---
    t, c = await _make()
    fence = await repo.create_fence(
        tenant_id=t, conversation_id=c, owner_key="workspace.core.v1"
    )
    await _expect_reject(t, c, S.ACTIVE, fence.revision, S.ACTIVE, 1, 0)
    await _expect_reject(t, c, S.ACTIVE, fence.revision, S.BLOCKED, 1, 0)
    await _expect_reject(t, c, S.ACTIVE, fence.revision, S.ERASED, 1, 0, ack="a" * 64)

    # --- from=erasing：→erased/blocked 合法（purge_revision>=1），→active 非法 ---
    t, c = await _make()
    st, rev = await _drive(t, c, [(S.ERASING, 1, 0, None)])
    await _expect_reject(t, c, st, rev, S.ACTIVE, 2, 1)  # erasing→active 即使 token 递增也拒
    await _expect_reject(t, c, st, rev, S.ERASING, 2, 1)  # 自迁移非法
    # erasing→blocked 合法
    st, rev = await _drive(t, c, [(S.BLOCKED, 1, 0, None)])
    assert st is S.BLOCKED

    # --- from=blocked：→erasing 合法，→active/erased 非法 ---
    await _expect_reject(t, c, st, rev, S.ACTIVE, 2, 1)
    await _expect_reject(t, c, st, rev, S.ERASED, 1, 0, ack="a" * 64)
    st, rev = await _drive(t, c, [(S.ERASING, 2, 1, None)])
    assert st is S.ERASING

    # --- from=erased：→任意非法（终态）---
    st, rev = await _drive(t, c, [(S.ERASED, 3, 1, "d" * 64)])
    assert st is S.ERASED
    for target in (S.ACTIVE, S.ERASING, S.BLOCKED, S.ERASED):
        await _expect_reject(t, c, st, rev, target, 4, 2, ack="e" * 64)

    # --- 合法推进 token 下界：erasing→erased / erasing→blocked 要求 purge_revision>=1 ---
    t, c = await _make()
    st, rev = await _drive(t, c, [(S.ERASING, 1, 0, None)])
    await _expect_reject(t, c, st, rev, S.ERASED, 0, 0, ack="f" * 64)
    await _expect_reject(t, c, st, rev, S.BLOCKED, 0, 0)


@pytest.mark.asyncio
async def test_concurrent_fence_creation_is_unique(session_factory):
    """真实 PostgreSQL：并发建立同一 fence，唯一约束保证只有一行。"""
    # 在独立事务中创建并提交 Conversation，使并发连接可见。
    async with session_factory() as session, session.begin():
        tenant_id, conversation_id = await _make_conversation(session)

    async def _create_once() -> str:
        async with session_factory() as session, session.begin():
            await acquire_owner_lock(
                session,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key="workspace.core.v1",
            )
            repo = AgentErasureRepository(session)
            fence = await repo.get_or_create_fence_for_update(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key="workspace.core.v1",
            )
            return str(fence.conversation_id)

    results = await asyncio.gather(*[_create_once() for _ in range(6)])
    assert all(result == str(conversation_id) for result in results)

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND owner_key = 'workspace.core.v1'"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_conversation_actor_tombstone_clears_created_by_and_normal_holds(
    db_session,
):
    """Conversation actor tombstone：redacted 可清 created_by 并保留
    creator_identity_digest；present 仍强制 created_by 非空（不弱化正常约束）。

    直接 UPDATE 已存在的 Conversation（由 ``_make_conversation`` 以 present 形态
    创建）到 redacted tombstone 形态。
    """
    tenant_id, conversation_id = await _make_conversation(db_session)
    creator_digest = "c7" * 32
    # redacted tombstone：created_by NULL + actor_state=redacted + digest 保留合法。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET created_by = NULL, "
            " actor_state = 'redacted', creator_identity_digest = :d "
            "WHERE tenant_id = :t AND id = :c"
        ),
        {"t": tenant_id, "c": conversation_id, "d": creator_digest},
    )
    # present 但 created_by NULL 仍违反 CHECK（子事务回滚，保留 Conversation）。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE metaedu.agent_conversations SET created_by = NULL, "
                    " actor_state = 'present' "
                    "WHERE tenant_id = :t AND id = :c"
                ),
                {"t": tenant_id, "c": conversation_id},
            )


@pytest.mark.asyncio
async def test_message_actor_tombstone_clears_author_id_and_normal_holds(db_session):
    """user_input redacted tombstone 可清 author_id 并保留 actor_identity_digest；
    未擦除（present）的 user_input 仍强制 author_id 非空（不弱化正常约束）。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    digest = "a1" * 32
    actor_digest = "b2" * 32
    # redacted tombstone：author_id NULL + actor_identity_digest 保留合法。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_messages "
            "(id, tenant_id, conversation_id, seq, message_kind, author_type, "
            " author_id, actor_identity_digest, client_message_id, requested_run_id, "
            " requested_run_queue_seq, turn_request_digest, turn_dispatch_state, "
            " content_state, body_state, content_digest, created_at) "
            "VALUES (:id, :t, :c, 1, 'user_input', 'user', NULL, :ad, :cmid, :rid, "
            " 1, :trd, 'accepted', 'redacted', 'redacted', :d, now())"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant_id,
            "c": conversation_id,
            "ad": actor_digest,
            "cmid": uuid.uuid4(),
            "rid": uuid.uuid4(),
            "trd": digest,
            "d": digest,
        },
    )
    # present user_input 缺 author_id 仍违反 CHECK（子事务回滚，保留 Conversation）。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_messages "
                    "(id, tenant_id, conversation_id, seq, message_kind, author_type, "
                    " author_id, actor_identity_digest, client_message_id, "
                    " requested_run_id, requested_run_queue_seq, turn_request_digest, "
                    " turn_dispatch_state, content_state, body_state, content_digest, "
                    " created_at) "
                    "VALUES (:id, :t, :c, 2, 'user_input', 'user', NULL, NULL, :cmid, "
                    " :rid, 1, :trd, 'accepted', 'visible', 'present', :d, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "c": conversation_id,
                    "cmid": uuid.uuid4(),
                    "rid": uuid.uuid4(),
                    "trd": digest,
                    "d": digest,
                },
            )


@pytest.mark.asyncio
async def test_snapshot_columns_reject_non_object_json(db_session):
    """ingress_checkpoint / retention_policy_snapshot 必须是 JSON object
    （Spec：JSON object），标量/数组被拒绝。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, state, "
                    " ingress_checkpoint, ingress_digest) "
                    "VALUES (:t, :c, 'workspace.core.v1', 1, 'active', "
                    " '[1,2]'::jsonb, :d)"
                ),
                {"t": tenant_id, "c": conversation_id, "d": "c3" * 32},
            )


@pytest.mark.asyncio
async def test_tombstone_states_insertable_and_normal_constraints_hold(db_session):
    """tombstone expand-only：tombstone 状态可表达；正常未擦除写路径仍受约束。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    digest = "c" * 64

    # Message body tombstone：body_state=redacted 且 content_state=redacted 合法。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_messages "
            "(id, tenant_id, conversation_id, seq, message_kind, author_type, "
            " content_state, body_state, content_digest, created_at) "
            "VALUES (:id, :t, :c, 1, 'system_notice', 'system', 'redacted', "
            " 'redacted', :d, now())"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "c": conversation_id, "d": digest},
    )
    # body_state=redacted 但 content_state=visible -> 违反 CHECK（子事务回滚，
    # 不丢弃外层已建 Conversation）。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_messages "
                    "(id, tenant_id, conversation_id, seq, message_kind, author_type, "
                    " content_state, body_state, content_digest, created_at) "
                    "VALUES (:id, :t, :c, 2, 'system_notice', 'system', 'visible', "
                    " 'redacted', :d, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "c": conversation_id,
                    "d": digest,
                },
            )


@pytest.mark.asyncio
async def test_compat_output_tombstone_and_normal_constraint(db_session):
    tenant_id, conversation_id = await _make_conversation(db_session)
    # 需要一个 completed Run 才能挂 CompatibilityOutput 外键；直接用最小列集构造。
    run_id = uuid.uuid4()
    await _insert_minimal_completed_run(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        run_id=run_id,
    )
    digest = "d" * 64
    # present 状态正文必须非空：reply_text NULL 违反 CHECK（子事务回滚，保留 Run）。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_compatibility_outputs "
                    "(id, tenant_id, conversation_id, run_id, output_ref, "
                    " output_digest, response_digest, reply_text, response_envelope, "
                    " payload_state, media_type, classification, created_at) "
                    "VALUES (:id, :t, :c, :r, :ref, :od, :rd, NULL, NULL, 'present', "
                    " 'text/markdown', 'internal', now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "c": conversation_id,
                    "r": run_id,
                    "ref": "ref-1",
                    "od": digest,
                    "rd": digest,
                },
            )

    # redacted tombstone：正文 NULL + digest 保留合法。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_compatibility_outputs "
            "(id, tenant_id, conversation_id, run_id, output_ref, output_digest, "
            " response_digest, reply_text, response_envelope, payload_state, "
            " media_type, classification, created_at) "
            "VALUES (:id, :t, :c, :r, :ref, :od, :rd, NULL, NULL, 'redacted', "
            " 'text/markdown', 'internal', now())"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant_id,
            "c": conversation_id,
            "r": run_id,
            "ref": "ref-2",
            "od": digest,
            "rd": digest,
        },
    )


async def _insert_minimal_completed_run(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
) -> None:
    """构造 suppressed completed Run（tombstone 分支），供 CompatibilityOutput 外键。"""
    # catalog：definition version + runtime profile + binding 省略（binding 可空）。
    def_id, profile_id = uuid.uuid4(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            " created_by, created_at) "
            "VALUES (:id, :t, 'system.direct_rag.v1', 1, 'published', :d, :a, now())"
        ),
        {"id": def_id, "t": tenant_id, "d": "e" * 64, "a": uuid.uuid4()},
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            " capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES (:id, :t, 'compat.direct_rag.v1', 'compat', 'direct_rag', :d, :d2, "
            " true, 1, now(), now())"
        ),
        {"id": profile_id, "t": tenant_id, "d": "f" * 64, "d2": "f" * 64},
    )
    # suppressed completed Run：terminal_output_ref NULL + digest/size 保留。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            " agent_definition_version_id, runtime_profile_id, creation_digest, "
            " status, status_revision, next_event_seq, first_available_event_seq, "
            " last_event_seq, event_log_complete, queued_at, ended_at, terminal_code, "
            " terminal_reason, terminal_result_digest, terminal_output_digest, "
            " terminal_output_size, output_publish_state, created_by, correlation_id, "
            " runtime_capability_snapshot, run_config_snapshot, budget_snapshot, "
            " usage_summary, created_at, updated_at) "
            "VALUES (:id, :t, :c, 1, :root, :def, :prof, :cd, 'completed', 1, 1, 1, 0, "
            " true, now(), now(), 'completed', 'ok', :trd, :tod, 10, 'suppressed', "
            " :cb, :corr, '{}', '{}', '{}', '{}', now(), now())"
        ),
        {
            "id": run_id,
            "t": tenant_id,
            "c": conversation_id,
            "root": uuid.uuid4(),
            "def": def_id,
            "prof": profile_id,
            "cd": "1" * 64,
            "trd": "2" * 64,
            "tod": "3" * 64,
            "cb": uuid.uuid4(),
            "corr": uuid.uuid4(),
        },
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_completed_run_normal_output_constraint_still_enforced(db_session):
    """completed 且未 suppress 的 Run 缺 terminal_output_ref 仍违反 CHECK。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    run_id = uuid.uuid4()
    def_id, profile_id = uuid.uuid4(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            " created_by, created_at) "
            "VALUES (:id, :t, 'k', 1, 'published', :d, :a, now())"
        ),
        {"id": def_id, "t": tenant_id, "d": "4" * 64, "a": uuid.uuid4()},
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            " capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES (:id, :t, 'p', 'compat', 'direct_rag', :d, :d2, true, 1, "
            " now(), now())"
        ),
        {"id": profile_id, "t": tenant_id, "d": "5" * 64, "d2": "5" * 64},
    )
    # completed + output_publish_state=published 但 terminal_output_ref NULL -> 违反
    # （子事务回滚，保留 catalog 行）。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_runs "
                    "(id, tenant_id, conversation_id, queue_seq, "
                    " root_input_message_id, agent_definition_version_id, "
                    " runtime_profile_id, creation_digest, status, status_revision, "
                    " next_event_seq, first_available_event_seq, last_event_seq, "
                    " event_log_complete, queued_at, ended_at, terminal_code, "
                    " terminal_reason, terminal_result_digest, terminal_output_digest, "
                    " terminal_output_size, terminal_output_media_type, "
                    " terminal_output_classification, terminal_message_id, "
                    " output_publish_state, created_by, correlation_id, "
                    " runtime_capability_snapshot, run_config_snapshot, "
                    " budget_snapshot, usage_summary, created_at, updated_at) "
                    "VALUES (:id, :t, :c, 1, :root, :def, :prof, :cd, 'completed', 1, "
                    " 1, 1, 0, true, now(), now(), 'completed', 'ok', :trd, :tod, 10, "
                    " 'text/markdown', 'internal', :tmid, 'published', :cb, :corr, "
                    " '{}', '{}', '{}', '{}', now(), now())"
                ),
                {
                    "id": run_id,
                    "t": tenant_id,
                    "c": conversation_id,
                    "root": uuid.uuid4(),
                    "def": def_id,
                    "prof": profile_id,
                    "cd": "6" * 64,
                    "trd": "7" * 64,
                    "tod": "8" * 64,
                    "tmid": uuid.uuid4(),
                    "cb": uuid.uuid4(),
                    "corr": uuid.uuid4(),
                },
            )


# ---------------------------------------------------------------------------
# purge operation / owner checkpoint：registry snapshot 持久化与 digest 绑定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_operation_persists_registry_snapshot(db_session):
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    # digest 与 snapshot 同源：digest 由持久化的 snapshot 计算，二者绑定。
    assert purge.registry_digest == registry_digest()
    # 排序 owner 列表持久化（不只是 digest），可重建该次 operation 的能力视图。
    assert isinstance(purge.registry_snapshot, list)
    assert [entry["owner_key"] for entry in purge.registry_snapshot] == sorted(
        entry["owner_key"] for entry in purge.registry_snapshot
    )
    for entry in purge.registry_snapshot:
        assert set(entry) == {"owner_key", "owner_version", "capability_digest"}


@pytest.mark.asyncio
async def test_purge_operation_rejects_mismatched_expected_digest(db_session):
    """反例（评审 P1.1）：传入与当前 registry 不一致的 expected digest 必须
    fail closed，不得持久化 snapshot 与 digest 不一致的 operation。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    with pytest.raises(OwnerRegistryChangedError):
        await repo.create_purge_operation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=1,
            retention_policy_snapshot={"conversation_days": 30},
            hold_revision_snapshot=0,
            expected_registry_digest="0" * 64,
        )


@pytest.mark.asyncio
async def test_owner_checkpoint_uses_operation_snapshot(db_session):
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    checkpoint = await repo.create_owner_checkpoint(
        tenant_id=tenant_id,
        purge_operation_id=purge.id,
        owner_key="workspace.core.v1",
    )
    # checkpoint 的 owner_version/capability_digest 来自该 operation 持久化的
    # snapshot（与 digest 同源），而非重新读取当前 registry。
    snapshot_entry = next(
        entry
        for entry in purge.registry_snapshot
        if entry["owner_key"] == "workspace.core.v1"
    )
    assert checkpoint.owner_version == snapshot_entry["owner_version"]
    assert checkpoint.capability_digest == snapshot_entry["capability_digest"]
    assert checkpoint.owner_version == 1
    assert checkpoint.capability_digest == capability_digest("workspace.core.v1")


@pytest.mark.asyncio
async def test_owner_checkpoint_rejects_owner_not_in_snapshot(db_session):
    """owner 不在该 operation 持久化 snapshot 中 -> fail closed。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    with pytest.raises(UnknownOwnerError):
        await repo.create_owner_checkpoint(
            tenant_id=tenant_id,
            purge_operation_id=purge.id,
            owner_key="workspace.unknown.v9",
        )


@pytest.mark.asyncio
async def test_owner_checkpoint_fails_closed_on_registry_drift(db_session):
    """反例（评审 round3 P1.1）：operation 持久化的 registry_digest 不再匹配当前
    registry 时，create_owner_checkpoint 必须 fail closed，不得继续创建 checkpoint
    （Spec §4.2 / R1-AC2 registry drift）。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    # 模拟 registry 升级后留下的旧 operation：digest 与当前 registry 不一致。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET registry_digest = :d "
            "WHERE tenant_id = :t AND id = :p"
        ),
        {"t": tenant_id, "p": purge.id, "d": "0" * 64},
    )
    await db_session.flush()
    with pytest.raises(OwnerRegistryChangedError):
        await repo.create_owner_checkpoint(
            tenant_id=tenant_id,
            purge_operation_id=purge.id,
            owner_key="workspace.core.v1",
        )


@pytest.mark.asyncio
async def test_owner_checkpoint_fails_closed_on_tampered_snapshot(db_session):
    """反例（评审 round3 P1.1）：operation 的 snapshot 与其 registry_digest 内部
    不一致（被篡改）时，create_owner_checkpoint 必须 fail closed。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    purge = await repo.create_purge_operation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        purge_revision=1,
        retention_policy_snapshot={"conversation_days": 30},
        hold_revision_snapshot=0,
    )
    # 篡改 snapshot（owner_version=999），但不改 registry_digest -> 内部不一致。
    tampered = [
        (
            {**entry, "owner_version": 999}
            if entry["owner_key"] == "workspace.core.v1"
            else entry
        )
        for entry in purge.registry_snapshot
    ]
    import json as _json

    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET registry_snapshot = "
            " CAST(:s AS jsonb) WHERE tenant_id = :t AND id = :p"
        ),
        {"t": tenant_id, "p": purge.id, "s": _json.dumps(tampered)},
    )
    await db_session.flush()
    with pytest.raises(OwnerRegistryChangedError):
        await repo.create_owner_checkpoint(
            tenant_id=tenant_id,
            purge_operation_id=purge.id,
            owner_key="workspace.core.v1",
        )


@pytest.mark.asyncio
async def test_owner_checkpoint_fails_closed_on_stale_but_consistent_registry(db_session):
    """反例（round4 复审 F2，变异杀手）：operation 的 snapshot 与 digest 内部自洽
    （校验 a 通过），但不再匹配当前已安装 registry（校验 b 必须 fail closed）。

    模拟 registry 升级后留下的旧 operation：snapshot 被改成 v999 视图，digest 也
    同步改成该篡改 snapshot 的 digest（故内部自洽、躲过校验 a），但该 digest 与
    当前 registry digest 不符——只有独立的校验 (b) 能拦截。删掉校验 (b) 本测试变红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    repo = AgentErasureRepository(db_session)
    tenant_id, _, purge = await _make_purge_operation(db_session)
    stale = [
        (
            {**entry, "owner_version": 999}
            if entry["owner_key"] == "workspace.core.v1"
            else entry
        )
        for entry in purge.registry_snapshot
    ]
    stale_digest = snapshot_digest(stale)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET registry_snapshot = CAST(:s AS jsonb), registry_digest = :d "
            "WHERE tenant_id = :t AND id = :p"
        ),
        {"t": tenant_id, "p": purge.id, "s": _json.dumps(stale), "d": stale_digest},
    )
    await db_session.flush()
    with pytest.raises(OwnerRegistryChangedError):
        await repo.create_owner_checkpoint(
            tenant_id=tenant_id,
            purge_operation_id=purge.id,
            owner_key="workspace.core.v1",
        )


@pytest.mark.asyncio
async def test_create_purge_operation_rejects_non_positive_purge_revision(db_session):
    """反例（round4 复审 F10c）：purge_revision 是 >=1 的单调 fencing token，
    create_purge_operation 必须在应用层 fail closed（与 hold_revision_snapshot
    校验深度一致），而不是漏到 DB 才报 IntegrityError。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    # purge_revision=0 与 -1 都必须应用层 fail closed；各自独立 savepoint，
    # 避免前一次失败的 flush 污染后一次（GREEN 后应用层校验在 flush 前抛 ValueError）。
    for bad_revision in (0, -1):
        with pytest.raises(ValueError):
            async with db_session.begin_nested():
                await repo.create_purge_operation(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    purge_revision=bad_revision,
                    retention_policy_snapshot={"conversation_days": 30},
                    hold_revision_snapshot=0,
                )


@pytest.mark.asyncio
async def test_purge_operation_rejects_negative_hold_revision(db_session):
    """反例（评审 round3 P1.2）：hold_revision_snapshot 是单调 fencing token，
    负数必须在 repository 参数校验层 fail closed。"""
    repo = AgentErasureRepository(db_session)
    tenant_id, conversation_id = await _make_conversation(db_session)
    with pytest.raises(ValueError):
        await repo.create_purge_operation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=1,
            retention_policy_snapshot={"conversation_days": 30},
            hold_revision_snapshot=-1,
        )


@pytest.mark.asyncio
async def test_purge_hold_revision_snapshot_db_check_rejects_negative(db_session):
    """DB CHECK 层同样拒绝 hold_revision_snapshot < 0（绕过 repository 时兜底）。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_conversation_purges "
                    "(id, tenant_id, conversation_id, purge_revision, state, "
                    " registry_digest, registry_snapshot, retention_policy_snapshot, "
                    " retention_policy_digest, hold_revision_snapshot) "
                    "VALUES (:id, :t, :c, 1, 'scheduled', :rd, '[]'::jsonb, "
                    " '{}'::jsonb, :rpd, -1)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "c": conversation_id,
                    "rd": "ab" * 32,
                    "rpd": "cd" * 32,
                },
            )


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_is_idempotent_batched_and_resumable(session_factory):
    # 在独立事务中为同一 tenant 创建并提交 3 个 Conversation，使 backfill 连接可见。
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(session, tenant_id=tenant_id)

    owners = len(owner_registry())
    first = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=2
    )
    assert first.ok
    assert first.conversations_succeeded == 3
    assert first.fences_created == 3 * owners
    # 幂等：重复执行不再创建新 fence。
    second = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=2
    )
    assert second.ok
    assert second.fences_created == 0
    assert second.fences_already_present == 3 * owners

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
    assert count == 3 * owners


@pytest.mark.asyncio
async def test_backfill_max_conversations_is_resumable(session_factory):
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        await _insert_conversation(session, tenant_id=tenant_id)
        await _insert_conversation(session, tenant_id=tenant_id)

    owners = len(owner_registry())
    # 只处理一个 Conversation（模拟中断），随后恢复处理剩余。
    partial = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=100, max_conversations=1
    )
    assert partial.conversations_succeeded == 1
    resumed = await backfill_baseline_fences(
        session_factory,
        tenant_id=tenant_id,
        batch_size=100,
        after_id=partial.next_after_id,
    )
    assert resumed.ok
    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
    assert count == 2 * owners


@pytest.mark.asyncio
async def test_backfill_bounded_runs_advance_via_cursor(session_factory):
    """反例（评审 P1.1）：连续 bounded 调用必须通过游标持续推进。

    三次 ``max_conversations=1`` 且正确串联游标，应处理全部 3 个 Conversation，
    而不是反复处理第一个。
    """
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(session, tenant_id=tenant_id)

    owners = len(owner_registry())
    after_id = None
    for _ in range(3):
        report = await backfill_baseline_fences(
            session_factory,
            tenant_id=tenant_id,
            batch_size=100,
            max_conversations=1,
            after_id=after_id,
        )
        assert report.conversations_succeeded == 1
        after_id = report.next_after_id
    # 游标串联 3 次后已扫完全部 -> 第 4 次从该游标起没有更多 Conversation。
    final = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=100, after_id=after_id
    )
    assert final.conversations_succeeded == 0
    assert final.completed is True
    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
    assert count == 3 * owners


@pytest.mark.asyncio
async def test_backfill_rejects_invalid_batch_and_max(session_factory):
    """反例（评审 P1.3）：batch_size<1 或 max_conversations<1 必须 fail closed，
    不得产生“处理 0 个却 completed=True”的虚假完成。"""
    tenant_id = uuid.uuid4()
    with pytest.raises(ValueError):
        await backfill_baseline_fences(
            session_factory, tenant_id=tenant_id, batch_size=0
        )
    with pytest.raises(ValueError):
        await backfill_baseline_fences(
            session_factory, tenant_id=tenant_id, batch_size=-5
        )
    with pytest.raises(ValueError):
        await backfill_baseline_fences(
            session_factory, tenant_id=tenant_id, max_conversations=0
        )


@pytest.mark.asyncio
async def test_backfill_report_does_not_retain_all_ids(session_factory):
    """BackfillReport 不持有全量 processed id 列表（内存随会话数线性增长）；
    游标与计数已足够串联与诊断。"""
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(session, tenant_id=tenant_id)
    report = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=2
    )
    assert report.conversations_succeeded == 3
    assert not hasattr(report, "processed_conversations")


@pytest.mark.asyncio
async def test_backfill_failures_are_bounded(session_factory, monkeypatch):
    """反例（评审 round3 P1.3）：系统性失败时 failures 必须内存有界。

    强制所有 Conversation 失败并超过样本上限，report 只保留固定上限样本 +
    总失败计数，不随失败数线性增长。
    """
    from app.composition import agent_erasure_backfill as backfill_module

    async def _always_fail(session, *, tenant_id, conversation_id):
        raise RuntimeError("simulated systematic failure")

    monkeypatch.setattr(backfill_module, "_backfill_conversation", _always_fail)
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(5):
            await _insert_conversation(session, tenant_id=tenant_id)
    report = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=2
    )
    assert report.failure_count == 5
    # 样本数封顶于 _MAX_FAILURE_SAMPLES（有界），不随失败数线性增长。
    assert len(report.failures) <= backfill_module._MAX_FAILURE_SAMPLES
    assert report.ok is False


@pytest.mark.asyncio
async def test_backfill_marks_complete_when_last_row_hits_max(session_factory):
    """反例（评审 round3 P2.4）：仅剩 1 行且 max_conversations=1 时，
    实际已无更多 Conversation，应 completed=True 而非误报未完成。"""
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        await _insert_conversation(session, tenant_id=tenant_id)
    report = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=100, max_conversations=1
    )
    assert report.conversations_succeeded == 1
    assert report.completed is True


# ---------------------------------------------------------------------------
# backfill CLI 退出码契约（评审 P2）：0=完成 / 1=失败 / 2=未完成须续跑
# ---------------------------------------------------------------------------


class _NullEngine:
    async def dispose(self) -> None:
        return None


def _cli_args(**overrides):
    import argparse

    defaults = {
        "tenant_id": str(uuid.uuid4()),
        "batch_size": 100,
        "max_conversations": None,
        "after_id": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _patch_session_factory(monkeypatch, session_factory):
    from app.composition import agent_erasure_backfill as backfill_module

    monkeypatch.setattr(
        backfill_module,
        "_make_session_factory",
        lambda: (session_factory, _NullEngine()),
    )
    return backfill_module


@pytest.mark.asyncio
async def test_cli_exit_0_when_complete(session_factory, monkeypatch):
    backfill_module = _patch_session_factory(monkeypatch, session_factory)
    # 空 tenant：无可处理 Conversation -> completed=True -> exit 0。
    exit_code = await backfill_module._run_cli(_cli_args())
    assert exit_code == 0


@pytest.mark.asyncio
async def test_cli_exit_2_when_incomplete(session_factory, monkeypatch):
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(session, tenant_id=tenant_id)
    backfill_module = _patch_session_factory(monkeypatch, session_factory)
    exit_code = await backfill_module._run_cli(
        _cli_args(tenant_id=str(tenant_id), max_conversations=1)
    )
    assert exit_code == 2


@pytest.mark.asyncio
async def test_cli_rejects_invalid_batch_size(session_factory, monkeypatch):
    backfill_module = _patch_session_factory(monkeypatch, session_factory)
    with pytest.raises(ValueError):
        await backfill_module._run_cli(_cli_args(batch_size=0))


# ---------------------------------------------------------------------------
# round4 复审 F5：tombstone「清一半必须拒」负向分支（真实 PostgreSQL CHECK）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_redacted_requires_actor_identity_digest(db_session):
    """反例（round4 复审 F5）：redacted user_input 清 author_id 时必须保留不可逆
    actor_identity_digest；缺 digest 的「清一半」行必须被 DB CHECK 拒绝。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    base = {
        "t": tenant_id,
        "c": conversation_id,
        "id": uuid.uuid4(),
        "content_digest": "a" * 64,
        "client_message_id": uuid.uuid4(),
        "run_id": uuid.uuid4(),
        "turn_digest": "b" * 64,
        "actor_digest": "d" * 64,
    }
    insert_sql = (
        "INSERT INTO metaedu.agent_messages "
        "(id, tenant_id, conversation_id, seq, message_kind, author_type, author_id, "
        " content_state, body_state, actor_identity_digest, content_digest, "
        " client_message_id, requested_run_id, requested_run_queue_seq, "
        " turn_request_digest, turn_dispatch_state, created_at) "
        "VALUES (:id, :t, :c, 1, 'user_input', 'user', :author_id, 'redacted', "
        " 'redacted', :actor_digest, :content_digest, :client_message_id, :run_id, 1, "
        " :turn_digest, 'accepted', now())"
    )
    # 负向：redacted 但 actor_identity_digest 为 NULL（清了 actor 却没留 digest）-> 拒。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(insert_sql),
                {**base, "author_id": None, "actor_digest": None},
            )
    # 正向：redacted + 清 author_id + 保留 digest -> 允许。
    async with db_session.begin_nested():
        await db_session.execute(
            text(insert_sql), {**base, "author_id": None}
        )


@pytest.mark.asyncio
async def test_conversation_redacted_requires_creator_identity_digest(db_session):
    """反例（round4 复审 F5）：Conversation redacted 清 created_by 时必须保留
    creator_identity_digest；缺 digest 必须被 DB CHECK 拒绝。"""
    tenant_id, conversation_id = await _make_conversation(db_session)
    # 负向：redacted 但 creator_identity_digest 为 NULL -> 拒。
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE metaedu.agent_conversations SET actor_state='redacted', "
                    "created_by=NULL, creator_identity_digest=NULL "
                    "WHERE tenant_id=:t AND id=:c"
                ),
                {"t": tenant_id, "c": conversation_id},
            )
    # 正向：redacted + 清 created_by + 保留 64-hex digest -> 允许。
    async with db_session.begin_nested():
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_conversations SET actor_state='redacted', "
                "created_by=NULL, creator_identity_digest=:d "
                "WHERE tenant_id=:t AND id=:c"
            ),
            {"t": tenant_id, "c": conversation_id, "d": "e" * 64},
        )


@pytest.mark.asyncio
async def test_outbox_suppressed_requires_cleared_payload(db_session):
    """反例（round4 复审 F5）：两侧 outbox 的 suppressed tombstone 必须清空
    payload_inline/payload_ref；保留正文的 suppressed 行必须被 DB CHECK 拒绝。"""
    tenant_id = uuid.uuid4()
    ws_sql = (
        "INSERT INTO metaedu.agent_workspace_outbox "
        "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        " payload_inline, payload_ref, payload_digest, correlation_id, status, "
        " attempt_count, next_attempt_at, created_at) "
        "VALUES (:id, :t, 'turn.requested.v1', 1, :agg, 'conversation', :inline, "
        " :ref, :digest, :corr, :status, 0, now(), now())"
    )
    ex_sql = (
        "INSERT INTO metaedu.agent_execution_outbox "
        "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        " payload_inline, payload_ref, payload_digest, correlation_id, status, "
        " attempt_count, next_attempt_at, created_at) "
        "VALUES (:id, :t, 'assistant_message.publish_requested.v1', 1, :agg, 'run', "
        " :inline, :ref, :digest, :corr, :status, 0, now(), now())"
    )
    for stmt in (ws_sql, ex_sql):
        base = {
            "id": uuid.uuid4(),
            "t": tenant_id,
            "agg": uuid.uuid4(),
            "corr": uuid.uuid4(),
            "digest": "f" * 64,
        }
        # 负向：suppressed 但仍带正文 inline -> 拒。
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(stmt),
                    {
                        **base,
                        "inline": '{"k":"v"}',
                        "ref": None,
                        "status": "suppressed",
                    },
                )
        # 正向：suppressed + 双 NULL payload + 保留 digest -> 允许。
        async with db_session.begin_nested():
            await db_session.execute(
                text(stmt), {**base, "inline": None, "ref": None, "status": "suppressed"}
            )


# ---------------------------------------------------------------------------
# round4 复审 F3/F4：failures 上界变异杀手 + CLI 失败总数
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_failures_capped_above_sample_limit(session_factory, monkeypatch):
    """反例（round4 复审 F3，变异杀手）：失败数必须真正超过样本上限，验证样本
    恰好封顶于 _MAX_FAILURE_SAMPLES 且 failure_count 仍为总失败数。只造 5 个失败
    无法区分有无封顶——本测试用上限 + 富余，删掉封顶逻辑即变红。"""
    from app.composition import agent_erasure_backfill as backfill_module

    cap = backfill_module._MAX_FAILURE_SAMPLES
    total = cap + 5

    async def _always_fail(session, *, tenant_id, conversation_id):
        raise RuntimeError("simulated systematic failure")

    monkeypatch.setattr(backfill_module, "_backfill_conversation", _always_fail)
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(total):
            await _insert_conversation(session, tenant_id=tenant_id)
    # batch_size >= total，保证单批扫完全部、失败数真实超过样本上限（>cap）。
    # 失败路径只计 failure_count，不计 conversations_succeeded（succeeded 仅成功行）。
    report = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=total
    )
    assert report.failure_count == total
    assert len(report.failures) == cap
    assert report.ok is False


@pytest.mark.asyncio
async def test_cli_prints_total_failure_count(session_factory, monkeypatch, capsys):
    """反例（round4 复审 F4）：CLI 报告的 failed= 必须是失败总数 failure_count，
    不是有界样本数。系统性失败 20 个（>16 上限）时应打印 failed=20 而非 failed=16。"""
    from app.composition import agent_erasure_backfill as backfill_module

    cap = backfill_module._MAX_FAILURE_SAMPLES
    total = cap + 4

    async def _always_fail(session, *, tenant_id, conversation_id):
        raise RuntimeError("simulated systematic failure")

    monkeypatch.setattr(backfill_module, "_backfill_conversation", _always_fail)
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(total):
            await _insert_conversation(session, tenant_id=tenant_id)
    module = _patch_session_factory(monkeypatch, session_factory)
    capsys.readouterr()  # 清掉 setup 输出
    exit_code = await module._run_cli(_cli_args(tenant_id=str(tenant_id)))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert f"failed={total}" in out
    assert f"failed={cap}\n" not in out


@pytest.mark.asyncio
async def test_backfill_report_exposes_succeeded_not_scanned(session_factory, monkeypatch):
    """反例（round5 复审 P2.4）：report 必须明确「成功」而非模糊「scanned」——
    scanned 只计成功行，失败行不计。字段名 conversations_succeeded 才准确表达。"""
    from app.composition import agent_erasure_backfill as backfill_module

    async def _fail_after_first(session, *, tenant_id, conversation_id):
        _fail_after_first.calls += 1
        if _fail_after_first.calls > 1:
            raise RuntimeError("boom")
        return (6, 0)

    _fail_after_first.calls = 0
    monkeypatch.setattr(backfill_module, "_backfill_conversation", _fail_after_first)
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(session, tenant_id=tenant_id)
    report = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=10
    )
    assert report.conversations_succeeded == 1
    assert report.failure_count == 2
    assert not hasattr(report, "conversations_scanned")


@pytest.mark.asyncio
async def test_cli_exit1_prints_full_rerun_recovery(session_factory, monkeypatch, capsys):
    """反例（round5 复审 P2.4）：exit 1 时 CLI 必须打印「从 tenant 起点完整重跑」
    指令——失败行不会被 next_after_id 续跑覆盖（游标已越过失败行），唯一可靠
    恢复是从起点幂等重跑。"""
    from app.composition import agent_erasure_backfill as backfill_module

    async def _always_fail(session, *, tenant_id, conversation_id):
        raise RuntimeError("simulated systematic failure")

    monkeypatch.setattr(backfill_module, "_backfill_conversation", _always_fail)
    async with session_factory() as session, session.begin():
        tenant_id = uuid.uuid4()
        await _insert_conversation(session, tenant_id=tenant_id)
    module = _patch_session_factory(monkeypatch, session_factory)
    capsys.readouterr()
    exit_code = await module._run_cli(_cli_args(tenant_id=str(tenant_id)))
    out = capsys.readouterr().out
    assert exit_code == 1
    # 必须给出从起点重跑的明确指令（不带 --after-id），而非误导续跑游标。
    assert f"--tenant-id {tenant_id}" in out
    assert "起点" in out or "rerun from" in out.lower() or "from the start" in out.lower()
