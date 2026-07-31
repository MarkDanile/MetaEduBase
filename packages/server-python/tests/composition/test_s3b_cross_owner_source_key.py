"""S3-B round-4 P2-2 + round-5 P1-1：cross-owner source key 实际调用 repository 断言拒绝。

``test_s3b_actor_tombstone_contract::test_cross_owner_key_is_rejected`` 只检查
两个集合互斥，删除 ``advance_ingress_checkpoint_for_update`` 的 owner/source
guard 后仍能通过。本测试直接调 ``AgentErasureRepository.advance_ingress_checkpoint_for_update``，
workspace core.v1 owner 写 execution source key（及反之）必须 raise ``ValueError``。

round-5 P1-1：seed/cleanup 与 ``db_session`` 同事务，避免 ``advance_ingress_checkpoint_for_update``
持锁后另一个 asyncpg 连接 DELETE 等待锁释放导致死锁。
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    INGRESS_SOURCE_KEYS_BY_OWNER,
    AgentErasureRepository,
)


async def _seed_conversation_and_fence_in_txn(
    session, owner_key: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """在同一事务内插入 conversation + active fence，返回 (tenant_id, conversation_id)。

    round-5 P1-1：与 db_session 同事务，避免外部连接 DELETE 等待 db_session
    持锁导致的死锁。测试结束后依赖 ``clean_agent_control_plane`` autouse
    兜底清理。
    """
    from sqlalchemy import text as _sa_text

    tid = uuid.uuid4()
    cid = uuid.uuid4()
    digest = "a" * 64
    await session.execute(
        _sa_text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, title, "
            "title_source, state, parent_conversation_id, forked_from_message_id, "
            "next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            "purge_revision, hold_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tid, :creator, 'present', :digest, NULL, 'none', 'active', "
            "NULL, NULL, 1, 1, now(), 'not_scheduled', 0, 0, 1, now(), now())"
        ),
        {"id": cid, "tid": tid, "creator": tid, "digest": digest},
    )
    await session.execute(
        _sa_text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "last_body_write_at, ack_digest, acked_at, revision, created_at, updated_at) "
            "VALUES (:tid, :cid, :owner, 1, 'active', 0, 0, "
            "'{\"schema_version\": 1, \"sources\": {}}', :digest, NULL, NULL, NULL, "
            "1, now(), now())"
        ),
        {"tid": tid, "cid": cid, "owner": owner_key, "digest": digest},
    )
    return tid, cid


@pytest.mark.asyncio
async def test_workspace_owner_cannot_advance_execution_source_key(db_session) -> None:
    """workspace.core.v1 owner 写 execution.core.v1 source key 必须 ValueError。

    实际调用 ``AgentErasureRepository.advance_ingress_checkpoint_for_update``。
    若 owner/source guard 被删，本测试 fail。
    """
    tid, cid = await _seed_conversation_and_fence_in_txn(
        db_session, "workspace.core.v1"
    )
    repo = AgentErasureRepository(db_session)
    with pytest.raises(ValueError, match="run_output_body"):
        await repo.advance_ingress_checkpoint_for_update(
            tenant_id=tid,
            conversation_id=cid,
            owner_key="workspace.core.v1",
            source_key="run_output_body",  # 属于 execution.core.v1
            watermark=1,
            epoch=0,
        )


@pytest.mark.asyncio
async def test_execution_owner_cannot_advance_workspace_source_key(db_session) -> None:
    """execution.core.v1 owner 写 workspace.core.v1 source key 必须 ValueError。"""
    tid, cid = await _seed_conversation_and_fence_in_txn(
        db_session, "execution.core.v1"
    )
    repo = AgentErasureRepository(db_session)
    with pytest.raises(ValueError, match="body_messages"):
        await repo.advance_ingress_checkpoint_for_update(
            tenant_id=tid,
            conversation_id=cid,
            owner_key="execution.core.v1",
            source_key="body_messages",  # 属于 workspace.core.v1
            watermark=1,
            epoch=0,
        )


@pytest.mark.asyncio
async def test_execution_owner_can_advance_own_source_key(db_session) -> None:
    """execution.core.v1 owner 写自己的 source key（run_output_body）必须成功。"""
    assert "run_output_body" in INGRESS_SOURCE_KEYS_BY_OWNER["execution.core.v1"]

    tid, cid = await _seed_conversation_and_fence_in_txn(
        db_session, "execution.core.v1"
    )
    repo = AgentErasureRepository(db_session)
    # 不应 raise
    await repo.advance_ingress_checkpoint_for_update(
        tenant_id=tid,
        conversation_id=cid,
        owner_key="execution.core.v1",
        source_key="run_output_body",
        watermark=1,
        epoch=0,
    )
