from __future__ import annotations

import pytest

from app.shared.schemas.canonical_json import canonical_digest

EXPECTED_OWNER_KEYS = [
    "execution.core.v1",
    "execution.transport.v1",
    "external.payload.v1",
    "runtime.private.v1",
    "workspace.core.v1",
    "workspace.transport.v1",
]


def _import_registry():
    from app.composition import agent_erasure_registry as registry

    return registry


def test_registry_has_six_fixed_owners() -> None:
    registry = _import_registry()
    owners = registry.owner_registry()
    assert [owner.owner_key for owner in owners] == EXPECTED_OWNER_KEYS


def test_registry_snapshot_is_sorted_and_stable() -> None:
    registry = _import_registry()
    first = registry.registry_snapshot()
    second = registry.registry_snapshot()
    assert first == second
    keys = [entry["owner_key"] for entry in first]
    assert keys == sorted(keys)
    for entry in first:
        assert set(entry) == {"owner_key", "owner_version", "capability_digest"}
        assert entry["owner_key"].endswith(".v1")
        assert entry["owner_version"] == 1


def test_registry_digest_matches_sorted_snapshot() -> None:
    registry = _import_registry()
    snapshot = registry.registry_snapshot()
    expected = canonical_digest({"owners": snapshot, "schema_version": 1})
    assert registry.registry_digest() == expected
    assert len(registry.registry_digest()) == 64


def test_capability_digest_is_deterministic_per_owner() -> None:
    registry = _import_registry()
    digest_a = registry.capability_digest("workspace.core.v1")
    digest_b = registry.capability_digest("workspace.core.v1")
    assert digest_a == digest_b
    assert len(digest_a) == 64
    # 不同 owner 的能力集合不同 -> digest 必须不同。
    assert digest_a != registry.capability_digest("execution.core.v1")


def test_unknown_owner_fails_closed() -> None:
    registry = _import_registry()
    with pytest.raises(registry.UnknownOwnerError):
        registry.require_owner("workspace.unknown.v9")


def test_owner_version_mismatch_fails_closed() -> None:
    registry = _import_registry()
    with pytest.raises(registry.OwnerRegistryChangedError):
        registry.require_owner_version("workspace.core.v1", 2)


def test_missing_capability_fails_closed() -> None:
    registry = _import_registry()
    with pytest.raises(registry.OwnerCapabilityUnavailableError):
        registry.require_capability("runtime.private.v1", "session_destroy")


def test_workspace_and_execution_eraser_available_in_s3d() -> None:
    """S3-D round-1 P1-7 + S4-D-B：S3-D 落 execution.core.v1、S4-D-B 落两个
    transport eraser 后，workspace.core/execution.core/workspace.transport/
    execution.transport 四 owner erase_available=True；其余 owner
    （external/runtime）仍 False。
    """
    registry = _import_registry()
    # S3-D：workspace + execution core eraser 已落地；S4-D-B：两 transport eraser
    # merged-boundary 验收后翻 True。
    for owner_key in (
        "workspace.core.v1",
        "execution.core.v1",
        "workspace.transport.v1",
        "execution.transport.v1",
    ):
        owner = registry.require_owner(owner_key)
        assert owner.erase_available is True, (
            f"{owner_key} eraser not available after S3-D/S4-D-B"
        )
        registry.require_capability(owner_key, "erase")  # 不抛
    # 其余 owner erase 仍 fail closed（external.payload.v1 / runtime.private.v1 待 S4-E）
    for owner in registry.owner_registry():
        if owner.owner_key in (
            "workspace.core.v1",
            "execution.core.v1",
            "workspace.transport.v1",
            "execution.transport.v1",
        ):
            continue
        assert owner.erase_available is False
        with pytest.raises(registry.OwnerCapabilityUnavailableError):
            registry.require_capability(owner.owner_key, "erase")


def test_execution_core_has_actor_identity_capability() -> None:
    """S3-B round-1 P1-2：execution.core.v1 增 actor_identity capability（Spec §7.1）。
    S3-D round-1 P1-7：erase_available 翻 True（与 participant/scan/ACK 同 commit）。
    """
    registry = _import_registry()
    execution = registry.require_owner("execution.core.v1")
    assert "actor_identity" in execution.capabilities
    registry.require_capability("execution.core.v1", "actor_identity")  # 不抛
    # S3-D：erase 已可用，require_capability 不再抛
    assert execution.erase_available is True
    registry.require_capability("execution.core.v1", "erase")  # 不抛


def test_validate_snapshot_digest_detects_registry_change() -> None:
    registry = _import_registry()
    current = registry.registry_digest()
    registry.assert_snapshot_current(current)
    with pytest.raises(registry.OwnerRegistryChangedError):
        registry.assert_snapshot_current("0" * 64)
