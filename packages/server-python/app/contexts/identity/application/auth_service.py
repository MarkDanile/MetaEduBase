from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# BUG-017: JWT 根信任硬约束。公开默认值与最低强度阈值，生产启动校验引用。
JWT_DEFAULT_SECRET = "dev-only-change-in-production"
JWT_SECRET_MIN_LENGTH = 32
# round-7 P1：仓库已知 placeholder 拒绝表（公开值，长度 >=32 会通过强度校验，
# 直接用模板启动会把公开 JWT 密钥带入生产）。含 config 默认值 + deploy 模板值。
_KNOWN_JWT_PLACEHOLDERS = frozenset({
    JWT_DEFAULT_SECRET,
    "CHANGE_ME_random_jwt_secret_at_least_32_chars",
})


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


def validate_production_jwt_secret(cfg=settings) -> None:
    """BUG-017 AC-3: 生产环境启动校验 JWT 密钥，缺失 / default / 低强度 -> fail-fast。

    development 环境保留默认值便于本地启动；production 必须显式配置一个非
    默认、不少于 :data:`JWT_SECRET_MIN_LENGTH` 字符的密钥。部署遗漏
    ``JWT_SECRET`` 时用公开默认值运行是最危险的--默认 seed tenant/admin UUID
    固定可知，攻击者可用公开默认密钥伪造默认管理员 Token。
    """
    if getattr(cfg, "environment", "development") != "production":
        return
    secret = getattr(cfg, "jwt_secret", "") or ""
    if (
        not secret
        or secret in _KNOWN_JWT_PLACEHOLDERS
        or len(secret) < JWT_SECRET_MIN_LENGTH
    ):
        raise RuntimeError(
            "JWT_SECRET 在 production 环境必须显式配置为非默认、非仓库 placeholder、"
            f"不少于 {JWT_SECRET_MIN_LENGTH} 字符的值（当前不满足）。"
            "请设置 JWT_SECRET 环境变量为随机高熵值（例：openssl rand -hex 32）。"
        )
