"""R1 code-defined owner registry 与 capability negotiation。

owner key/version/capability digest 是协议字段，固定写死在代码中，不使用
Python 类名、模块路径或运行时随机顺序。registry snapshot 与 digest 按
owner_key 字典序排序，保证顺序稳定。unknown owner、版本变化或缺失
capability 一律 fail closed。

R1-S2 S2-D：``workspace.core.v1`` 的 eraser 已由
``WorkspaceErasureParticipant`` 实现（正文清除 + body scan + ACK），其
``erase_available=True``；其余 owner 的 eraser 仍待 S3/S4 实现，保持
``erase_available=False``，调用 ``require_capability(..., "erase")`` fail closed。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.schemas.canonical_json import canonical_digest


class OwnerRegistryError(Exception):
    """Base class for fail-closed owner registry verdicts."""


class UnknownOwnerError(OwnerRegistryError):
    pass


class OwnerRegistryChangedError(OwnerRegistryError):
    pass


class OwnerCapabilityUnavailableError(OwnerRegistryError):
    pass


@dataclass(frozen=True, slots=True)
class OwnerDefinition:
    owner_key: str
    owner_version: int
    capabilities: tuple[str, ...]
    # ``erase_available=True`` 表示该 owner 的 eraser 已安装（可经
    # ``require_capability(owner, "erase")`` 放行）。S2-D 为 workspace.core.v1
    # 翻 True；其余 owner 待 S3/S4。
    erase_available: bool


# V1 固定 owner（Spec §4.1）。capabilities 只描述 owner 持有的正文/引用类别，
# 不保存正文或 secret。顺序在代码中不承载语义；对外 snapshot 一律排序。
# S2-D：workspace.core.v1 eraser 已实现（WorkspaceErasureParticipant），
# erase_available=True；其余 owner 待 S3/S4。
_OWNER_DEFINITIONS: tuple[OwnerDefinition, ...] = (
    OwnerDefinition(
        owner_key="workspace.core.v1",
        owner_version=1,
        capabilities=(
            "conversation_title",
            "message_part_body",
            "actor_identity",
            "user_state",
        ),
        erase_available=True,
    ),
    OwnerDefinition(
        owner_key="workspace.transport.v1",
        owner_version=1,
        capabilities=("workspace_outbox_payload", "workspace_inbox_receipt"),
        erase_available=False,
    ),
    OwnerDefinition(
        owner_key="execution.core.v1",
        owner_version=1,
        capabilities=(
            "run_context_body",
            "run_output_body",
            "compatibility_output",
            "run_event_payload",
            # S3-B round-1 P1-2：execution 表直接主体标识（Run/TurnInput created_by）
            # purge 时清除 + HMAC digest（Spec §7.1「等直接主体标识」）。与
            # workspace.core.v1 actor_identity 同名 capability。
            "actor_identity",
        ),
        # S3-D：ExecutionErasureParticipant 已实现，但 erase_available 保持 False
        # 直到 participant + final scan + ACK 测试同 commit 翻 True（待测试就位）。
        erase_available=False,
    ),
    OwnerDefinition(
        owner_key="execution.transport.v1",
        owner_version=1,
        capabilities=("execution_outbox_payload", "execution_inbox_receipt"),
        erase_available=False,
    ),
    OwnerDefinition(
        owner_key="external.payload.v1",
        owner_version=1,
        capabilities=("external_object_ref", "staging_object"),
        erase_available=False,
    ),
    OwnerDefinition(
        owner_key="runtime.private.v1",
        owner_version=1,
        capabilities=("runtime_session_ref", "runtime_spool"),
        erase_available=False,
    ),
)

_OWNERS_BY_KEY: dict[str, OwnerDefinition] = {
    owner.owner_key: owner for owner in _OWNER_DEFINITIONS
}


def owner_registry() -> list[OwnerDefinition]:
    """按 owner_key 字典序返回固定 owner 定义。"""
    return sorted(_OWNER_DEFINITIONS, key=lambda owner: owner.owner_key)


def capability_digest(owner_key: str) -> str:
    """单个 owner 能力集合的 canonical digest。"""
    owner = require_owner(owner_key)
    return canonical_digest(
        {
            "capabilities": sorted(owner.capabilities),
            "erase_available": owner.erase_available,
            "owner_key": owner.owner_key,
            "owner_version": owner.owner_version,
            "schema_version": 1,
        }
    )


def registry_snapshot() -> list[dict[str, object]]:
    """排序后的 (owner_key, owner_version, capability_digest) 列表。"""
    return [
        {
            "owner_key": owner.owner_key,
            "owner_version": owner.owner_version,
            "capability_digest": capability_digest(owner.owner_key),
        }
        for owner in owner_registry()
    ]


def snapshot_digest(snapshot: list[dict[str, object]]) -> str:
    """对任意（含持久化的）registry snapshot 计算 canonical digest。

    与 ``registry_digest()`` 同一 canonical 形式，但作用于传入的 snapshot——
    用于校验持久化 operation 的 ``registry_snapshot`` 与其 ``registry_digest``
    是否内部一致，避免“重新生成快照再 digest”与持久化对象脱节。
    """
    return canonical_digest({"owners": snapshot, "schema_version": 1})


def registry_digest() -> str:
    """registry snapshot 的 canonical digest。"""
    return snapshot_digest(registry_snapshot())


def require_owner(owner_key: str) -> OwnerDefinition:
    owner = _OWNERS_BY_KEY.get(owner_key)
    if owner is None:
        raise UnknownOwnerError(f"unknown erasure owner key: {owner_key!r}")
    return owner


def require_owner_version(owner_key: str, owner_version: int) -> OwnerDefinition:
    owner = require_owner(owner_key)
    if owner.owner_version != owner_version:
        raise OwnerRegistryChangedError(
            f"owner {owner_key!r} version {owner_version} does not match "
            f"installed version {owner.owner_version}"
        )
    return owner


def require_capability(owner_key: str, capability: str) -> OwnerDefinition:
    owner = require_owner(owner_key)
    if capability == "erase":
        # ``erase`` 是跨 owner 的统一擦除动词，只对已安装 eraser 的 owner 开放。
        if not owner.erase_available:
            raise OwnerCapabilityUnavailableError(
                f"owner {owner_key!r} eraser is not installed; fail closed"
            )
        return owner
    if capability not in owner.capabilities:
        raise OwnerCapabilityUnavailableError(
            f"owner {owner_key!r} does not declare capability {capability!r}"
        )
    return owner


def assert_snapshot_current(snapshot_digest: str) -> None:
    """校验运行中 operation 的 registry digest 仍匹配当前 registry。"""
    if snapshot_digest != registry_digest():
        raise OwnerRegistryChangedError(
            "purge operation registry digest no longer matches installed registry"
        )
