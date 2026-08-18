"""R1-S5 SCH-D：adapter recovery descriptor 与历史 resolver（S5-C-3/4/5/6）。

契约：R1-S5-C S5-C-3 裁决 1——「owner_version 可重建的历史 adapter resolver」+
显式 fail closed，不新增持久 provenance。descriptor 为 immutable 值对象，六字段
全冻结；resolver 覆盖全部可能出现在持久 snapshot 中的历史 (owner_key,
owner_version)。

强不变量（S5-C-3）：descriptor 任一字段或 adapter 路由（owner_key → 具体实现
装配）变化必须 bump owner_version（新 version 新 descriptor，旧 descriptor 语义
不变）；历史 descriptor 与实现装配不得删除（删除即破坏旧 snapshot 可解析性）。

settlement 解析恢复事实**只用** frozen snapshot 的 (owner_key, owner_version) 经
resolver 取旧 descriptor；禁止「当前已安装 adapter 即旧 adapter」的假定——当前
descriptor 仅在 resolver 判定 owner_version == 当前 registry 版本时才与旧身份
一致。解析失败 / descriptor 命中但实现不可加载 → 输出态 6（零 adapter 调用，
不允许 fallback 当前实现）。

本模块只定义 descriptor / resolver / 实现装配接口；**不接线生产 adapter**——
组合根（生产 wiring）保持不可达，测试经显式注入 fake adapter。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.composition.agent_erasure_registry import require_owner

# S5-C-4 默认 settlement 自动恢复期限（descriptor 无历史覆盖时）。external/runtime
# 窗口态专用；transport/core owner 无 adapter 窗口不适用输出态 5/6。
DEFAULT_SETTLEMENT_DEADLINE = timedelta(days=7)
# S5-C-4 adapter 去重窗口默认（与 deadline 关系 = 必要条件 dedup_window >=
# settlement_deadline 才允许 settlement 自动 replay）。
DEFAULT_DEDUP_WINDOW = timedelta(days=14)


class RecoveryDescriptorError(Exception):
    """Recovery descriptor 解析/装配 fail-closed 信号（→ 输出态 6）。"""


class AdapterUnresolvableError(RecoveryDescriptorError):
    """历史 (owner_key, owner_version) 不在 resolver 域或实现不可加载。"""


@dataclass(frozen=True, slots=True)
class RecoveryDescriptor:
    """immutable recovery descriptor（S5-C-3 六字段，全冻结）。

    - ``adapter_key`` / ``adapter_version``：协议身份（idempotency/receipt 派生输入）。
    - ``supports_idempotent_replay``：幂等重放能力。
    - ``dedup_window``：idempotency key 去重窗口。
    - ``receipt_lookup_semantics_version``：receipt lookup 三态语义版本；**非空 ⇔
      supports_receipt_lookup == True**（lookup 能力位由语义版本的存在性表达，
      S5-C-6 replay-only 定义输入；无 lookup 能力 = 无语义版本）。
    - ``settlement_deadline``：该 owner-version 的 settlement 自动恢复期限。
    """

    adapter_key: str
    adapter_version: int
    supports_idempotent_replay: bool
    dedup_window: timedelta
    receipt_lookup_semantics_version: int | None
    settlement_deadline: timedelta

    @property
    def supports_receipt_lookup(self) -> bool:
        return self.receipt_lookup_semantics_version is not None


# ---------------------------------------------------------------------------
# code-defined 历史 descriptor 域（V1 全 owner；未来 owner_version bump 时在此
# 增补历史版本，不得删除既有行——S5-C-3 强不变量）。
# ---------------------------------------------------------------------------

def _descriptor_for(
    *,
    adapter_key: str,
    supports_idempotent_replay: bool,
    receipt_lookup_semantics_version: int | None,
    settlement_deadline: timedelta = DEFAULT_SETTLEMENT_DEADLINE,
    dedup_window: timedelta = DEFAULT_DEDUP_WINDOW,
) -> RecoveryDescriptor:
    return RecoveryDescriptor(
        adapter_key=adapter_key,
        adapter_version=1,
        supports_idempotent_replay=supports_idempotent_replay,
        dedup_window=dedup_window,
        receipt_lookup_semantics_version=receipt_lookup_semantics_version,
        settlement_deadline=settlement_deadline,
    )


# V1 固定 recovery descriptor（与 owner_registry V1 对齐）。adapter_key 与 owner_key
# 同构（external/runtime 各一；transport/core owner 无 adapter 窗口，其 descriptor
# 仅用于输出态映射——lookup/replay 位恒 False，不适用输出态 5/6）。
_RECOVERY_DESCRIPTORS: dict[tuple[str, int], RecoveryDescriptor] = {
    (
        "external.payload.v1",
        1,
    ): _descriptor_for(
        adapter_key="external.object.v1",
        supports_idempotent_replay=True,
        receipt_lookup_semantics_version=1,
    ),
    (
        "runtime.private.v1",
        1,
    ): _descriptor_for(
        adapter_key="runtime.session.v1",
        supports_idempotent_replay=True,
        receipt_lookup_semantics_version=1,
    ),
    (
        "workspace.transport.v1",
        1,
    ): _descriptor_for(
        adapter_key="workspace.transport.v1",
        supports_idempotent_replay=False,
        receipt_lookup_semantics_version=None,
    ),
    (
        "execution.transport.v1",
        1,
    ): _descriptor_for(
        adapter_key="execution.transport.v1",
        supports_idempotent_replay=False,
        receipt_lookup_semantics_version=None,
    ),
    (
        "workspace.core.v1",
        1,
    ): _descriptor_for(
        adapter_key="workspace.core.v1",
        supports_idempotent_replay=False,
        receipt_lookup_semantics_version=None,
    ),
    (
        "execution.core.v1",
        1,
    ): _descriptor_for(
        adapter_key="execution.core.v1",
        supports_idempotent_replay=False,
        receipt_lookup_semantics_version=None,
    ),
}


def resolve_adapter(owner_key: str, owner_version: int) -> RecoveryDescriptor:
    """按 frozen snapshot 的 (owner_key, owner_version) 取旧 recovery descriptor。

    解析失败（历史版本不在 resolver 域）→ raise ``AdapterUnresolvableError``（输出
    态 6，零 adapter 调用、reconcile-only）。
    """
    require_owner(owner_key)  # unknown owner 直接 fail closed
    descriptor = _RECOVERY_DESCRIPTORS.get((owner_key, owner_version))
    if descriptor is None:
        raise AdapterUnresolvableError(
            f"no recovery descriptor for {owner_key!r} version {owner_version}; "
            "historical adapter unresolvable, fail closed"
        )
    return descriptor


# ---------------------------------------------------------------------------
# adapter 实现装配（S5-C-3「descriptor 与实现装配是两个独立事实」）
# ---------------------------------------------------------------------------

AdapterInstance = object


class AdapterImplementationResolver(Protocol):
    """按 (owner_key, owner_version) 解析可调用 adapter 实例（lookup/replay 用）。

    组合根提供具体装配（生产 wiring 不可达）；测试注入 fake。解析失败（类已
    删除/不可导入/未知版本）→ 输出态 6（零 adapter 调用，不 fallback 当前实现）。
    """

    def __call__(self, *, owner_key: str, owner_version: int) -> AdapterInstance: ...


class FailClosedAdapterResolver:
    """默认实现装配 = 一律 fail closed（SCH-D 生产 wiring 不可达门禁）。

    SettlementService 默认使用本 resolver——任何 adapter 调用路径在未显式接线时
    落输出态 6（零调用），保证生产 erase 入口保持不可达。
    """

    def __call__(self, *, owner_key: str, owner_version: int) -> AdapterInstance:
        raise AdapterUnresolvableError(
            f"adapter implementation for {owner_key!r} v{owner_version} is not "
            "wired; production wiring unreachable, fail closed"
        )


__all__ = [
    "AdapterImplementationResolver",
    "AdapterUnresolvableError",
    "FailClosedAdapterResolver",
    "RecoveryDescriptor",
    "RecoveryDescriptorError",
    "resolve_adapter",
]
