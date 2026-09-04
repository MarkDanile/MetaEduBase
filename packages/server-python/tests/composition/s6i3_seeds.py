"""R1-S6-I3 共享种子/fixture（fault matrix + restore replay 测试共用）。

从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分收口 td-032。
仅承载 fixture 与 seed helper；**不含任何测试**（文件名无 ``test_`` 前缀，
pytest 不收集）。所有 SQL 列名以 migration 034/040/043 + ORM + fresh PG
（alembic head=043）为准。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.shared.schemas.canonical_json import canonical_digest

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


async def _seed_6_owner_acked_with_residual_body(
    session: AsyncSession,
    *,
    tid: uuid.UUID,
    cid: uuid.UUID,
    purge_operation_id: uuid.UUID,
    window_owner_key: str = "external.payload.v1",
) -> None:
    """F10 M6 priority-3 scan 真实 PG 判别载体：6 owner 全部 pre-state=acked + 5-party
    validation 全 pass + workspace.core.v1 final scan nonzero。

    - 6 owner 全部 pre-INSERT checkpoint.state=acked + capability_digest=64hex +
      ack_digest=64hex（**不**依赖 closeout_erasing 写入路径；M6 判别只关心 projection
      聚合 stage 看到的状态）；
    - conversation 保留 actor_state='present'（workspace.core.v1 final scan 命中
      unanonymized_actors=1 → scan_total=1 nonzero → priority 3 scan_reason 触发）；
    - **不** create legal hold（**不**推进 hold_revision；G2/G3 cleared）；
    - **不**改 registry_digest（**不**触发 G1 drift）；
    - **不**改 purge_revision（**不**触发五方版本 mismatch）；

    caller 责任：调用此 helper **前** 须确保 conversation 状态满足：
    - state='deleted' 或 'erasing' + purge_after 已过期（closeout_erasing 前置）
    - 已有 1 行 agent_conversation_purges (state=running/erasing 起始，purge_revision=1)
    - 已有对应的 fence 行 state='erasing'（window owner 的 closeout_erasing 前置）

    usage（test_s6i3_fault_f10.py::test_f10_m6_completed_bypass_scan_check_blocked）:
        tid = await _seed_tenant(seed, name="f10-m6")
        cid = await _seed_conversation(seed, tid=tid)
        await _seed_fence(seed, tid, cid, "external.payload.v1", state="erasing")
        op_id = await _seed_operation(seed, tid=tid, cid=cid, state="running")
        await _seed_6_owner_acked_with_residual_body(
            seed, tid=tid, cid=cid, purge_operation_id=op_id,
            window_owner_key="external.payload.v1",
        )
    """
    from app.composition.agent_erasure_registry import capability_digest

    # 6 owner：workspace.core/transport + execution.core/transport + external + runtime
    # 唯一约束 = (tenant_id, purge_operation_id, owner_key)（migration 034 uq_agent_purge_owner）
    for owner_key in (
        "workspace.core.v1",
        "workspace.transport.v1",
        "execution.core.v1",
        "execution.transport.v1",
        "external.payload.v1",
        "runtime.private.v1",
    ):
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_conversation_purge_owners "
                "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
                "capability_digest, state, attempt, checkpoint_digest, "
                "ack_digest, reason_code, created_at) "
                "VALUES (gen_random_uuid(), :tid, :pid, :ok, 1, :cap, 'acked', "
                "        1, :digest, :digest, NULL, now()) "
                "ON CONFLICT (tenant_id, purge_operation_id, owner_key) DO UPDATE SET "
                "state='acked', attempt=1, capability_digest=EXCLUDED.capability_digest, "
                "checkpoint_digest=EXCLUDED.checkpoint_digest, "
                "ack_digest=EXCLUDED.ack_digest, reason_code=NULL"
            ),
            {
                "tid": tid,
                "pid": purge_operation_id,
                "ok": owner_key,
                "cap": capability_digest(owner_key),
                "digest": _DIGEST,
            },
        )

    # 5 非 window owner fence 预置 erased（fence.owner_version=1 + ack_digest 64hex +
    # hold_revision=0 + purge_revision=1）。**不**改 window owner fence —— 留 caller 通过
    # closeout_erasing 从 erasing 推到 erased（演示 production entry path）。
    # 缺 fence 行的 owner 在 5-party 验证失败（fence_row is None → return False）→
    # priority 2 提前 blocked，priority 3 scan 不达——故必须全部 6 owner fence 显式
    # 预置（5 非 window=erased + 1 window=由 closeout_erasing 推到 erased）。
    for owner_key in (
        "workspace.core.v1",
        "workspace.transport.v1",
        "execution.core.v1",
        "execution.transport.v1",
        "runtime.private.v1",
    ):
        await _seed_fence(
            session, tid, cid, owner_key, state="erased", ack=_DIGEST
        )

    # 对话 actor_state 保持 'present'（默认 seed）→ workspace.core.v1 scan 命中
    # unanonymized_actors=1 → scan_total nonzero。**不**修改 title / created_by /
    # archived_by / deleted_by（保持默认即可触发 scan）。
    # **不**改 hold_revision（保持 0 → G2 cleared）。
    # **不**create legal hold（G3 cleared）。
    # **不**改 registry（snapshot 一致 → G1 cleared）。

async def _seed_fence(
    session: AsyncSession,
    tid: uuid.UUID,
    cid: uuid.UUID,
    owner_key: str,
    *,
    state: str = "erasing",
    ack: str | None = None,
) -> None:
    """种 1 行 ``agent_erasure_fences``（state + 可选 ack_digest）。

    复用 test_s5_sch_d_settlement.py::_seed_fence 形态（列名 + JSON 序列化 +
    canonical_digest）；ack 仅 state='erased' 时落 DB 列。
    """
    ic = {"schema_version": 1, "sources": {}}
    ack_sql = ", ack_digest, acked_at" if state == "erased" else ""
    ack_vals = ", :ack, now()" if state == "erased" else ""
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest"
            + ack_sql
            + ", revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            ":st, 1, 0, :ic, :ing"
            + ack_vals
            + ", 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": owner_key, "st": state,
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
            "ack": ack,
        },
    )
