"""Shared actor erasure digest helper（composition coordination）。

R1-S2 S2-D/E round-2 P2-2：actor audit digest 与 V1 key fingerprint 逻辑从
``workspace_erasure_participant`` 私有提取为 composition/shared 公开版本化 helper，
由 workspace 与 execution 两 participant 共用，避免跨 context 私有依赖或双实现
漂移。

- ``actor_audit_digest``：tenant-scoped 不可逆 actor audit digest（Spec §7.1）。
  ``HMAC(HMAC("{version}:{secret}", tenant_id), actor_id)``（SHA-256），版本混入
  key 派生（防跨版本碰撞）、tenant-scoped 派生 key、密钥隔离（独立
  ``actor_erasure_secret``，非 jwt_secret）。digest 不含 actor UUID 明文、不可逆；
  不同 tenant/secret/version 产生不同 digest；可复现。64-hex。
- V1 冻结契约（S2-D/E round-4/5）：digest key version **未持久化**（表只存 64-hex
  digest），轮换 secret/version 会使历史 digest 成为无法溯源的孤儿，故 migration
  落地持久化 digest version 之前，生产 ``actor_erasure_secret_version`` 冻结为 1、
  **禁止轮换** secret（启动期 fingerprint 比对 + 构造器禁覆盖全局 key 强制）。
- ``validate_production_actor_erasure_secret``：生产启动校验 secret 强度 + 版本冻结。
- ``validate_production_actor_erasure_key_fingerprint``：生产启动期校验 V1 key
  fingerprint（upsert 持久化，首次锁定 / 不一致 fail closed / 常量时间比较 / 异常
  不泄露 fingerprint）。

本模块组合既有 ``SystemKeyFingerprintModel``（agent_workspace coordination ORM），
是 control-plane coordination infrastructure（Spec §5），不成为业务正文事实源。
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.agent_workspace.infrastructure.models import (
    SystemKeyFingerprintModel,
)

# 生产环境 actor_erasure_secret 强度阈值（S2-D/E round-3 P1-4：启动期 + 构造期双重校验）。
ACTOR_ERASURE_SECRET_MIN_LENGTH = 32
# 非生产环境空 secret 退化到此占位（仅 dev/test，生产 fail-fast 不走到这里）。
_ACTOR_ERASURE_SECRET_DEV_PLACEHOLDER = "dev-only-actor-erasure-secret"
# round-7 P1：仓库已知 placeholder 拒绝表（公开值，长度 >=32 会通过强度校验，
# 直接用模板启动会把公开 actor key fingerprint 锁入 037，V1 冻结期不可轮换）。
# 含 dev 占位 + deploy 模板值。
_KNOWN_ACTOR_ERASURE_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        _ACTOR_ERASURE_SECRET_DEV_PLACEHOLDER,
        "CHANGE_ME_random_actor_erasure_secret_at_least_32_chars",
    }
)

# 生产环境 actor_erasure_secret 必须显式设置（P1-2：fail-fast，不与 jwt_secret 共用）。
_PROD_ENVS: frozenset[str] = frozenset({"production"})

# round-5 P1-2：V1 key fingerprint 持久化键名（system_key_fingerprints.key_name）。
ACTOR_ERASURE_V1_KEY_NAME = "actor_erasure_v1"
# round-5 P1-2：fingerprint 域分隔符（与 actor digest 的 tenant+actor 域隔离）。
_ACTOR_ERASURE_KEY_FINGERPRINT_DOMAIN = b"actor-erasure-v1-key-fingerprint"


def actor_audit_digest(
    *, secret: str, secret_version: int, tenant_id: uuid.UUID, actor_id: uuid.UUID
) -> str:
    """tenant-scoped 不可逆 actor audit digest（Spec §7.1）。

    ``HMAC(HMAC("{version}:{secret}", tenant_id), actor_id)``（SHA-256）：版本混入
    key 派生（防跨版本碰撞）、tenant-scoped 派生 key、密钥隔离（独立
    ``actor_erasure_secret``，非 jwt_secret）。digest 不含 actor UUID 明文、不可逆；
    不同 tenant/secret/version 产生不同 digest；可复现。64-hex。round-4/5 P1-2 V1
    冻结：digest version 未持久化，migration 落地前生产禁止轮换 secret/version。

    由 workspace（Conversation/Message）与 execution（Run/TurnInput）两 participant
    共用，保证同 tenant + 同 actor + 同 key 产生同 digest（跨 context 一致）。
    """
    versioned_key = f"{secret_version}:{secret}".encode()
    tenant_key = hmac.new(versioned_key, tenant_id.bytes, hashlib.sha256).digest()
    return hmac.new(tenant_key, actor_id.bytes, hashlib.sha256).hexdigest()


def validate_production_actor_erasure_secret(cfg=settings) -> None:
    """round-3 P1-4 / round-4 P1-4：生产环境启动校验 actor erasure secret 强度
    + 版本冻结契约。

    development 环境保留空值（退化到 dev 占位）便于本地启动；production 必须显式
    配置一个不少于 :data:`ACTOR_ERASURE_SECRET_MIN_LENGTH` 字符的 secret。round-4
    P1-4：digest key version 未持久化（表只存 64-hex digest），轮换会使历史 digest
    成为无法溯源的孤儿，故生产 ``actor_erasure_secret_version`` 冻结为 1，禁止
    轮换直到 migration 落地持久化 digest version。在 app lifespan 调用。
    """
    if getattr(cfg, "environment", "development") != "production":
        return
    secret = getattr(cfg, "actor_erasure_secret", "") or ""
    version = int(getattr(cfg, "actor_erasure_secret_version", 1))
    if (
        not secret
        or secret in _KNOWN_ACTOR_ERASURE_PLACEHOLDERS
        or len(secret) < ACTOR_ERASURE_SECRET_MIN_LENGTH
    ):
        raise RuntimeError(
            "ACTOR_ERASURE_SECRET 在 production 环境必须显式配置为非仓库 placeholder、"
            f"不少于 {ACTOR_ERASURE_SECRET_MIN_LENGTH} 字符的高强度值（当前不满足）。"
            "请设置 ACTOR_ERASURE_SECRET 环境变量为随机高熵值（例：openssl rand -hex 32；"
            "与 JWT_SECRET 隔离；V1 冻结期禁止轮换，详见 config 注记）。"
        )
    if version != 1:
        raise RuntimeError(
            f"ACTOR_ERASURE_SECRET_VERSION 在 production 必须为 1（digest key version "
            f"未持久化，轮换会使历史 digest 成为无法溯源的孤儿，当前 {version}）；"
            "需先落地 migration 持久化 digest version 后才能 bump 版本轮换。"
        )


def actor_erasure_key_fingerprint(secret: str) -> str:
    """round-5 P1-2：V1 key 非可逆 fingerprint（检测 secret 变更，不泄露 secret）。

    ``HMAC-SHA256(secret, _ACTOR_ERASURE_KEY_FINGERPRINT_DOMAIN)`` -> 64-hex。与
    actor digest 的区别：digest 混入 tenant_id + actor_id（per-actor），fingerprint
    只混入固定域分隔符（per-key），用于启动期比对持久化值。fingerprint 不含 secret
    明文（HMAC 单向），但 secret 变更必然改变 fingerprint，可检测轮换。域分隔符与
    actor digest 隔离，确保 fingerprint 不能被误当作 actor digest 或反之。
    """
    return hmac.new(
        secret.encode(), _ACTOR_ERASURE_KEY_FINGERPRINT_DOMAIN, hashlib.sha256
    ).hexdigest()


async def validate_production_actor_erasure_key_fingerprint(
    session: AsyncSession, cfg=settings
) -> None:
    """round-5 P1-2：生产环境启动期校验 actor erasure secret V1 key fingerprint。

    计算 fingerprint 并与 ``system_key_fingerprints`` 持久化值比对：
    - 首次（无行）：INSERT 锁定 fingerprint（upsert 防多 worker 首启竞争）。
    - 一致：放行。
    - 不一致：fail closed（secret 被换，历史 digest 孤儿化）。

    与 :func:`validate_production_actor_erasure_secret`（同步强度+版本校验）互补：
    后者防弱密钥/版本 bump，本函数防 secret 静默替换。非生产跳过（dev/test 无
    持久化 fingerprint 需求）。在 app lifespan 调用（需 DB session），**必须在**
    :func:`validate_production_actor_erasure_secret` 之后调用（依赖其强度+版本前置）。

    round-6 P2-2：本函数**不自行 commit**--调用方须用 ``async with
    session_factory.begin() as session`` 持有事务（成功自动提交、异常自动回滚），
    避免校验失败前提交调用方已有写入。多 worker 并发首启由 PG 行锁串行化。
    """
    if getattr(cfg, "environment", "development") != "production":
        return
    secret = getattr(cfg, "actor_erasure_secret", "") or ""
    if not secret:
        raise RuntimeError(
            "validate_production_actor_erasure_key_fingerprint called with empty "
            "secret; validate_production_actor_erasure_secret must run first"
        )
    fingerprint = actor_erasure_key_fingerprint(secret)
    # upsert + returning：原子处理多 worker 首启竞争。returning 非 None = 本次插入
    # （fingerprint 是自己的，必然一致）；None = 冲突（行已存在），需 re-read 比对。
    # round-6 P2-2：不在校验函数内 commit--由调用方（lifespan ``async with
    # session_factory.begin()``）持有事务，成功才提交、失败自动回滚。多 worker
    # 并发首启时，第二个 INSERT 会被 PG 行锁阻塞直到首个事务提交/回滚，再走
    # on_conflict 分支 re-read 比对，不会误判 "row vanished"。
    stmt = (
        pg_insert(SystemKeyFingerprintModel)
        .values(
            key_name=ACTOR_ERASURE_V1_KEY_NAME,
            fingerprint=fingerprint,
        )
        .on_conflict_do_nothing(index_elements=[SystemKeyFingerprintModel.key_name])
        .returning(SystemKeyFingerprintModel.fingerprint)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        return  # 首次锁定，fingerprint 是自己的（调用方提交）。
    existing = await session.scalar(
        select(SystemKeyFingerprintModel.fingerprint).where(
            SystemKeyFingerprintModel.key_name == ACTOR_ERASURE_V1_KEY_NAME
        )
    )
    # 冲突分支：行已存在（并发首启对端已提交或历史锁定），existing 必非 None。
    if existing is None:
        raise RuntimeError(
            "system_key_fingerprints row vanished after upsert conflict; "
            "concurrent migration/downgrade in progress?"
        )
    # round-6 P2-3：常量时间比较（fingerprint 是密钥 verifier，防时序侧信道），
    # 异常文本不泄露 existing/current 值（固定消息 HMAC 可离线验证密钥猜测，
    # 不应扩散到日志）。
    if not hmac.compare_digest(existing, fingerprint):
        raise RuntimeError(
            "ACTOR_ERASURE_SECRET 在 production 不一致：持久化 fingerprint 与当前"
            "不匹配。secret 被替换会使历史 actor digest 成为无法溯源的孤儿"
            "（digest key version 未持久化，V1 冻结期禁止轮换 secret）。"
            "需先落地 migration 持久化 digest version 后才能轮换。"
        )


def resolve_actor_erasure_secret(
    *,
    audit_secret: str | None,
    audit_secret_version: int | None,
    environment: str | None = None,
) -> tuple[str, int]:
    """解析 participant 构造期的 actor erasure secret/version。

    生产环境：必须来自 ``settings`` 全局配置（启动期 fingerprint 已校验一致性），
    调用方不得注入覆盖。非生产：允许测试显式注入 secret/version（digest 派生测试），
    缺省回退 settings + dev 占位。

    返回 ``(secret, version)``，version 缺省/非法回退 1。
    """
    env = (
        environment
        if environment is not None
        else getattr(settings, "environment", "development")
    )
    if env in _PROD_ENVS:
        secret = settings.actor_erasure_secret
        version = settings.actor_erasure_secret_version
        if (
            not secret
            or secret in _KNOWN_ACTOR_ERASURE_PLACEHOLDERS
            or len(secret) < ACTOR_ERASURE_SECRET_MIN_LENGTH
        ):
            raise RuntimeError(
                "actor_erasure_secret must be a non-placeholder high-entropy value "
                f"(>= {ACTOR_ERASURE_SECRET_MIN_LENGTH} chars) in production; "
                "refusing to derive actor audit digests from a weak/empty/known secret"
            )
        if version != 1:
            raise RuntimeError(
                f"actor_erasure_secret_version must be 1 in production (frozen; "
                f"digest version not persisted, rotation would orphan historical "
                f"digests), got {version}"
            )
        return secret, version
    secret = (
        audit_secret if audit_secret is not None else settings.actor_erasure_secret
    )
    version = (
        audit_secret_version
        if audit_secret_version is not None
        else settings.actor_erasure_secret_version
    )
    return secret or _ACTOR_ERASURE_SECRET_DEV_PLACEHOLDER, version if version >= 1 else 1


__all__ = [
    "ACTOR_ERASURE_SECRET_MIN_LENGTH",
    "ACTOR_ERASURE_V1_KEY_NAME",
    "actor_audit_digest",
    "actor_erasure_key_fingerprint",
    "resolve_actor_erasure_secret",
    "validate_production_actor_erasure_key_fingerprint",
    "validate_production_actor_erasure_secret",
]
