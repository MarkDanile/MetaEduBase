"""BUG-017 Slice 1: JWT 信任边界 fail-fast（AC-3, AC-4）。

生产环境启动时 JWT 密钥缺失 / 为公开默认值 / 低强度 -> 阻断启动；
开发环境保留默认值便于本地。用公开默认密钥伪造的 Token 在生产（不同
密钥）下解码失败 -> 401（AC-4）。
"""
from types import SimpleNamespace

import pytest

from app.contexts.identity.application.auth_service import (
    create_access_token,
    decode_access_token,
    validate_production_jwt_secret,
)

_DEFAULT_SECRET = "dev-only-change-in-production"
_VALID_SECRET = "a" * 48  # 48 chars, clearly above the 32 floor


def _settings(*, environment: str, jwt_secret: str) -> SimpleNamespace:
    return SimpleNamespace(environment=environment, jwt_secret=jwt_secret)


# AC-3: 生产启动缺失 / default / 低强度 secret -> fail-fast


def test_production_missing_jwt_secret_raises():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_jwt_secret(_settings(environment="production", jwt_secret=""))


def test_production_default_jwt_secret_raises():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_jwt_secret(
            _settings(environment="production", jwt_secret=_DEFAULT_SECRET)
        )


def test_production_short_jwt_secret_raises():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_jwt_secret(
            _settings(environment="production", jwt_secret="short-weak-secret")
        )


def test_production_valid_jwt_secret_allowed():
    # 不 raise 即通过
    validate_production_jwt_secret(
        _settings(environment="production", jwt_secret=_VALID_SECRET)
    )


def test_development_default_secret_allowed():
    # 开发环境保留默认值，不 raise
    validate_production_jwt_secret(
        _settings(environment="development", jwt_secret=_DEFAULT_SECRET)
    )


# AC-4: 公开默认密钥伪造的 Token 在生产密钥下被拒


def test_default_secret_signed_token_rejected_under_production_secret(monkeypatch):
    """攻击者用公开默认密钥伪造 admin Token；生产用不同密钥 -> decode None -> 401。"""
    from app.config import settings

    forged_token = create_access_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "tid": "00000000-0000-0000-0000-000000000001",
        }
    )
    # 生产密钥与默认值不同
    monkeypatch.setattr(settings, "jwt_secret", _VALID_SECRET)
    assert decode_access_token(forged_token) is None


@pytest.mark.asyncio
async def test_lifespan_blocks_startup_in_production_with_default_secret(monkeypatch):
    """AC-3 端到端：production + 默认 secret -> lifespan 进入即 raise，进程不进入服务态。"""
    from app.config import settings
    from app.main import app, lifespan

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", _DEFAULT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        async with lifespan(app):
            pass
