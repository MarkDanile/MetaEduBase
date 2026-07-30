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


def test_only_workspace_core_eraser_available_in_s2d() -> None:
    registry = _import_registry()
    # S2-D：workspace.core.v1 eraser 已实现（WorkspaceErasureParticipant），
    # erase_available=True；其余 owner 待 S3/S4，erase 必须 fail closed。
    workspace = registry.require_owner("workspace.core.v1")
    assert workspace.erase_available is True
    registry.require_capability("workspace.core.v1", "erase")  # 不抛
    for owner in registry.owner_registry():
        if owner.owner_key == "workspace.core.v1":
            continue
        assert owner.erase_available is False
        with pytest.raises(registry.OwnerCapabilityUnavailableError):
            registry.require_capability(owner.owner_key, "erase")


def test_validate_snapshot_digest_detects_registry_change() -> None:
    registry = _import_registry()
    current = registry.registry_digest()
    registry.assert_snapshot_current(current)
    with pytest.raises(registry.OwnerRegistryChangedError):
        registry.assert_snapshot_current("0" * 64)
