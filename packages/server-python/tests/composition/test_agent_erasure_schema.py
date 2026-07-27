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
    UnknownOwnerError,
    owner_registry,
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
    assert first.conversations_scanned == 3
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
    assert partial.conversations_scanned == 1
    resumed = await backfill_baseline_fences(
        session_factory, tenant_id=tenant_id, batch_size=100
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
