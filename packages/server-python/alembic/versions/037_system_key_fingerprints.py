"""round-5 P1-2: system key fingerprints 表（V1 冻结契约强制）。

Revision ID: 037_system_key_fingerprints
Revises: 036_erasure_fence_empty_ingress
Create Date: 2026-07-29

round-4 P1-4 冻结了 ``actor_erasure_secret_version = 1``，但 round-5 P1-2 复审
指出：digest key version **未持久化**（Conversation/Message 表只存 64-hex digest，
无 version 列），生产把 secret A 换成 secret B、继续 version=1，启动和构造都会通过，
但历史 digest 仍成为无法溯源的孤儿--"禁止轮换 secret/version" 只是文案约定。

本迁移建 ``system_key_fingerprints`` 单行表，存储 V1 key 的非可逆 fingerprint
（``HMAC-SHA256(secret, "actor-erasure-v1-key-fingerprint")``，64-hex）。启动期
``validate_production_actor_erasure_key_fingerprint`` 计算 fingerprint 并与持久化值
比对：首次锁定（INSERT）、一致放行、**不一致 fail closed**（secret 被换，历史
digest 孤儿化）。fingerprint 不含 secret 明文（HMAC 单向），但可检测 secret 变更。

纯 expand：新增一张系统级表（非 tenant-scoped），不动 034/035/036 的 schema/
索引/约束。downgrade 删表（仅含启动期写入的 fingerprint 行，无业务数据）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "037_system_key_fingerprints"
down_revision: str | None = "036_erasure_fence_empty_ingress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "system_key_fingerprints"
_SCHEMA = "metaedu"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("key_name", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "set_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("key_name", name="pk_system_key_fingerprints"),
        sa.CheckConstraint(
            "char_length(fingerprint) = 64",
            name="ck_system_key_fingerprints_fingerprint",
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(_TABLE, schema=_SCHEMA)
