"""R1-S4-B transport/external ledger ORM（migration 040，coordination infrastructure）。

两张 ledger 表属于跨 workspace/execution 的 control-plane coordination
infrastructure，由 composition 持有（与 ``agent_erasure_*`` 同层），不建跨
bounded-context 外键或 ORM cascade：

- ``agent_transport_scope_reconcile``（D3 三态 reconcile ledger）：transport scope
  回填/异常解决的**唯一事实源**。4 张 transport 表上的行内
  ``scope_reconcile_state`` 只是派生只读投影，必须与 ledger 同事务写入。
- ``agent_external_object_refs``（D5 external ref ledger）：所有 ref-bearing source
  （RunEvent/两张 outbox 的 ``payload_ref``）的 erase 状态机与 receipt 证据。

CHECK/唯一键/索引由 migration 040 持有；ORM 只映射列（约束在 DB 层强制）。
``erase_available`` 保持 False（本模块不接线 eraser）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# 注册 ``metaedu.tenants`` Table 到共享 metadata，使下方 ForeignKeyConstraint
# （``metaedu.tenants.id``）可解析。仅 import 副作用，不直接使用其 ORM 类。
from app.contexts.identity.infrastructure import models as _identity_models  # noqa: F401
from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransportScopeReconcileModel(Base):
    """D3 三态 reconcile ledger（transport scope 唯一事实源）。"""

    __tablename__ = "agent_transport_scope_reconcile"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["metaedu.tenants.id"],
            name="fk_agent_transport_reconcile_tenant",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(40), nullable=False)
    source_table: Mapped[str] = mapped_column(String(40), nullable=False)
    source_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reconcile_class: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    resolution_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExternalObjectRefModel(Base):
    """D5 external ref ledger（erase 状态机 + receipt 证据）。"""

    __tablename__ = "agent_external_object_refs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["metaedu.tenants.id"],
            name="fk_agent_external_refs_tenant",
        ),
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    owner_key: Mapped[str] = mapped_column(
        String(40), nullable=False, default="external.payload.v1"
    )
    ref_scheme: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_value: Mapped[str] = mapped_column(String(500), nullable=False)
    source_table: Mapped[str] = mapped_column(String(40), nullable=False)
    source_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    erase_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    receipt_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
