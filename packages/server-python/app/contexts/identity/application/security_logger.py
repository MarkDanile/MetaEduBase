"""BUG-017 Slice 4: 身份安全事件结构化日志（AC-6）。

记录注册 / 建用户 / 角色变更 / 启停的结果，供审计追溯。严格不记录密码、
Token、password_hash--这些字段即使误传进来也会被 redact。
"""
from __future__ import annotations

import logging
from typing import Any

_SECURITY_LOGGER = logging.getLogger("metaedu.security")

# 永不进日志的敏感字段名（密码 / token / hash）。
_SENSITIVE_KEYS = frozenset(
    {"password", "password_hash", "token", "access_token", "refresh_token", "secret"}
)


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    """剥离敏感字段，值永不落日志。"""
    return {k: "***" for k in payload if k in _SENSITIVE_KEYS} | {
        k: v for k, v in payload.items() if k not in _SENSITIVE_KEYS
    }


def log_security_event(
    *,
    event_type: str,
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    result: str = "success",
    ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """写一条身份安全事件日志。

    Args:
        event_type: register / admin_create_user / admin_update_role / admin_disable_user 等。
        actor_user_id: 操作者 user id（匿名注册为 None）。
        target_user_id: 被操作用户 id。
        result: success / denied / failed。
        ip: 请求来源 IP（可空）。
        detail: 额外上下文（敏感字段自动 redact）。
    """
    payload: dict[str, Any] = {
        "event": event_type,
        "actor": actor_user_id,
        "target": target_user_id,
        "result": result,
    }
    if ip is not None:
        payload["ip"] = ip
    if detail:
        payload["detail"] = _redact(detail)
    _SECURITY_LOGGER.info("security_event %s", event_type, extra=payload)
