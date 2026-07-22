"""REQ-058 Slice 1: tenant-scoped 配置 service。

Internal MCP / DD Catalog / Skill binding 等 tenant 级配置从 settings 全局单值
迁到 ``metaedu.tenant_scoped_config`` 表，按 ``(tenant_id, config_key)`` 唯一。

跨 tenant 隔离：tenant A 的配置对 tenant B 不可见（AC-4）。
fail-closed：未配置 key 抛 ``TenantConfigNotFoundError``；``get_config_or`` 提供
settings 兜底场景的 default 回退。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.infrastructure.models import TenantScopedConfigModel


class TenantConfigNotFoundError(LookupError):
    """Raised when a tenant-scoped config key is not set."""


class TenantConfigService:
    """CRUD for tenant-scoped configuration rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_config(self, tenant_id: uuid.UUID, key: str) -> Any:
        """读取 tenant 配置；未配置抛 :class:`TenantConfigNotFoundError`。

        返回值可为 dict / list / 标量（由 config_key 语义决定，JSONB 任意 JSON）。
        """
        stmt = select(TenantScopedConfigModel).where(
            TenantScopedConfigModel.tenant_id == tenant_id,
            TenantScopedConfigModel.config_key == key,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise TenantConfigNotFoundError(
                f"tenant {tenant_id} 未配置 {key!r}"
            )
        return row.config_value

    async def get_config_or(
        self, tenant_id: uuid.UUID, key: str, *, default: Any,
    ) -> Any:
        """读取 tenant 配置；未配置返回 ``default``（供 settings 兜底场景）。"""
        try:
            return await self.get_config(tenant_id, key)
        except TenantConfigNotFoundError:
            return default

    async def set_config(
        self,
        tenant_id: uuid.UUID,
        key: str,
        value: Any,
        *,
        updated_by: uuid.UUID,
    ) -> None:
        """UPSERT tenant 配置（同 key 覆盖）。"""
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = insert(TenantScopedConfigModel).values(
            tenant_id=tenant_id,
            config_key=key,
            config_value=value,
            updated_by=updated_by,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "config_key"],
            set_=dict(
                config_value=value,
                updated_by=updated_by,
                updated_at=now,
            ),
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_configs(self, tenant_id: uuid.UUID) -> list[dict]:
        """列出该 tenant 全部配置（不含其他 tenant）。"""
        stmt = select(TenantScopedConfigModel).where(
            TenantScopedConfigModel.tenant_id == tenant_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "tenant_id": str(r.tenant_id),
                "config_key": r.config_key,
                "config_value": r.config_value,
                "updated_by": str(r.updated_by) if r.updated_by else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
