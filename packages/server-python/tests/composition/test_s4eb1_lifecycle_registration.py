"""R1-S4-E-B1：lifecycle registration port 真实 PostgreSQL 测试。

契约事实源：Plan §R1-S4-E E-1（B1 = `registered` 唯一正常生产者；`blocked/
unknown_scheme -> registered` 仅 scheme 明确识别 + adapter capability 验证通过）
+ E-5-2（集合 advisory lock）+ B5（db_local allowlist 冻结为空，禁猜测）。

**allowlist 冻结（B5）**：`_EXTERNAL_REF_SCHEME_ALLOWLIST` 为空集合——`db_local`
scheme 当前**不可达**（无生产级 db_local adapter / 无可证明 DB-local 格式），故
生产路径 ``register_external_object_ref`` 对任何非空 scheme 都 fail closed、
``promote_external_ref_to_registered`` 对任何 scheme 都保持 blocked。**promote 的
"scheme 已识别 + adapter capability 验证" 分支是冻结的 gate 定义**（未来 db_local
adapter 加入 allowlist 后同一入口放行）——本套件用 monkeypatch 把 allowlist 临时
扩展为含 ``db_local``，以真实 SQL 验证 gate 两条件各自生效与组合行为，不改变生产
空 allowlist。

判别点（E-6）：
- ``register_external_object_ref``：scheme 未识别 -> fail closed raise，**不写**
  `registered` 行（变异：删 allowlist 判定 -> 红）；scheme 已识别 -> 写 registered +
  幂等（不重复新建）。
- ``promote_external_ref_to_registered``：backfill 种 `blocked/unknown_scheme` 行 ->
  (a) scheme 未识别 -> 保持 blocked（E-6 未知 scheme 反例）；
  (b) scheme 已识别但 adapter 缺幂等重放/receipt lookup -> 保持 blocked（E-2b 硬前置）；
  (c) scheme 已识别 + adapter 满足前置 -> 转 registered + 清 blocked_reason + 更新
  ref_scheme（`ck_agent_external_refs_erase_evidence` 要求 registered 不带 reason）；
  (d) 已 registered/erased 的行不被覆盖（0 行命中 -> 返回当前态）。
- 锁序：register/promote 在集合 advisory lock 内（backfill 同款）。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_locks import transport_aggregate_key
from app.composition.agent_transport_backfill import _EXTERNAL_OWNER, OWNER_BY_TABLE
from app.composition.external_object_adapter import (
    ExternalEraseUnknown,
    ExternalObjectAdapter,
)
from app.composition.external_ref_lifecycle import (
    _EXTERNAL_REF_COLLECTION_OWNER_BY_SOURCE,
    _collection_owner,
    promote_external_ref_to_registered,
    ref_scheme_allowlist,
    register_external_object_ref,
)
from tests.contexts.agent_control_plane.helpers import TENANT_ID

pytestmark = pytest.mark.asyncio

_TABLE = "agent_workspace_outbox"
_ROW_ID = uuid.uuid4()
_REF_VALUE = "obj://staging/object/1"
_RECOGNIZED = "db_local"


class _CapableAdapter(ExternalObjectAdapter):
    """满足 E-2b 硬前置的 fake adapter（幂等重放 + 计数）。"""

    adapter_key = "fake-db-local"
    adapter_version = 1
    supports_idempotent_replay = True
    supports_receipt_lookup = False

    def __init__(self) -> None:
        self.calls = 0

    async def delete_object(self, **kwargs):
        self.calls += 1
        return ExternalEraseUnknown()

    async def receipt_lookup(self, **kwargs):
        return None


class _UnsupportedAdapter(_CapableAdapter):
    """缺幂等重放且缺 receipt lookup 的 adapter（E-2b 硬前置不满足）。"""

    supports_idempotent_replay = False
    supports_receipt_lookup = False


def _recognize_db_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """临时把 allowlist 扩展为含 ``db_local``（模拟未来 db_local 加入）。

    不改变生产空 allowlist（B5 冻结）；只让 promote/register 的「scheme 已识别」
    分支可被真实 SQL 验证。
    """
    import app.composition.external_ref_lifecycle as lifecycle

    monkeypatch.setattr(
        lifecycle, "_EXTERNAL_REF_SCHEME_ALLOWLIST", frozenset({_RECOGNIZED})
    )


async def _ensure_tenant(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, :isolation, true, :now, :now) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": TENANT_ID,
            "name": "s4eb1-tenant",
            "school_name": "s4eb1 school",
            "isolation": "shared",
            "now": now,
        },
    )
    await db_session.flush()


async def _seed_blocked_ref(db_session, *, ref_value: str = _REF_VALUE):
    """backfill 同款：登记 blocked/unknown_scheme 行（走生产 SQL 形态）。"""
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs ("
            "  id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "  source_table, source_row_id, erase_state, blocked_reason, "
            "  created_at, updated_at"
            ") VALUES (:id, :t, NULL, 'external.payload.v1', 'unknown', :rv, "
            "  :st, :sr, 'blocked', 'unknown_scheme', clock_timestamp(), clock_timestamp()) "
            "ON CONFLICT ON CONSTRAINT uq_agent_external_ref_source DO NOTHING"
        ),
        {
            "id": uuid.uuid4(),
            "t": TENANT_ID,
            "rv": ref_value,
            "st": _TABLE,
            "sr": _ROW_ID,
        },
    )
    await db_session.flush()


async def _fetch_ref(db_session, *, ref_value: str = _REF_VALUE):
    row = (
        await db_session.execute(
            text(
                "SELECT erase_state, blocked_reason, ref_scheme, receipt_digest "
                "FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :t AND source_table = :st "
                "  AND source_row_id = :sr AND ref_value = :rv"
            ),
            {"t": TENANT_ID, "st": _TABLE, "sr": _ROW_ID, "rv": ref_value},
        )
    ).one_or_none()
    return row


async def _seed_registered_ref(db_session, *, ref_scheme: str = _RECOGNIZED):
    """直接种 registered 行（绕过 promote 的 blocked 谓词）。"""
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_external_object_refs ("
            "  id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "  source_table, source_row_id, erase_state, created_at, updated_at"
            ") VALUES (:id, :t, NULL, 'external.payload.v1', :rs, :rv, "
            "  :st, :sr, 'registered', clock_timestamp(), clock_timestamp()) "
            "ON CONFLICT ON CONSTRAINT uq_agent_external_ref_source DO NOTHING"
        ),
        {
            "id": uuid.uuid4(),
            "t": TENANT_ID,
            "rs": ref_scheme,
            "rv": _REF_VALUE,
            "st": _TABLE,
            "sr": _ROW_ID,
        },
    )
    await db_session.flush()


async def test_ref_scheme_allowlist_is_empty_frozen():
    """B5 冻结：db_local allowlist 为空集合（无可证明 DB-local 格式）。"""
    assert ref_scheme_allowlist() == frozenset()


# --- 集合锁 owner 与 backfill 同源（E-5-2/D8，首轮 P0-1/P1-1 返修） --------


async def test_collection_owner_matches_backfill_for_all_ref_sources():
    """B1 集合锁 owner 与 backfill 对同一源行取的 owner 一致（同 advisory key）。

    变异杀手：把 ``_EXTERNAL_REF_COLLECTION_OWNER_BY_SOURCE`` 的任一表 owner 改成
    ``external.payload.v1``（旧实现）-> 本测试变红。覆盖 3 个 ref-bearing source
    （run_events 归 external、两 outbox 归 transport owner），与 backfill
    ``OWNER_BY_TABLE.get(table, _EXTERNAL_OWNER)`` 逐一比对。
    """
    ref_sources = ("agent_run_events", "agent_workspace_outbox", "agent_execution_outbox")
    for table in ref_sources:
        expected = OWNER_BY_TABLE.get(table, _EXTERNAL_OWNER)
        assert _collection_owner(table) == expected, (
            f"collection lock owner for {table!r} must match backfill "
            f"({expected!r}); mismatched advisory keys on the same source row "
            "break E-5-2/D8 serialization"
        )
        # 两方派生出的 advisory key 必须相同（owner 是 key 输入之一）。
        assert transport_aggregate_key(
            tenant_id=TENANT_ID,
            owner_key=_collection_owner(table),
            source_table=table,
            source_row_id=_ROW_ID,
        ) == transport_aggregate_key(
            tenant_id=TENANT_ID,
            owner_key=expected,
            source_table=table,
            source_row_id=_ROW_ID,
        )


async def test_collection_owner_map_only_contains_ref_bearing_sources():
    """锁 owner 映射只覆盖 ref-bearing source（其余表 fallback external owner）。

    防映射意外膨胀（如塞入 inbox 表）——B1 只登记 3 个 ref-bearing source。
    """
    assert set(_EXTERNAL_REF_COLLECTION_OWNER_BY_SOURCE) == {
        "agent_run_events",
        "agent_workspace_outbox",
        "agent_execution_outbox",
    }


# --- register：正常生产入口 ------------------------------------------------


async def test_register_unknown_scheme_fails_closed(db_session):
    """scheme 未识别（生产空 allowlist）-> register 拒绝，不写 registered 行。

    变异杀手：删 `scheme_is_recognized` 判定 -> 本测试变红。
    """
    await _ensure_tenant(db_session)
    with pytest.raises(ValueError, match="not in the recognized allowlist"):
        await register_external_object_ref(
            db_session,
            tenant_id=TENANT_ID,
            conversation_id=None,
            source_table=_TABLE,
            source_row_id=_ROW_ID,
            ref_scheme="db_local",
            ref_value=_REF_VALUE,
        )
    await db_session.flush()
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :t AND source_table = :st AND source_row_id = :sr"
            ),
            {"t": TENANT_ID, "st": _TABLE, "sr": _ROW_ID},
        )
    ).scalar()
    assert count == 0, "未识别 scheme 不得登记 registered 行"


async def test_register_recognized_scheme_sets_registered_and_idempotent(
    db_session, monkeypatch
):
    """allowlist 含 scheme 时 register 写 registered + 幂等（不重复新建）。

    模拟未来 db_local adapter 加入 allowlist 后的正常生产路径（staging/publish 登记）。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    created = await register_external_object_ref(
        db_session,
        tenant_id=TENANT_ID,
        conversation_id=None,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_scheme=_RECOGNIZED,
        ref_value=_REF_VALUE,
    )
    assert created is True
    await db_session.flush()
    row = await _fetch_ref(db_session)
    assert row.erase_state == "registered"
    assert row.blocked_reason is None

    created_again = await register_external_object_ref(
        db_session,
        tenant_id=TENANT_ID,
        conversation_id=None,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_scheme=_RECOGNIZED,
        ref_value=_REF_VALUE,
    )
    assert created_again is False
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :t AND source_table = :st AND source_row_id = :sr"
            ),
            {"t": TENANT_ID, "st": _TABLE, "sr": _ROW_ID},
        )
    ).scalar()
    assert count == 1


# --- promote：blocked/unknown_scheme -> registered 唯一受控入口 --------------


async def test_promote_unknown_scheme_keeps_blocked(db_session):
    """E-6 未知 scheme 反例：scheme 未识别（空 allowlist）-> 保持 blocked。"""
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme="db_local",
        adapter=_CapableAdapter(),
    )
    assert state == "blocked"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "blocked"
    assert row.blocked_reason == "unknown_scheme"
    assert row.ref_scheme == "unknown"


async def test_promote_adapter_without_prerequisite_keeps_blocked(
    db_session, monkeypatch
):
    """E-2b 硬前置：scheme 已识别但 adapter 缺幂等重放/receipt lookup -> 保持 blocked。

    变异杀手：promote 缺 `adapter_satisfies_prerequisite` 判定 -> 本测试变红。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_UnsupportedAdapter(),
    )
    assert state == "blocked"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "blocked"
    assert row.blocked_reason == "unknown_scheme"
    assert row.ref_scheme == "unknown", "未通过前置不得更新 ref_scheme"


async def test_promote_recognized_scheme_and_capable_adapter(db_session, monkeypatch):
    """scheme 明确识别 + adapter capability 验证通过 -> registered + 清 reason。

    变异杀手：promote 缺「blocked/unknown_scheme 谓词」-> 红（已 registered 行被覆盖）。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_CapableAdapter(),
    )
    assert state == "registered"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "registered"
    assert row.blocked_reason is None, "registered 行不得带 reason"
    assert row.ref_scheme == "db_local", "ref_scheme 更新为已识别值"
    assert row.receipt_digest is None


async def test_promote_does_not_overwrite_registered(db_session, monkeypatch):
    """已 registered 的行不被覆盖（0 行命中 -> 返回当前态，不降级）。"""
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_registered_ref(db_session)
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_CapableAdapter(),
    )
    assert state == "registered", "已 registered 行返回当前态，不覆盖"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "registered"
    assert row.blocked_reason is None


async def test_promote_does_not_overwrite_erased(db_session, monkeypatch):
    """已 erased 的行不被覆盖（0 行命中 -> 返回当前态，不降级）。

    变异杀手：把 promote 的 UPDATE 谓词从「blocked/unknown_scheme」放宽为任何
    blocked（如去掉 ``blocked_reason = 'unknown_scheme'`` 限定）或去掉谓词 ->
    本测试变红（erased 行被错误覆盖）。对应 docstring「已 registered/**erased**
    的行不被覆盖」——首轮 P2-2 补。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    # 把 blocked 行推进到 erased（带合法 receipt digest，满足
    # ck_agent_external_refs_erase_evidence：erased 必有 receipt_digest）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_external_object_refs "
            "SET erase_state = 'erased', blocked_reason = NULL, "
            "  receipt_digest = :rd, ref_scheme = 'db_local', "
            "  updated_at = clock_timestamp() "
            "WHERE tenant_id = :t AND source_table = :st "
            "  AND source_row_id = :sr AND ref_value = :rv"
        ),
        {
            "t": TENANT_ID,
            "st": _TABLE,
            "sr": _ROW_ID,
            "rv": _REF_VALUE,
            "rd": "a" * 64,
        },
    )
    await db_session.flush()
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_CapableAdapter(),
    )
    assert state == "erased", "已 erased 行返回当前态，不覆盖"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "erased", "已 erased 行不得被 promote 改回 registered"
    assert row.receipt_digest == "a" * 64, "receipt 证据保留"


async def test_promote_unknown_scheme_returns_real_state_when_already_registered(
    db_session, monkeypatch
):
    """scheme 未识别但行已被并发推进为 registered -> 返回真实态（不谎报 blocked）。

    变异杀手：把 promote 改回首轮 P1-2 的「gate 早退」实现（scheme 未识别
    直接 return 'blocked'，不取锁不读当前态）-> 本测试变红。锁定
    「锁内诚实返回实际当前态」语义。
    """
    # allowlist 保持空（scheme 未识别），但种一条已 registered 行。
    await _ensure_tenant(db_session)
    await _seed_registered_ref(db_session, ref_scheme="db_local")
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_CapableAdapter(),
    )
    assert state == "registered", "scheme 未识别也应返回行真实当前态（不谎报 blocked）"
    row = await _fetch_ref(db_session)
    assert row.erase_state == "registered"


async def test_promote_missing_row_returns_blocked(db_session, monkeypatch):
    """行不存在 -> 返回 blocked（保持 fail-closed 语义）。"""
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    state = await promote_external_ref_to_registered(
        db_session,
        tenant_id=TENANT_ID,
        source_table=_TABLE,
        source_row_id=_ROW_ID,
        ref_value=_REF_VALUE,
        ref_scheme=_RECOGNIZED,
        adapter=_CapableAdapter(),
    )
    assert state == "blocked"


# --- 并发串行化（真实 PostgreSQL 双连接，首轮 P2-2 补） -----------------------


async def test_concurrent_promote_serializes_to_single_registered(
    db_session, session_factory, monkeypatch
):
    """两个并发 promote 同一 blocked/unknown_scheme 行 -> 集合锁串行化，只一行 registered。

    变异杀手：把 promote 的集合锁 owner 改回 ``external.payload.v1``（与 backfill
    不同 key）——本测试虽不直接与 backfill 并发，但两 promote 之间仍由同 key 串行化；
    真正的变异判别是 ``test_collection_owner_matches_backfill_for_all_ref_sources``。
    本测试验证：并发下不重复推进、不产生重复行、返回态与行实际态一致。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    await db_session.commit()  # 提交基行，使并发连接可见。

    async def _promote_once() -> str:
        async with session_factory() as session, session.begin():
            return await promote_external_ref_to_registered(
                session,
                tenant_id=TENANT_ID,
                source_table=_TABLE,
                source_row_id=_ROW_ID,
                ref_value=_REF_VALUE,
                ref_scheme=_RECOGNIZED,
                adapter=_CapableAdapter(),
            )

    states = await asyncio.gather(*[_promote_once() for _ in range(4)])
    assert all(state == "registered" for state in states), (
        f"concurrent promote must all observe registered, got {states}"
    )

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND source_table = :st "
                    "  AND source_row_id = :sr AND ref_value = :rv"
                ),
                {"t": TENANT_ID, "st": _TABLE, "sr": _ROW_ID, "rv": _REF_VALUE},
            )
        ).scalar_one()
        row = await _fetch_ref(session)
    assert count == 1, "并发 promote 不得产生重复 ledger 行"
    assert row.erase_state == "registered"
    assert row.blocked_reason is None


async def test_concurrent_promote_does_not_overwrite_erased(
    db_session, session_factory, monkeypatch
):
    """并发 promote 命中已被推进为 erased 的行 -> 不覆盖、保留 receipt 证据。

    判别点（首轮 P1-2 补）：promote 若被改成无条件覆盖（删除或放宽
    ``blocked/unknown_scheme`` 谓词），在无并发的
    ``test_promote_does_not_overwrite_erased`` 中已变红；本测试补充**并发组合**：
    一行先从 blocked 推进为 erased，再并发 promote 同一行，最终仍为 erased。
    """
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await _seed_blocked_ref(db_session)
    await db_session.commit()

    # 先把基行推进为 erased（带合法 receipt digest，满足 erase_evidence）。
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs "
                "SET erase_state = 'erased', blocked_reason = NULL, "
                "  receipt_digest = :rd, ref_scheme = 'db_local', "
                "  updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND source_table = :st "
                "  AND source_row_id = :sr AND ref_value = :rv"
            ),
            {
                "t": TENANT_ID,
                "st": _TABLE,
                "sr": _ROW_ID,
                "rv": _REF_VALUE,
                "rd": "b" * 64,
            },
        )

    async def _promote_once() -> str:
        async with session_factory() as session, session.begin():
            return await promote_external_ref_to_registered(
                session,
                tenant_id=TENANT_ID,
                source_table=_TABLE,
                source_row_id=_ROW_ID,
                ref_value=_REF_VALUE,
                ref_scheme=_RECOGNIZED,
                adapter=_CapableAdapter(),
            )

    states = await asyncio.gather(*[_promote_once() for _ in range(3)])
    assert all(state == "erased" for state in states), (
        f"concurrent promote on erased row must observe erased, got {states}"
    )
    async with session_factory() as session:
        row = await _fetch_ref(session)
    assert row.erase_state == "erased", "并发 promote 不得把 erased 改回 registered"
    assert row.receipt_digest == "b" * 64, "receipt 证据保留"


async def test_concurrent_register_is_unique(
    db_session, session_factory, monkeypatch
):
    """6 个并发 register 同一 ref -> 唯一约束 + 集合锁 -> 恰一行，恰一个 created。"""
    _recognize_db_local(monkeypatch)
    await _ensure_tenant(db_session)
    await db_session.commit()

    async def _register_once() -> bool:
        async with session_factory() as session, session.begin():
            return await register_external_object_ref(
                session,
                tenant_id=TENANT_ID,
                conversation_id=None,
                source_table=_TABLE,
                source_row_id=_ROW_ID,
                ref_scheme=_RECOGNIZED,
                ref_value=_REF_VALUE,
            )

    created_flags = await asyncio.gather(*[_register_once() for _ in range(6)])
    assert sum(1 for flag in created_flags if flag) == 1, (
        f"exactly one concurrent register should win, got {created_flags}"
    )

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_external_object_refs "
                    "WHERE tenant_id = :t AND source_table = :st "
                    "  AND source_row_id = :sr AND ref_value = :rv"
                ),
                {"t": TENANT_ID, "st": _TABLE, "sr": _ROW_ID, "rv": _REF_VALUE},
            )
        ).scalar_one()
    assert count == 1, "并发 register 不得产生重复 ledger 行"
