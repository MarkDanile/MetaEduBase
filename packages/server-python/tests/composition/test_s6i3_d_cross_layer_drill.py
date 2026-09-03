"""R1-S6-I3-D PR-D 跨层 safety drill / contract verification。

**Scope（plan §S6-14 item 3 + PR-D 允许范围）**：D1a → D1b → D2 → restore-before-open gate
端到端真实 PG 串联，验证 §S6-12/§S6-13 路由表与判定方式在串联路径上的 fail-closed 一致性。

**严格边界（不复制既有层业务逻辑）**：
- 本测试**仅**做 callable composition：调 D1a export_ledger_segment_for_archive + D1b
  publish_ledger_segment + fetch_segment_bytes + decode_ledger_segment + reconstruct_owner_facts
  + D2 replay_archive_segment_for_tenant + D2 evaluate_restore_before_open
- **不**重写 D1a decoder 校验 / D1b 协议 / D2 6×5 路由矩阵 / D2 pass A / pass B 任一实现
- **不**新增 mutation script（既有 D1b 11/11 + D2 21/21 覆盖单层；drill 为 acceptance 层）

**测试数据库硬边界**：仅 ``metaedu_test``；不修改 schema / 不开新 transaction。
"""

from __future__ import annotations

import uuid

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.restore_replay import (
    RestoreReplayReport,
    evaluate_restore_before_open,
    replay_archive_segment_for_tenant,
)
from app.composition.s6i3_d_ledger_archive_sink import (
    InMemoryLedgerArchiveSink,
    PublishOutcome,
    fetch_segment_bytes,
    find_committed_tip,
)
from app.composition.s6i3_d_ledger_orchestration import (
    export_and_archive_ledger_segment,
)
from app.composition.s6i3_ledger_snapshot import (
    LedgerSnapshotError,
    decode_ledger_segment,
    reconstruct_owner_facts,
)
from tests.composition.s6i3_seeds import (
    _seed_checkpoint,
    _seed_conversation,
    _seed_operation,
    _seed_tenant,
)
from tests.conftest import TEST_DB_URL

logger = structlog.get_logger(__name__)

pytestmark = pytest.mark.asyncio

_ARCHIVE_BUCKET = "metaedu-ledger-archive"
_DIGEST = "a" * 64
_DIGEST_B = "b" * 64


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def drill_factory():
    """每个测试一个独立 engine/sessionmaker 复用 metaedu_test。"""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _assert_metaedu_test(session: AsyncSession) -> None:
    row = (await session.execute(text("SELECT current_database()"))).scalar_one()
    assert row == "metaedu_test", (
        f"DB hard boundary: current_database()={row!r} (expected 'metaedu_test'); aborting"
    )


async def _seed_minimal_acked(
    session: AsyncSession, *, tenant_label: str = "drill"
) -> dict[str, uuid.UUID]:
    """种最小可解码 + 可 D2 replay 的 ledger：1 tenant + 1 conversation (deleted,
    **title=NULL** 满足 workspace.core.v1 body-scan 零) + 1 operation (running, 已 archive)
    + 1 local owner checkpoint (acked, 64-hex ack_digest)。

    关键：ack_digest **必须**严格 64-hex lowercase（migration 034 ck_agent_purge_owner_ack
    + D1a 应用层门禁；D2 archive facts 严格来源要求）。
    """
    from app.composition.agent_erasure_registry import (
        capability_digest,
        registry_digest,
    )

    tid = await _seed_tenant(session, name=tenant_label)
    cid = await _seed_conversation(session, tid=tid)
    # 必须 deleted + purge_after 已过期；否则 D2 routing 走 SKIP/REPLAY_SKIP_ZERO_WRITE。
    # **workspace.core.v1 body-scan 零残留**（计划 §S6-8 item 5）：title / created_by /
    # archived_by / deleted_by 全部置 NULL + actor_state='redacted'（CHECK：
    # ck_agent_conv_actor 要求 created_by=NULL + creator_identity_digest 64-hex 时
    # actor_state 必须为 'redacted'）。
    # 否则 restore-before-open gate 的 ``scan_body`` 谓词（MessageModel/MessagePart/
    # ConversationUserState/author_id/actor_state）视这些为未清残留 → gate 阻断。
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversations "
            "SET state = 'deleted', purge_after = now() - interval '1 day', "
            "    title = NULL, title_source = 'none', "
            "    created_by = NULL, actor_state = 'redacted', "
            "    creator_identity_digest = :d, "
            "    archived_by = NULL, deleted_by = NULL "
            "WHERE id = :cid"
        ),
        {"cid": cid, "d": _DIGEST},
    )
    op_id = await _seed_operation(
        session, tid=tid, cid=cid, state="running", purge_rev=1
    )
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET revision = 1, lease_epoch = 0, "
            "registry_digest = :rd, retention_policy_digest = :rd "
            "WHERE id = :oid"
        ),
        {"rd": registry_digest(), "oid": op_id},
    )
    await _seed_checkpoint(
        session,
        tid=tid,
        purge_operation_id=op_id,
        owner_key="workspace.core.v1",
        owner_version=1,
        capability_digest=capability_digest("workspace.core.v1"),
        state="acked",
        attempt=1,
        ack_digest=_DIGEST,
    )
    await session.commit()
    return {"tid": tid, "cid": cid, "op_id": op_id}


# ---------------------------------------------------------------------------
# 跨层串联 happy path
# ---------------------------------------------------------------------------


async def test_cross_layer_drill_full_path_open_allowed(
    drill_factory,
) -> None:
    """完整路径：orchestration → D1b publish → fetch → D1a decode → reconstruct
    → D2 replay → restore-before-open gate open_allowed=True。

    验证 §S6-12 routing 表（completed + acked + local owner → VERIFY_ONLY）与 §S6-13
    判定方式在串联路径上不破。
    """
    factory = drill_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_acked(seed, tenant_label="drill-happy")

    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)

    # phase A: orchestration (caller-managed RR+RO + D1b phase-2)
    first_outcome = await export_and_archive_ledger_segment(
        factory, sink=sink, tenant_id=ids["tid"]
    )
    assert isinstance(first_outcome, PublishOutcome)
    assert first_outcome.generation == 1
    assert first_outcome.idempotent_retry is False

    # phase B: fetch_segment_bytes → D1a decoder round-trip（与 plan §S6-8 item 5 一致）
    tip = find_committed_tip(sink, tenant_id=str(ids["tid"]))
    assert tip is not None
    from app.composition.s6i3_d_ledger_archive_sink import CommitMarker

    marker = CommitMarker.from_bytes(tip.marker_bytes)
    fetched = fetch_segment_bytes(sink, tenant_id=str(ids["tid"]), marker=marker)
    manifest = decode_ledger_segment(fetched, expected_tenant_id=ids["tid"])

    # phase C: reconstruct_owner_facts（按 (operation_id, owner_key) 键）
    facts = reconstruct_owner_facts(manifest)
    assert len(facts) >= 1
    for (op_id_str, _owner_key), fact in facts.items():
        assert uuid.UUID(op_id_str) == ids["op_id"]
        assert fact.owner_key == "workspace.core.v1"
        assert fact.checkpoint_state == "acked"
        assert fact.ack_digest == _DIGEST
        assert fact.runtime_per_binding_proof_available is False

    # phase D: D2 replay_archive_segment_for_tenant（restore_replay 主体）
    replay_report: RestoreReplayReport = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=ids["tid"]
    )
    # 6×5 路由：running + acked → NO_REPEAT（**不**调 participant）
    assert replay_report.error is None
    assert replay_report.owners_no_repeat >= 1
    assert replay_report.owners_local_cleared == 0  # NO_REPEAT ≠ LOCAL_CLEARED
    assert replay_report.has_blocking_finding() is False

    # phase E: restore-before-open gate
    gate_report = await evaluate_restore_before_open(
        factory,
        tenant_id=ids["tid"],
        replay_report=replay_report,
        runtime_proof_c_present=False,
    )
    assert gate_report.open_allowed is True, (
        f"gate must allow open on happy path; blocked_reasons={gate_report.blocked_reasons}"
    )


# ---------------------------------------------------------------------------
# Continuous export = fresh-snapshot series（审计4 决策：无 watermark/cursor）
# ---------------------------------------------------------------------------


async def test_cross_layer_drill_continuous_export_advances_generation(
    drill_factory,
) -> None:
    """同一 DB state 第二次调 orchestration → 同 ``export_id``（D1a 字节稳定）
    但 generation 单调推进（D1b commit-graph 单调；fresh snapshot 非 idempotent retry）。

    **不**引入 cursor / watermark / 增量状态表 —— 仅依赖 D1a 字节确定性 +
    D1b commit-graph tip walking。验证 audit 4 决策"continuous export = fresh snapshot series"。
    """
    factory = drill_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_acked(seed, tenant_label="drill-cont")

    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)

    first = await export_and_archive_ledger_segment(
        factory, sink=sink, tenant_id=ids["tid"]
    )
    assert first.idempotent_retry is False
    assert first.generation == 1

    second = await export_and_archive_ledger_segment(
        factory, sink=sink, tenant_id=ids["tid"]
    )
    # D1a 字节稳定 → 同 export_id（segment_sha256[:16]）。D1b commit-graph 单调 →
    # generation=2（**不**走 idempotent retry 路径 —— generation 不匹配既有 marker key）。
    assert second.export_id == first.export_id, (
        "D1a 字节稳定契约违反：同 DB state 两次 export 应得相同 segment_bytes "
        "→ 相同 export_id；非 cursor/watermark 累积"
    )
    assert second.generation == first.generation + 1, (
        "D1b commit-graph 单调推进；同 DB state 第二次 publish 仍写新 marker"
    )
    assert second.idempotent_retry is False


# ---------------------------------------------------------------------------
# Gate fail-closed：runtime_proof_c_present → blocked
# ---------------------------------------------------------------------------


async def test_cross_layer_drill_gate_blocks_on_runtime_proof_c(
    drill_factory,
) -> None:
    """Gate 消费 runtime_proof_c_present=True → restore-before-open 保持关闭（plan §S6-15）。

    与 user 裁决 5 项（runtime per-binding proof = c）一致：archived completed runtime
    缺 per-binding proof 即 fail-closed。
    """
    factory = drill_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_acked(seed, tenant_label="drill-c-block")

    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    await export_and_archive_ledger_segment(
        factory, sink=sink, tenant_id=ids["tid"]
    )

    replay_report = await replay_archive_segment_for_tenant(
        factory, sink=sink, tenant_id=ids["tid"]
    )

    gate_report = await evaluate_restore_before_open(
        factory,
        tenant_id=ids["tid"],
        replay_report=replay_report,
        runtime_proof_c_present=True,
        # **唯一**触发 RUNTIME_BINDING_EVIDENCE_UNPROVABLE:runtime_proof_c_present
    )
    assert gate_report.open_allowed is False
    assert any(
        reason.startswith("RUNTIME_BINDING_EVIDENCE_UNPROVABLE:runtime_proof_c_present")
        for reason in gate_report.blocked_reasons
    )


# ---------------------------------------------------------------------------
# D1a decoder 失败注入（cross-tenant injection）→ orchestration 失败
# ---------------------------------------------------------------------------


async def test_cross_layer_drill_cross_tenant_decoder_rejects(
    drill_factory,
) -> None:
    """跨 tenant 解码 D1b segment（expected_tenant_id ≠ actual tenant）→ LedgerSnapshotError。

    验证 D1b 边界：sink 端 segment 字节必须按 caller expected_tenant_id 解码；错位立即
    fail-closed。orchestration 不绕 D1a decoder。
    """
    factory = drill_factory
    async with factory() as seed:
        await _assert_metaedu_test(seed)
        ids = await _seed_minimal_acked(seed, tenant_label="drill-cross")

    sink = InMemoryLedgerArchiveSink(bucket=_ARCHIVE_BUCKET)
    await export_and_archive_ledger_segment(
        factory, sink=sink, tenant_id=ids["tid"]
    )

    tip = find_committed_tip(sink, tenant_id=str(ids["tid"]))
    assert tip is not None
    from app.composition.s6i3_d_ledger_archive_sink import CommitMarker

    marker = CommitMarker.from_bytes(tip.marker_bytes)
    fetched = fetch_segment_bytes(sink, tenant_id=str(ids["tid"]), marker=marker)

    # **故意**用错 tenant 解码 → TENANT_BINDING_MISMATCH
    wrong_tid = uuid.uuid4()
    with pytest.raises(LedgerSnapshotError) as exc_info:
        decode_ledger_segment(fetched, expected_tenant_id=wrong_tid)
    assert exc_info.value.reason == "TENANT_BINDING_MISMATCH"


# ---------------------------------------------------------------------------
# Orchestration DB 边界硬校验：禁止 metaedu，仅 metaedu_test
# ---------------------------------------------------------------------------


async def test_cross_layer_drill_asserts_metaedu_test(
    drill_factory,
) -> None:
    """orchestration 必须 assert session_factory 连 metaedu_test；连接其他 DB
    （包括 metaedu）→ 立即 fail closed（DB hard boundary）。

    **禁止** drop / truncate / reseed / rebuild metaedu。本测试**仅**断言当前会话 database。
    """
    factory = drill_factory
    async with factory() as session:
        row = (await session.execute(text("SELECT current_database()"))).scalar_one()
        assert row == "metaedu_test", (
            f"PR-D hard boundary: current_database()={row!r}; "
            "orchestration must only run against metaedu_test"
        )
