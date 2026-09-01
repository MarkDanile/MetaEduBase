"""唯一、版本化的 conversation owner advisory lock key 实现。

R1-S1 只提供锁 key 原语与获取帮助；owner registry、fence 状态机与
purge saga 由相邻模块实现。所有 Adapter 必须复用
``conversation_owner_key``，不得自行 hash。
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 带版本前缀的 canonical bytes 前缀。独立常量确保与既有
# ``conversation_guard_key``（无前缀、仅 tenant+conversation 32 bytes）
# 处于不同输出域；未来 key 版本变化通过新增前缀常量表达。
_OWNER_KEY_V1_PREFIX = b"metaedu.agent.owner.v1\x00"


def conversation_owner_key(
    *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, owner_key: str
) -> int:
    """派生稳定 signed 64-bit owner advisory lock key。

    material = 版本前缀 + tenant bytes + conversation bytes + NUL + owner_key utf8。
    NUL 分隔避免 (conversation_id, owner_key) 拼接的前缀模糊。SHA-256 取前
    8 字节 big-endian signed，与 ``conversation_guard_key`` 位宽一致。
    """
    if not owner_key:
        raise ValueError("owner_key must be a non-empty registry identity")
    material = (
        _OWNER_KEY_V1_PREFIX
        + tenant_id.bytes
        + conversation_id.bytes
        + b"\x00"
        + owner_key.encode("utf-8")
    )
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


async def acquire_owner_lock(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner_key: str,
) -> None:
    """获取 transaction-scoped owner advisory lock。

    锁序固定为 Guard -> Conversation row -> owner advisory lock ->
    ErasureFence FOR UPDATE -> owner aggregate rows。本函数只承担
    owner lock 一步；调用方负责先取得 Guard 与 Conversation row。
    """
    key = conversation_owner_key(
        tenant_id=tenant_id, conversation_id=conversation_id, owner_key=owner_key
    )
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:owner_key)"),
        {"owner_key": key},
    )


# ---------------------------------------------------------------------------
# R1-S4-B transport/external aggregate 集合 advisory lock（Plan §R1-S4 B4）。
#
# 集合级并发正确性不能依赖 reconcile 子行或源 transport 行的行锁（子行锁无
# 范围锁、空集合无行可锁；源行是多态引用、无 FK，删除后 FOR UPDATE 命中 0 行）。
# 故集合锁用**事务级 advisory lock**（无需数据行即可获取，覆盖源行存在/已删/
# 空集合/新增成员全场景），key 用独立版本前缀与 guard/owner 分域。
# ---------------------------------------------------------------------------

# 带版本前缀的 canonical bytes 前缀。独立常量确保集合锁与既有
# ``conversation_guard_key``（无前缀）、``conversation_owner_key``
# （``metaedu.agent.owner.v1\x00``）处于不同输出域——域隔离避免跨域同 material
# 复用导致的系统性撞锁；SHA-256 截断 signed 64-bit 后理论碰撞仍存在，但同域内
# 偶发碰撞仅造成保守的额外串行化、不破坏正确性。
_TRANSPORT_AGG_KEY_V1_PREFIX = b"metaedu.agent.transport.agg.v1\x00"


def transport_aggregate_key(
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
    source_table: str,
    source_row_id: uuid.UUID,
) -> int:
    """派生稳定 signed 64-bit transport/external aggregate 集合 advisory lock key。

    material = 版本前缀 + tenant bytes + owner_key utf8 + NUL + source_table utf8
    + NUL + source_row_id bytes。NUL 分隔避免拼接的前缀模糊。SHA-256 取前 8 字节
    big-endian signed，与 owner/guard key 位宽一致。

    key 由 ``(tenant_id, owner_key, source_table, source_row_id)`` 四元组确定性
    派生，与 reconcile ledger 的源行唯一键一致——同一源行的全部 issue 集合共享
    一把集合锁。
    """
    if not owner_key:
        raise ValueError("owner_key must be a non-empty registry identity")
    if not source_table:
        raise ValueError("source_table must be a non-empty transport source table")
    material = (
        _TRANSPORT_AGG_KEY_V1_PREFIX
        + tenant_id.bytes
        + owner_key.encode("utf-8")
        + b"\x00"
        + source_table.encode("utf-8")
        + b"\x00"
        + source_row_id.bytes
    )
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


async def acquire_transport_aggregate_lock(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
    source_table: str,
    source_row_id: uuid.UUID,
) -> None:
    """获取 transaction-scoped transport/external aggregate 集合 advisory lock。

    全局锁序（D8，防 AB-BA）：生产路径
    ``Guard -> Conversation 行锁 -> owner advisory lock -> fence 重验 ->
    **本集合锁（最内层 owner aggregate 位置）** -> 源 transport 行 FOR UPDATE 投影写``。
    任何路径不得在 Guard/Conversation/owner/fence 之前获取本锁；纯 backfill/运维
    路径不经 Guard/owner 时**只**取本锁再读集/写投影，顺序一致（不引入第二顺序）。

    调用方负责在本锁内：读源行完整 issue 集（ledger 唯一事实源）-> 必要时
    INSERT ... ON CONFLICT DO NOTHING 登记新 issue -> 重算行内投影。本锁承担集合
    级串行化；单条 issue 的 ``(id, revision)`` CAS 仍护单 issue 状态机迁移。
    """
    key = transport_aggregate_key(
        tenant_id=tenant_id,
        owner_key=owner_key,
        source_table=source_table,
        source_row_id=source_row_id,
    )
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:agg_key)"),
        {"agg_key": key},
    )


# ---------------------------------------------------------------------------
# R1-S6-I3-D D2: M 类维护路径 advisory lock（Plan §S6-8.3 + 用户裁决 A）。
#
# retention/audit 每个事务先取 ``pg_advisory_xact_lock_shared``（与 replay
# 事务互斥）；replay 事务取 ``pg_advisory_xact_lock``（独占）。锁序必须早于
# Run/Conversation/owner/aggregate/row 锁（保留各自层级；本锁提供顶层互斥
# 串行化）。同一 stable namespace/scope — 单 global key（M 类是维护路径层
# 串行化，不按 tenant 切分）。
#
# ``maintenance_lock_key`` 必须保持稳定 + signed 64-bit + 独立前缀（避免与
# owner / transport aggregate 前缀撞域，跨部署互斥依赖固定前缀）。
# ---------------------------------------------------------------------------

_MAINTENANCE_KEY_V1_PREFIX = b"metaedu.agent.maintenance.v1\x00"


def maintenance_lock_key() -> int:
    """派生稳定 signed 64-bit maintenance advisory lock key（global）。

    material = 版本前缀 + ``b"global"``（不按 tenant 切分；M 类是维护路径
    串行化）。SHA-256 取前 8 字节 big-endian signed，与 ``conversation_owner_key``
    / ``conversation_guard_key`` / ``transport_aggregate_key`` 位宽一致。
    """
    material = _MAINTENANCE_KEY_V1_PREFIX + b"global"
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


async def acquire_maintenance_shared_lock(session: AsyncSession) -> None:
    """retention/audit worker transaction-level shared maintenance lock。

    与 replay 事务互斥（replay 取 exclusive；shared 申请在 exclusive 持锁
    期间阻塞）。任意 worker 可并发持有本 shared lock（多 retention/audit
    实例可同时跑）。
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock_shared(:key)"),
        {"key": maintenance_lock_key()},
    )


async def acquire_maintenance_exclusive_lock(session: AsyncSession) -> None:
    """replay executor transaction-level exclusive maintenance lock。

    独占串行化：与所有 shared 持有者互斥，且任意时刻仅允许一个 exclusive
    持有者。锁在事务 commit/rollback 时由 PG 自动释放（事务级语义）。"""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": maintenance_lock_key()},
    )
