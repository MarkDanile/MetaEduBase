"""REQ-058 Slice 1b: Internal MCP / DD Catalog tenant-scoped binding resolver。

优先从 ``tenant_scoped_config`` 读 binding（per-caller-tenant），未配置时
fallback 到 ``settings`` 全局值；两者皆无则 ``ConfigurationError``（fail-closed）。

- ``resolve_internal_mcp_tenant(caller_tenant_id, config_service)`` -> UUID
- ``resolve_dd_catalog_id(caller_tenant_id, config_service)`` -> UUID
"""
from __future__ import annotations

import uuid

from app.config import settings
from app.contexts.identity.application.tenant_config_service import TenantConfigService


class ConfigurationError(RuntimeError):
    """Raised when binding is missing in both DB and settings."""


async def _resolve(
    caller_tenant_id: uuid.UUID,
    config_service: TenantConfigService,
    *,
    config_key: str,
    settings_attr: str,
    value_key: str,
) -> uuid.UUID:
    """公共解析逻辑：DB -> settings -> ConfigurationError。"""
    try:
        binding = await config_service.get_config(caller_tenant_id, config_key)
    except Exception:
        binding = None
    if isinstance(binding, dict) and value_key in binding:
        try:
            return uuid.UUID(binding[value_key])
        except (TypeError, ValueError):
            pass
    fallback = getattr(settings, settings_attr, "")
    if fallback:
        try:
            return uuid.UUID(fallback)
        except (TypeError, ValueError):
            pass
    raise ConfigurationError(
        f"{config_key} 未配置：tenant {caller_tenant_id} "
        f"DB 无 binding + settings.{settings_attr} 空"
    )


async def resolve_internal_mcp_tenant(
    caller_tenant_id: uuid.UUID, config_service: TenantConfigService,
) -> uuid.UUID:
    """解析 Internal MCP server 实际查询的 tenant_id（按 caller tenant binding）。"""
    return await _resolve(
        caller_tenant_id, config_service,
        config_key="internal_mcp_binding",
        settings_attr="internal_mcp_tenant_id",
        value_key="tenant_id",
    )


async def resolve_dd_catalog_id(
    caller_tenant_id: uuid.UUID, config_service: TenantConfigService,
) -> uuid.UUID:
    """解析 DD internal query 的 catalog_id（按 caller tenant binding）。"""
    return await _resolve(
        caller_tenant_id, config_service,
        config_key="dd_catalog_binding",
        settings_attr="dd_internal_query_catalog_id",
        value_key="catalog_id",
    )
