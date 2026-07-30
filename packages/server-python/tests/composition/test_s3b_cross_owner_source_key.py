"""S3-B round-4 P2-2：cross-owner source key 实际调用 repository 断言拒绝。

``test_s3b_actor_tombstone_contract::test_cross_owner_key_is_rejected`` 只检查
两个集合互斥，删除 ``advance_ingress_checkpoint_for_update`` 的 owner/source
guard 后仍能通过。本测试直接调 ``AgentErasureRepository.advance_ingress_checkpoint_for_update``，
workspace core.v1 owner 写 execution source key（及反之）必须 raise ``ValueError``。
需要先建 conversation + fence（FK 约束）。
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    INGRESS_SOURCE_KEYS_BY_OWNER,
    AgentErasureRepository,
)


def _sqlalchemy_url() -> str:
    from tests.conftest import TEST_DB_URL

    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _seed_conversation_and_fence(owner_key: str) -> tuple[uuid.UUID, uuid.UUID]:
    """插入 conversation（最小列）+ active fence，返回 (tenant_id, conversation_id)。"""
    connection = await asyncpg.connect(_sqlalchemy_url())
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    digest = "a" * 64
    try:
        # 对话：最小合法列（test_alembic 已验证 schema）。
        await connection.execute(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, title, "
            "title_source, state, parent_conversation_id, forked_from_message_id, "
            "next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            "purge_revision, hold_revision, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'present', $4, NULL, 'none', 'active', NULL, NULL, "
            "1, 1, now(), 'not_scheduled', 0, 0, 1, now(), now())",
            cid, tid, tid, digest,
        )
        # fence：active + 最小列。
        await connection.execute(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "last_body_write_at, ack_digest, acked_at, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 1, 'active', 0, 0, "
            "'{\"schema_version\": 1, \"sources\": {}}', $4, NULL, NULL, NULL, "
            "1, now(), now())",
            tid, cid, owner_key, digest,
        )
        return tid, cid
    finally:
        await connection.close()


async def _cleanup_conversation_and_fence(tid: uuid.UUID) -> None:
    connection = await asyncpg.connect(_sqlalchemy_url())
    try:
        await connection.execute(
            "DELETE FROM metaedu.agent_erasure_fences WHERE tenant_id=$1", tid
        )
        await connection.execute(
            "DELETE FROM metaedu.agent_conversations WHERE tenant_id=$1", tid
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_workspace_owner_cannot_advance_execution_source_key(db_session) -> None:
    """workspace.core.v1 owner 写 execution.core.v1 source key 必须 ValueError。

    实际调用 ``AgentErasureRepository.advance_ingress_checkpoint_for_update``。
    若 owner/source guard 被删，本测试 fail。
    """
    tid, cid = await _seed_conversation_and_fence("workspace.core.v1")
    try:
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
    finally:
        await _cleanup_conversation_and_fence(tid)


@pytest.mark.asyncio
async def test_execution_owner_cannot_advance_workspace_source_key(db_session) -> None:
    """execution.core.v1 owner 写 workspace.core.v1 source key 必须 ValueError。"""
    tid, cid = await _seed_conversation_and_fence("execution.core.v1")
    try:
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
    finally:
        await _cleanup_conversation_and_fence(tid)


@pytest.mark.asyncio
async def test_execution_owner_can_advance_own_source_key(db_session) -> None:
    """execution.core.v1 owner 写自己的 source key（run_output_body）必须成功。"""
    assert "run_output_body" in INGRESS_SOURCE_KEYS_BY_OWNER["execution.core.v1"]

    tid, cid = await _seed_conversation_and_fence("execution.core.v1")
    try:
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
    finally:
        await _cleanup_conversation_and_fence(tid)
