"""S4-E-B1 lifecycle registration port（external.payload.v1）。

契约事实源：Plan §R1-S4-E E-1（`registered` 唯一正常生产者）+ B5（`db_local`
allowlist 冻结为空，禁猜测 scheme）。B1 是 ``registered`` 的**唯一正常生产者**；
external eraser（B2）只消费 ``registered`` 行，不生产。

- **``pending -> registered``（B1 登记）**：对象 staging/publish 时在 owner fence
  transaction 内登记并转 ``registered``（Spec §7.3「object 必须先写隔离 staging，
  再在 owner fence transaction 内登记/publish ref」）。当前仓库**没有生产级
  db_local staging adapter**（B5 allowlist 为空、无可证明 DB-local 格式）——故
  ``register_external_object_ref`` 对未识别 scheme **fail closed raise**（禁猜测），
  真实 db_local adapter 加入 allowlist 前该正常生产路径不可达（与 E-4：无 adapter
  -> external ``erase_available`` 保持 False 一致）。
- **``blocked/unknown_scheme -> registered``（仅当 scheme 明确识别 + adapter
  capability 验证通过）**：backfill 写 ``blocked/unknown_scheme``（``_register_
  external_ref`` 一律 ``unknown`` scheme）；``promote_external_ref_to_registered``
  是唯一允许把 ``blocked/unknown_scheme`` 行转 ``registered`` 的受控入口——仅当
  scheme 被明确识别（进入 allowlist）**且** adapter capability 验证通过（E-2b 硬
  前置）时放行（把 ``ref_scheme`` 更新为已识别值 + 清 ``blocked_reason``）；不满足
  保持 ``blocked``（E-6 未知 scheme 反例）。已 ``registered``/``erased`` 的行不覆盖
  （由 verify/后续流程 fail closed 暴露）。
- **锁序（E-5-2）**：本模块只写 ledger 行（不写 outbox `payload_ref` 源行），入口
  统一在**事务内先取集合 advisory lock**（``acquire_transport_aggregate_lock``，
  backfill 同款）——纯 backfill/运维路径不经 Guard/owner 只取集合锁再写，顺序一致
  （不引入第二顺序）；生产路径若未来写 outbox `payload_ref` 行必须按 D8 全局链
  ``Guard -> Conversation 行锁 -> owner advisory lock -> fence -> 集合锁 -> 源行``，
  本 Slice 不接线该写路径。
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_transport_aggregate_lock
from app.composition.external_object_adapter import (
    ExternalObjectAdapter,
    adapter_satisfies_prerequisite,
)

_EXTERNAL_OWNER = "external.payload.v1"


# B5 冻结：db_local allowlist 为空集合。**禁止猜测 scheme**——任何非空 scheme
# 值当前都不在 allowlist，登记一律 ``unknown`` + ``blocked/unknown_scheme``。
# S4-E 引入真实 DB-local staging adapter 时须先定义可证明的 ref 格式并加入本
# allowlist（配套新 migration 扩 ``ck_agent_external_refs_ref_scheme`` 语义/登记
# 规则），此前 ``db_local`` 不可达。
_EXTERNAL_REF_SCHEME_ALLOWLIST: frozenset[str] = frozenset()


def ref_scheme_allowlist() -> frozenset[str]:
    """只读暴露 scheme allowlist（B1 判定/测试断言用）。"""
    return _EXTERNAL_REF_SCHEME_ALLOWLIST


def scheme_is_recognized(ref_scheme: str) -> bool:
    """scheme 是否在 allowlist（B5：空集合 -> 一律 False；禁猜测）。"""
    return ref_scheme in _EXTERNAL_REF_SCHEME_ALLOWLIST


async def register_external_object_ref(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    source_table: str,
    source_row_id: uuid.UUID,
    ref_scheme: str,
    ref_value: str,
) -> bool:
    """受控登记 external object ref（``registered`` 唯一正常生产者入口）。

    正常生产路径：对象 staging/publish 时登记并转 ``registered``。``ref_scheme``
    必须被 allowlist 明确识别（B5 禁猜测）；未识别 fail closed raise——不写
    ``registered``（对象无法被保证可删除时不得进入待删窗口）。返回是否新建。

    幂等：唯一键 ``(tenant_id, source_table, source_row_id, ref_value)`` 命中既有
    行时 ON CONFLICT DO NOTHING（不覆盖已推进行）；既有 ``blocked/unknown_scheme``
    行不在此入口升级（升级须走 ``promote_external_ref_to_registered`` 的能力验证）。
    """
    if not scheme_is_recognized(ref_scheme):
        raise ValueError(
            f"ref_scheme {ref_scheme!r} is not in the recognized allowlist; "
            "cannot register a 'registered' external object ref (B5 禁猜测)"
        )
    await acquire_transport_aggregate_lock(
        session,
        tenant_id=tenant_id,
        owner_key=_EXTERNAL_OWNER,
        source_table=source_table,
        source_row_id=source_row_id,
    )
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_external_object_refs ("
                "  id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
                "  source_table, source_row_id, erase_state, created_at, updated_at"
                ") VALUES (:id, :t, :c, :o, :rs, :rv, :st, :sr, 'registered', "
                "  clock_timestamp(), clock_timestamp()) "
                "ON CONFLICT ON CONSTRAINT uq_agent_external_ref_source DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "c": conversation_id,
                "o": _EXTERNAL_OWNER,
                "rs": ref_scheme,
                "rv": ref_value,
                "st": source_table,
                "sr": source_row_id,
            },
        ),
    )
    return result.rowcount > 0


async def promote_external_ref_to_registered(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_table: str,
    source_row_id: uuid.UUID,
    ref_value: str,
    ref_scheme: str,
    adapter: ExternalObjectAdapter,
) -> str:
    """``blocked/unknown_scheme -> registered`` 唯一受控入口（E-1）。

    仅当 **scheme 明确识别（allowlist）+ adapter capability 验证通过（E-2b 硬
    前置）** 时放行：把 ``ref_scheme`` 更新为已识别值 + 清 ``blocked_reason`` +
    转 ``registered``（``ck_agent_external_refs_erase_evidence`` 要求 registered
    行不带 reason）。不满足保持 ``blocked``（E-6 未知 scheme 反例）。

    返回最终 erase_state（``'registered'`` 或 ``'blocked'``）。已推进
    ``registered``/``erased`` 的行不覆盖——0 行命中时读当前态返回（由 verify/后续
    流程 fail closed 暴露）。
    """
    if not scheme_is_recognized(ref_scheme):
        return "blocked"
    if not adapter_satisfies_prerequisite(adapter):
        return "blocked"
    await acquire_transport_aggregate_lock(
        session,
        tenant_id=tenant_id,
        owner_key=_EXTERNAL_OWNER,
        source_table=source_table,
        source_row_id=source_row_id,
    )
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "UPDATE metaedu.agent_external_object_refs "
                "SET erase_state = 'registered', blocked_reason = NULL, "
                "  ref_scheme = :rs, updated_at = clock_timestamp() "
                "WHERE tenant_id = :t AND source_table = :st "
                "  AND source_row_id = :sr AND ref_value = :rv "
                "  AND erase_state = 'blocked' AND blocked_reason = 'unknown_scheme'"
            ),
            {
                "t": tenant_id,
                "st": source_table,
                "sr": source_row_id,
                "rv": ref_value,
                "rs": ref_scheme,
            },
        ),
    )
    if result.rowcount == 1:
        return "registered"
    # 行不存在或已不在 blocked/unknown_scheme：读当前态返回（不覆盖已推进的
    # registered/erased 行）。
    current = (
        await session.execute(
            text(
                "SELECT erase_state FROM metaedu.agent_external_object_refs "
                "WHERE tenant_id = :t AND source_table = :st "
                "  AND source_row_id = :sr AND ref_value = :rv"
            ),
            {"t": tenant_id, "st": source_table, "sr": source_row_id, "rv": ref_value},
        )
    ).scalar()
    return current if current is not None else "blocked"
