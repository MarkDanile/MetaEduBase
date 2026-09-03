"""R1-S6-I3-D PR-D：production-neutral continuous ledger export / archive orchestration entry。

**Scope（plan §S6-14 item 1 + post-D2 rebaseline 注解）**：
thin composition of D1a ``export_ledger_segment_for_archive`` + D1b ``publish_ledger_segment``
两阶段 API；不引入 schema / migration / cursor / watermark；不接 scheduler caller；不实现
capability flip；不进入六 erase 入口生产可达路径。

**严格不变式（plan §S6-14 明确禁止）**：
- ❌ 不接 scheduler production caller
- ❌ 不做 D1b / D2 / S5 production wiring
- ❌ 不翻转 registry capability（external / runtime 仍 ``erase_available=False``）
- ❌ 不进入六 erase 入口生产可达
- ❌ 不修改 migration / schema / enum / CHECK
- ❌ 不实现 CLI / argparse / shell wrapper
- ❌ 不实现六 erase 任一入口

**Continuous export 语义（plan §S6-14 item 1 + 审计4）**：
"continuous" = 可重复调用同一 orchestration entry；每次返回当前 DB state 的 bounded
segment + D1b commit marker。**不**是 watermark推进 + cursor 表 + 增量累积。
每次调用 = fresh snapshot（受 ``MAX_RECORDS_PER_KIND = 10_000`` 硬限）。
caller 负责 cadence / 调度 / 并发 fork 防护（本模块不接管）。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition.s6i3_d_ledger_archive_sink import (
    LedgerArchiveSink,
    PublishOutcome,
    export_ledger_segment_for_archive,
    publish_ledger_segment,
)


async def export_and_archive_ledger_segment(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sink: LedgerArchiveSink,
    tenant_id: uuid.UUID,
) -> PublishOutcome:
    """Production-neutral orchestration entry：open RR+RO tx → D1b phase-1
    (D1a export + decoder 双校验) → commit → D1b phase-2 publish (pure sink I/O)。

    **不**修改 D1a / D1b 业务逻辑；**不**实现 cursor / watermark / scheduler接入。
    仅做 thin composition entry（plan §S6-14 item 1）。

    Args:
        session_factory: caller-managed ``async_sessionmaker``；orchestration 不持有
            session lifecycle 之外的状态。session 必须连接到 ``metaedu_test``（D1a hard
            boundary；不连接到 ``metaedu``）。
        sink: ``LedgerArchiveSink``（InMemoryLedgerArchiveSink for tests / MinIO adapter
            for production）。**caller**负责构造与配置 sink；orchestration 不实例化
            production sink，**不**触发 scheduler 接入。
        tenant_id: 严格规范 UUID；D1a / D1b 双侧 tenant binding 校验。

    Returns:
        ``PublishOutcome``（D1b 公开 dataclass）：
        - ``export_id`` = sha256(segment_bytes)[:16]
        - ``generation`` = 当前 tenant 单调推进
        - ``idempotent_retry`` = True 当同 export_id 同 marker key 已存在（同一 DB state 重试）

    Raises:
        ``PublishPreconditionFailedError``: phase-1 RR+RO / D1a decoder 校验失败
        ``LedgerArchiveError``（含子类）: phase-2 sink I/O 失败 / fork / generation
            regression / parent_export_id missing / segment digest mismatch / 现有
            marker payload diverges / archive unavailable

    Notes:
        - caller 责任：每 tenant 同一时刻只允许一个 publisher（V1 single-publisher
          fork fail-closed；orchestration 不加锁）。
        - caller 责任：连接 DB 必须为 ``metaedu_test``；orchestration 入口**不**主动
          校验（与 D1a 一致），由 DB hard boundary 在 D1a / D1b 内核 fail closed。
    """
    # Phase 1：caller-managed RR+RO 事务内 D1a export + D1a decoder 双侧校验。
    # **不**在事务内触发任何 sink I/O / retry / sleep（与 D1a / D1b B-1 契约一致）。
    exported: Any
    async with (
        session_factory() as session,
        session.begin(),
    ):
        # SET TRANSACTION ISOLATION LEVEL 必须是事务内首条语句（PostgreSQL 语义）。
        # D1a 入口 _assert_transaction_attrs() 会再次 SHOW transaction_isolation
        # / SHOW transaction_read_only 强校验；任何不满足立即抛 TX_ISOLATION_NOT_REPEATABLE_READ
        # / TX_NOT_READ_ONLY。
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        exported = await export_ledger_segment_for_archive(
            session, tenant_id=tenant_id
        )
    # 事务结束（async with session.begin() 块退出时自动 commit）

    # Phase 2：纯 sink I/O；不接 AsyncSession；不触发 DB I/O；任何 retry / sleep 仅在此处。
    return await publish_ledger_segment(
        sink=sink,
        tenant_id=tenant_id,
        segment_bytes=exported.segment_bytes,
        manifest=exported.manifest,
    )


__all__ = ["export_and_archive_ledger_segment"]
