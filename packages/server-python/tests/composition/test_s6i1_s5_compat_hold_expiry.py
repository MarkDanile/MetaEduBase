"""R1-S6 S6-I1 裁决一（S5 修改点 #1）：hold 到期读侧谓词宽化真实 PG 验收。

契约：Plan §R1-S6-1 item 3（裁决一，R1-AC7 缺口）——``has_active_legal_hold``
与 claim ``_has_active_hold`` 的 active 判定从 ``state='active'`` 宽化为
``state='active' AND (expires_at IS NULL OR expires_at > now)``（now = DB clock）；
**不 bump ``hold_revision``**（仍只由 create/release 推进）。过期 active hold 不再
阻塞 claim/participant/retention prune；未过期 hold 行为不变；``expires_at NULL``
仍 active。

判别测试（S6-1 item 3 限定）：过期 active hold 不再 defer claim；未过期 hold 仍
defer；``expires_at`` NULL 仍 active。宽化只解除读侧阻塞——已 G2-blocked 的旧
operation 仍走 S5 rebuild 通道，本测试不断言旧 operation 恢复完成。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.conversation_purge_scheduler import (
    ClaimKind,
    ConversationPurgeScheduler,
    DeferReason,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


async def _seed_conversation(session, *, tid=None, cid=None):
    tid = tid or uuid.uuid4()
    cid = cid or uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, purged_at, hold_revision, revision, "
            "next_message_seq, next_run_queue_seq, last_activity_at, created_at, "
            "updated_at) "
            "VALUES (:cid, :tid, :tid, 'present', :digest, NULL, 't', 'none', "
            "'deleted', now() - interval '1 day', 'scheduled', 1, NULL, 0, 1, "
            "1, 1, now(), now(), now())"
        ),
        {"cid": cid, "tid": tid, "digest": _DIGEST},
    )
    return tid, cid


async def _seed_hold(session, *, tid, cid, expires_at=None, state="active"):
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_legal_holds "
            "(id, tenant_id, conversation_id, reason_code, purpose, actor_id, state, "
            "expires_at, revision, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :tid, :cid, 'retention_test', 'test', :tid, "
            ":state, :expires_at, 1, now(), now())"
        ),
        {"tid": tid, "cid": cid, "state": state, "expires_at": expires_at},
    )


async def _claim(session, tid, cid):
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _has_active_hold(session, *, tid, cid) -> bool:
    return await AgentErasureRepository(session).has_active_legal_hold(
        tenant_id=tid, conversation_id=cid
    )


# ---------------------------------------------------------------------------
# repository 谓词（has_active_legal_hold）
# ---------------------------------------------------------------------------


async def test_repository_expired_hold_not_active(session_factory):
    """``expires_at`` 已过期的 active hold 不再是 active（DB clock 判定）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=datetime.now(UTC) - timedelta(days=30))
    async with session_factory() as verify:
        assert await _has_active_hold(verify, tid=tid, cid=cid) is False


async def test_repository_null_and_future_expiry_still_active(session_factory):
    """``expires_at`` NULL 与未来时间仍 active（行为不变）。"""
    async with session_factory() as seed, seed.begin():
        tid_null, cid_null = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid_null, cid=cid_null, expires_at=None)
        tid_future, cid_future = await _seed_conversation(seed)
        await _seed_hold(
            seed, tid=tid_future, cid=cid_future,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    async with session_factory() as verify:
        assert await _has_active_hold(verify, tid=tid_null, cid=cid_null) is True
        assert await _has_active_hold(verify, tid=tid_future, cid=cid_future) is True


async def test_repository_no_hold_false(session_factory):
    """无 hold 行 → False。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
    async with session_factory() as verify:
        assert await _has_active_hold(verify, tid=tid, cid=cid) is False


# ---------------------------------------------------------------------------
# claim 谓词（_has_active_hold）——R1-AC7 判别
# ---------------------------------------------------------------------------


async def test_claim_expired_hold_not_deferred(session_factory):
    """R1-AC7：过期 active hold 不再 defer claim——claim 继续并进入 CLAIMED
    （fresh operation 建行）；非 ACTIVE_HOLD 拒绝。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=datetime.now(UTC) - timedelta(days=30))
    async with session_factory() as verify:
        outcome = await _claim(verify, tid, cid)
        assert (
            outcome.kind is not ClaimKind.DEFERRED
            or outcome.defer_reason != DeferReason.ACTIVE_HOLD
        ), (
            "过期 hold 不得以 ACTIVE_HOLD 拒绝 claim"
        )
        assert outcome.kind is ClaimKind.CLAIMED, "过期 hold 不阻塞 claim → 应 CLAIMED"


async def test_claim_unexpired_hold_still_defers(session_factory):
    """未过期 hold（NULL expires_at）仍 defer ACTIVE_HOLD（行为不变）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=None)
    async with session_factory() as verify:
        outcome = await _claim(verify, tid, cid)
        assert outcome.kind is ClaimKind.DEFERRED
        assert outcome.defer_reason is DeferReason.ACTIVE_HOLD


async def test_claim_future_expiry_hold_still_defers(session_factory):
    """未来到期 hold 仍 defer ACTIVE_HOLD。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(
            seed, tid=tid, cid=cid, expires_at=datetime.now(UTC) + timedelta(days=30)
        )
    async with session_factory() as verify:
        outcome = await _claim(verify, tid, cid)
        assert outcome.kind is ClaimKind.DEFERRED
        assert outcome.defer_reason is DeferReason.ACTIVE_HOLD


async def test_claim_expired_hold_does_not_bump_hold_revision(session_factory):
    """裁决一边界：读侧宽化不 bump ``hold_revision``（仍只由 create/release 推进）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=datetime.now(UTC) - timedelta(days=30))
    async with session_factory() as verify:
        await _claim(verify, tid, cid)
        revision = await verify.scalar(
            text(
                "SELECT hold_revision FROM metaedu.agent_conversations "
                "WHERE tenant_id = :tid AND id = :cid"
            ),
            {"tid": tid, "cid": cid},
        )
        assert revision == 0, "claim 不得 bump hold_revision"
