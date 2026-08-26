"""R1-S6-I3 共享种子/fixture（fault matrix + restore replay 测试共用）。

从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分收口 td-032。
仅承载 fixture 与 seed helper；**不含任何测试**（文件名无 ``test_`` 前缀，
pytest 不收集）。所有 SQL 列名以 migration 034/040/043 + ORM + fresh PG
（alembic head=043）为准。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


@pytest.fixture
async def s6i3_session_factory(db_session) -> AsyncIterator[async_sessionmaker]:
    """每个测试一个独立 engine/sessionmaker 复用 db_session 同一 URL。"""

    engine = create_async_engine(
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_tenant(session: AsyncSession, *, name: str = "t") -> uuid.UUID:
    tid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants (id, name, school_name, "
            "isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :name, 'shared', true, now(), now())"
        ),
        {"id": tid, "name": f"{name}-{tid}"},
    )
    return tid


async def _seed_conversation(session: AsyncSession, *, tid: uuid.UUID) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, purged_at, hold_revision, revision, "
            "next_message_seq, next_run_queue_seq, last_activity_at, created_at, "
            "updated_at) "
            "VALUES (:cid, :tid, :tid, 'present', :digest, NULL, 't', 'none', "
            "'active', NULL, 'not_scheduled', 1, NULL, 0, 1, 1, 1, now(), now(), now())"
        ),
        {"cid": cid, "tid": tid, "digest": _DIGEST},
    )
    return cid


async def _seed_operation(
    session: AsyncSession,
    *,
    tid: uuid.UUID,
    cid: uuid.UUID,
    state: str,
    purge_rev: int = 1,
    failure_code: str | None = None,
) -> uuid.UUID:
    """种一张 ``agent_conversation_purges`` 行。"""

    pid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purges "
            "(id, tenant_id, conversation_id, purge_revision, state, "
            "registry_digest, retention_policy_snapshot, retention_policy_digest, "
            "hold_revision_snapshot, lease_epoch, "
            "lease_expires_at, scheduled_at, started_at, completed_at, "
            "failure_code, next_retry_at, revision, created_at, updated_at) "
            "VALUES (:id, :tid, :cid, :pr, :state, :digest, "
            "CAST(:rps AS jsonb), :digest, "
            "0, 0, NULL, "
            "now(), now(), NULL, :fc, NULL, 1, now(), now())"
        ),
        {
            "id": pid,
            "tid": tid,
            "cid": cid,
            "pr": purge_rev,
            "state": state,
            "digest": _DIGEST,
            "rps": '{"conversation_recovery_days": 30}',
            "fc": failure_code,
        },
    )
    return pid


async def _seed_checkpoint(
    session: AsyncSession,
    *,
    tid: uuid.UUID,
    purge_operation_id: uuid.UUID,
    owner_key: str,
    owner_version: int = 1,
    state: str = "acked",
    attempt: int = 1,
    capability_digest: str | None = None,
    checkpoint_digest: str | None = None,
    ack_digest: str | None = None,
    reason_code: str | None = None,
) -> uuid.UUID:
    """种一张 ``agent_conversation_purge_owners`` 行（per owner checkpoint）。"""

    cp_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, "
            "checkpoint_digest, ack_digest, reason_code, created_at) "
            "VALUES (:id, :tid, :pid, :ok, :ov, :cap, :state, :att, "
            ":cdigest, :adigest, :rc, now())"
        ),
        {
            "id": cp_id,
            "tid": tid,
            "pid": purge_operation_id,
            "ok": owner_key,
            "ov": owner_version,
            "cap": capability_digest or _DIGEST,
            "state": state,
            "att": attempt,
            "cdigest": checkpoint_digest or _DIGEST,
            # ck_agent_purge_owner_ack（034:567-571）：state='acked' ⇒ 合法
            # 64-hex ack_digest；state<>'acked' ⇒ ack_digest IS NULL
            "adigest": ack_digest
            if ack_digest is not None
            else (_DIGEST if state == "acked" else None),
            "rc": reason_code,
        },
    )
    return cp_id
