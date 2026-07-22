"""Tests for CredentialRef: 引用名格式 / resolve / fail-closed / 无 secret 泄漏.

REQ-044 Task 2 (spec §4.3, AC-3): the credential boundary. Only the env
key *name* is ever stored, validated, or surfaced in errors; the value
exists only in the process environment at call time and must never appear
in exceptions or logs.
"""
from __future__ import annotations

import logging

import pytest

from app.contexts.mcp_registry.domain.mcp_server import (
    CredentialRef,
    CredentialUnavailableError,
)

VALID_NAMES = [
    "QCC_MCP_TOKEN",
    "INTERNAL_MCP_TOKEN",
    "MCP_TEST_TOKEN",
    "TEST_MCP_CRED_OK",
    "TEST_MCP_CRED_BEARER",
    "TEST_MCP_CRED_REPR",
    "CANARY_MCP_TOKEN",
    "EMPTY_MCP_CRED",
    "MISSING_MCP_CRED",
    "PROBE_MCP_MISSING_TOKEN",
]
INVALID_NAMES = [
    "qcc_token",      # 小写开头
    "Qcc_Token",      # 含小写
    "HAS SPACE",      # 空格
    "HAS-DASH",       # 符号
    "1ABC",           # 数字开头
    "",               # 空串
    "QCC.TOKEN",      # 点号
    # BUG-019 AC-1: 非 MCP secret 命名空间拒绝
    "JWT_SECRET",     # 黑名单命中
    "DATABASE_URL",   # 黑名单命中
    "DEEPSEEK_API_KEY",  # 黑名单命中
    "PROBE_TOKEN",    # 不在 MCP 命名空间
    "MY_SECRET",      # 通配 *SECRET*
    "DB_PASSWORD",    # 黑名单命中
]


@pytest.mark.parametrize("name", VALID_NAMES)
def test_valid_env_key_names_pass(name: str):
    assert CredentialRef(name).env_key == name


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_invalid_env_key_names_raise(name: str):
    with pytest.raises(ValueError, match="credential_ref|命名空间|黑名单"):
        CredentialRef(name)


def test_resolve_returns_env_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TEST_MCP_CRED_OK", "expected-secret")
    cred = CredentialRef("TEST_MCP_CRED_OK").resolve()
    assert cred.raw == "expected-secret"
    assert cred.header_value == "Bearer expected-secret"


def test_resolve_strips_redundant_bearer_prefix(monkeypatch: pytest.MonkeyPatch):
    """env 值若误带 ``Bearer `` 前缀会被剥离 — 客户端自行加 scheme。"""
    monkeypatch.setenv("TEST_MCP_CRED_BEARER", "Bearer expected-secret")
    cred = CredentialRef("TEST_MCP_CRED_BEARER").resolve()
    assert cred.raw == "expected-secret"
    assert cred.header_value == "Bearer expected-secret"


def test_resolve_value_repr_is_redacted(monkeypatch: pytest.MonkeyPatch):
    """AuthCredential 的 repr/str 绝不暴露 secret — 防 traceback/log 泄漏。"""
    monkeypatch.setenv("TEST_MCP_CRED_REPR", "expected-secret")
    cred = CredentialRef("TEST_MCP_CRED_REPR").resolve()
    assert "expected-secret" not in repr(cred)
    assert "expected-secret" not in str(cred)
    assert "redacted" in repr(cred)


def test_resolve_missing_env_fails_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """缺失 env -> CredentialUnavailableError；message 只含引用名。"""
    monkeypatch.delenv("MISSING_MCP_CRED", raising=False)
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(CredentialUnavailableError) as exc_info,
    ):
        CredentialRef("MISSING_MCP_CRED").resolve()
    assert "MISSING_MCP_CRED" in str(exc_info.value)


def test_resolve_empty_env_value_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """空串 env 视为缺失 — fail-closed。"""
    monkeypatch.setenv("EMPTY_MCP_CRED", "")
    with pytest.raises(CredentialUnavailableError):
        CredentialRef("EMPTY_MCP_CRED").resolve()


def test_secret_value_never_leaks_to_errors_or_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """secret 值不出现在任何异常 message 或日志记录中（AC-3）。

    用一个 canary 值：先 set 并 resolve（成功路径），再 unset 触发
    CredentialUnavailableError（失败路径），最后断言 canary 不出现在
    异常 message / 任何 caplog 记录中；引用名可以出现。
    """
    canary = "leak-canary-9f8e7d6c5b"
    monkeypatch.setenv("CANARY_MCP_TOKEN", canary)
    ref = CredentialRef("CANARY_MCP_TOKEN")

    with caplog.at_level(logging.DEBUG):
        assert ref.resolve().raw == canary
        monkeypatch.delenv("CANARY_MCP_TOKEN")
        with pytest.raises(CredentialUnavailableError) as exc_info:
            ref.resolve()

    message = str(exc_info.value)
    assert "CANARY_MCP_TOKEN" in message  # 引用名可见
    assert canary not in message  # 值不可见
    for record in caplog.records:
        assert canary not in record.getMessage()
