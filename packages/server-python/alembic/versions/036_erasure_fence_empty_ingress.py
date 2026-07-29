"""S2-C P1-5: 归一 baseline erasure-fence 空 ingress checkpoint/digest。

Revision ID: 036_erasure_fence_empty_ingress
Revises: 035_erasure_fence_ix_cleanup
Create Date: 2026-07-29

`034`/`035`（经 S1 backfill 与 S2 惰性建 fence）落地的 legacy baseline fence 存在
「存 ``{}`` 却 hash 另一对象形状」的天生不一致：

- 持久化 ``ingress_checkpoint = {}``（空 JSON 对象）；
- ``ingress_digest = canonical_digest({"ingress": {}, "schema_version": 1})``（legacy
  digest，S1/S2-A 冻结代码可确定）。

因此这些 fence 在首次正文写入前都不满足冻结契约
``ingress_digest = canonical_digest(ingress_checkpoint)``（Spec §5.1）。

upgrade（P1 复审修订）：把**精确 legacy pair**
（``ingress_checkpoint = {} AND ingress_digest = LEGACY_EMPTY_DIGEST``）归一到规范空
checkpoint ``{"schema_version": 1, "sources": {}}`` 及其同源 digest。

- 不依赖 ``revision``：S2-A 可推进 fence revision 而未推进 ingress，``revision>1``
  的 legacy 行同样需修复；``revision`` 不是 legacy 空 checkpoint 的可靠标记。
- 不匹配「任意 digest」：未知 digest（异常/损坏数据）**保持不动**，不静默洗成正常
  ——留待验证/reconcile。
- 已推进正文 checkpoint 的 fence（``ingress_checkpoint <> {}``）不动——它们的
  digest 由 S2-C ``advance_ingress_checkpoint_for_update`` 同事务写入，本就一致。

downgrade（P1 复审修订）：同时还原 legacy checkpoint ``{}`` 与 legacy digest（旧
digest 从冻结代码可复现），保证降级中间态两列一致；不留「checkpoint={} + 新结构
digest」的失配。

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
# legacy baseline 形状：checkpoint={} + digest=canonical_digest(
# {"ingress": {}, "schema_version": 1})（S1/S2-A 冻结代码可确定）。
_LEGACY_EMPTY_DIGEST = (
    "f7552c7ea13f39feea276636a18d0553fe9f2ee545f3dfae8efcc4bf37f61d6f"
)


def upgrade() -> None:
    # 精确匹配 legacy pair（checkpoint={} AND digest=legacy），不依赖 revision、
    # 不匹配未知 digest。经 op.get_bind() 传参避免 JSON 内 ':' 被当作 bind。
    op.get_bind().execute(
        text(
            f'UPDATE "{_SCHEMA}"."{_TABLE}" '
            "SET ingress_checkpoint = CAST(:canonical AS jsonb), "
            "    ingress_digest = :new_digest "
            "WHERE ingress_checkpoint = '{}'::jsonb "
            "  AND ingress_digest = :legacy_digest"
        ),
        {
            "canonical": _CANONICAL_EMPTY,
            "new_digest": _CANONICAL_EMPTY_DIGEST,
            "legacy_digest": _LEGACY_EMPTY_DIGEST,
        },
    )


def downgrade() -> None:
    # 同时还原 legacy checkpoint {} 与 legacy digest（两列一致），不留
    # 「checkpoint={} + 新 digest」失配。只回退规范空 pair，不碰其他行。
    op.get_bind().execute(
        text(
            f'UPDATE "{_SCHEMA}"."{_TABLE}" '
            "SET ingress_checkpoint = '{}'::jsonb, "
            "    ingress_digest = :legacy_digest "
            "WHERE ingress_checkpoint = CAST(:canonical AS jsonb) "
            "  AND ingress_digest = :new_digest"
        ),
        {
            "canonical": _CANONICAL_EMPTY,
            "legacy_digest": _LEGACY_EMPTY_DIGEST,
            "new_digest": _CANONICAL_EMPTY_DIGEST,
        },
    )
