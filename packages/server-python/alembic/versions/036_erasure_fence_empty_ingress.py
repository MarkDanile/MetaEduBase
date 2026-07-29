"""S2-C P1-5: 归一 baseline erasure-fence 空 ingress checkpoint/digest。

Revision ID: 036_erasure_fence_empty_ingress
Revises: 035_erasure_fence_ix_cleanup
Create Date: 2026-07-29

`034`/`035`（经 S1 backfill 与 S2 惰性建 fence）落地的 baseline ``active`` fence
存在「存 ``{}`` 却 hash 另一对象形状」的天生不一致：

- 持久化 ``ingress_checkpoint = {}``（空 JSON 对象）；
- ``ingress_digest`` 却是 ``canonical_digest({"ingress": {}, "schema_version": 1})``。

因此这些 fence 在首次正文写入前都不满足冻结契约
``ingress_digest = canonical_digest(ingress_checkpoint)``（Spec §5.1）。

本迁移把**仅从未写入正文**的 baseline fence（``ingress_checkpoint = {}`` 且
``revision = 1``，即建 fence 后无任何正文/checkpoint 推进）归一到规范空 checkpoint
``{"schema_version": 1, "sources": {}}`` 及其同源 digest。已推进正文 checkpoint 的
fence（``ingress_checkpoint <> {}`` 或 ``revision > 1``）不动——它们的 digest 由
S2-C ``advance_ingress_checkpoint_for_update`` 同事务写入，本就一致。

canonical digest 值由应用侧 ``app.shared.schemas.canonical_json.canonical_digest``
（JCS + SHA-256）计算后内联，迁移不 import 应用代码（保持迁移自包含、可离线执行）。
只改 baseline fence 的两列，不动 schema/索引/约束，可安全在线执行。

PR #511 合并后 ``035`` 已冻结，故以新增 ``036`` 处理（不原地修订 034/035）。
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "036_erasure_fence_empty_ingress"
down_revision: str | None = "035_erasure_fence_ix_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agent_erasure_fences"
_SCHEMA = "metaedu"

# 规范空 checkpoint 与其 JCS SHA-256 digest（由 canonical_digest 计算，见模块
# docstring）。canonical JSON：键排序、无空白、UTF-8。
_CANONICAL_EMPTY = '{"schema_version":1,"sources":{}}'
_CANONICAL_EMPTY_DIGEST = (
    "3e17b54f0c02a2006978c6b820174145df71c6d2a864d6f255cfb7d188e581a1"
)


def upgrade() -> None:
    # 仅归一「从未写入正文」的 baseline fence：checkpoint 为裸 {} 且 revision=1。
    # 经 op.get_bind() 传位置/命名参数，避免 JSON 内 ':' 被 op.execute 当作 bind。
    op.get_bind().execute(
        text(
            f'UPDATE "{_SCHEMA}"."{_TABLE}" '
            "SET ingress_checkpoint = CAST(:canonical AS jsonb), "
            "    ingress_digest = :digest "
            "WHERE ingress_checkpoint = '{}'::jsonb "
            "  AND revision = 1"
        ),
        {"canonical": _CANONICAL_EMPTY, "digest": _CANONICAL_EMPTY_DIGEST},
    )


def downgrade() -> None:
    # 回滚：把规范空 checkpoint 还原为裸 {}。digest 的旧形状（hash 另一对象）已
    # 从代码移除且不可复现；downgrade 仅还原 checkpoint 列用于开发回滚，digest
    # 保持规范值（与升级后一致，保证 digest==canonical_digest(checkpoint) 不破）。
    op.get_bind().execute(
        text(
            f'UPDATE "{_SCHEMA}"."{_TABLE}" '
            "SET ingress_checkpoint = '{}'::jsonb "
            "WHERE ingress_checkpoint = CAST(:canonical AS jsonb) "
            "  AND revision = 1"
        ),
        {"canonical": _CANONICAL_EMPTY},
    )
