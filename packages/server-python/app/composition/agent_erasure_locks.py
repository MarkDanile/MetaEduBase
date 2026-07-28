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
