"""BUG-018 Slice 1: AI App 管理端点必须认证 + 管理 RBAC。

red: 匿名调用 8 个管理端点应 401；非管理（teacher/student/leader/employee）
调用应 403；HIGH_PRIVILEGE_ROLES（super_admin/data_admin/admin）应 PASS。

AC-1：匿名调用所有管理端点均返回 401；非管理角色返回 403。
"""
from __future__ import annotations

import logging
import uuid

import pytest
from httpx import AsyncClient

from app.contexts.identity.application.security_logger import _SECURITY_LOGGER
from tests.contexts.identity._helpers import admin_token, register_and_login


def _uname(prefix: str) -> str:
    """用户名加 uuid 后缀避免全量套件残留冲突（client fixture 不清 users 表）。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _endpoint(method: str, path: str) -> tuple[str, str]:
    return method, path


# 8 个管理端点覆盖（SPEC Section "管理 API"）
_MANAGEMENT_ENDPOINTS = [
    ("GET", ""),
    ("GET", "/00000000-0000-0000-0000-000000000000"),
    ("POST", ""),
    ("PUT", "/00000000-0000-0000-0000-000000000000"),
    ("DELETE", "/00000000-0000-0000-0000-000000000000"),
    ("POST", "/00000000-0000-0000-0000-000000000000/publish"),
    ("POST", "/00000000-0000-0000-0000-000000000000/disable"),
    ("POST", "/00000000-0000-0000-0000-000000000000/enable"),
    ("POST", "/00000000-0000-0000-0000-000000000000/archive"),
    ("POST", "/00000000-0000-0000-0000-000000000000/regenerate-share-token"),
    ("POST", "/00000000-0000-0000-0000-000000000000/regenerate-api-token"),
]


@pytest.mark.parametrize("method, sub_path", _MANAGEMENT_ENDPOINTS)
@pytest.mark.asyncio
async def test_anonymous_management_endpoints_return_401(
    client: AsyncClient, method: str, sub_path: str
):
    """AC-1：匿名 -> 401。"""
    url = f"/api/v1/ai-apps{sub_path}"
    if method == "GET":
        resp = await client.get(url)
    elif method == "POST":
        resp = await client.post(url, json={})
    elif method == "PUT":
        resp = await client.put(url, json={})
    elif method == "DELETE":
        resp = await client.delete(url)
    assert resp.status_code == 401, f"{method} {url} 匿名期望 401，实得 {resp.status_code}"


@pytest.mark.asyncio
async def test_teacher_management_list_returns_403(client: AsyncClient):
    """AC-1：非管理 role（teacher）-> 403。"""
    token = await register_and_login(client, username=_uname("teacher_role"), role="teacher")
    resp = await client.get("/api/v1/ai-apps", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list(client: AsyncClient):
    """HIGH_PRIVILEGE 角色可调用 list。"""
    token = await admin_token(client)
    resp = await client.get("/api/v1/ai-apps", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_data_admin_can_list(client: AsyncClient):
    """data_admin 也是 HIGH_PRIVILEGE，应可调用。"""
    token = await register_and_login(
        client, username=_uname("data_admin_role"), role="data_admin"
    )
    resp = await client.get("/api/v1/ai-apps", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_security_logger_records_admin_denied(client: AsyncClient):
    """非管理调管理应同时写 security_event admin_access_denied 日志。"""
    records: list = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = _Collect(level=logging.DEBUG)
    _SECURITY_LOGGER.addHandler(h)
    _SECURITY_LOGGER.setLevel(logging.DEBUG)
    logging.disable(logging.NOTSET)
    _SECURITY_LOGGER.disabled = False
    try:
        token = await register_and_login(
            client, username=_uname("denied_audit"), role="teacher"
        )
        resp = await client.get(
            "/api/v1/ai-apps", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
    finally:
        _SECURITY_LOGGER.removeHandler(h)
    denied = [r for r in records if getattr(r, "event", None) == "admin_access_denied"]
    assert len(denied) >= 1, "teacher 调管理端点应写 admin_access_denied"
