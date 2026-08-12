r"""R1-S4-E-C：RuntimeErasureParticipant conformance adapter contract 单元测试。

契约事实源：Plan §R1-S4-E E-5-4 + spec §10.3 + E-2b/E-3a 镜像（runtime adapter
contract，REQ-043 的每个 Runtime Adapter 启用前必须通过 conformance suite）。
纯单元测试（无 DB），镜像 ``test_s4eb1_adapter_contract.py``。

判别点（E-6 镜像）：
- 缺幂等重放且缺 receipt lookup 的 adapter -> ``adapter_satisfies_prerequisite``
  False、``require_adapter_prerequisite`` raise（变异：删任一 supports_* 判定 -> 红）。
- idempotency key 由 runtime_session_ref + adapter_key/adapter_version 派生，
  **不含 lease_epoch/attempt**（跨 takeover 稳定——固定输入下 key 相等；改 ref /
  adapter 输入 -> key 变化）。
- receipt digest 由 adapter evidence 重算（伪造本地 outcome 反例：同 envelope 改
  evidence -> digest 变化；64-hex）。
- E-3a 矩阵：RuntimeDestroySuccess -> erased；NotSent -> blocked/erase_timeout；
  Timeout/Unknown -> unknown/outcome_unknown；Failed -> blocked/adapter_unavailable。
"""
from __future__ import annotations

import uuid

import pytest

from app.composition.runtime_erasure_adapter import (
    RuntimeDestroyFailedError,
    RuntimeDestroyNotSentError,
    RuntimeDestroySuccess,
    RuntimeDestroyTimeoutError,
    RuntimeDestroyUnknown,
    adapter_satisfies_prerequisite,
    classify_destroy_outcome,
    require_adapter_prerequisite,
    runtime_destroy_idempotency_key,
    runtime_destroy_receipt_digest,
    runtime_session_identity_digest,
)

# ---------------------------------------------------------------------------
# fake adapter（支持注入失败分类 + 计数）
# ---------------------------------------------------------------------------


class FakeAdapter:
    def __init__(
        self,
        *,
        adapter_key: str = "fake-pi-sdk",
        adapter_version: int = 1,
        supports_idempotent_replay: bool = True,
        supports_receipt_lookup: bool = False,
    ):
        self.adapter_key = adapter_key
        self.adapter_version = adapter_version
        self.supports_idempotent_replay = supports_idempotent_replay
        self.supports_receipt_lookup = supports_receipt_lookup
        self.calls: list[str] = []

    async def destroy_session(self, **kwargs):
        self.calls.append("destroy")
        return RuntimeDestroyUnknown()

    async def receipt_lookup(self, **kwargs):
        return None


# ---------------------------------------------------------------------------
# E-2b 硬前置：幂等重放 / receipt lookup 至少一个
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("idempotent", "lookup", "expected"),
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, False),
    ],
)
def test_adapter_prerequisite_matrix(idempotent, lookup, expected):
    adapter = FakeAdapter(
        supports_idempotent_replay=idempotent,
        supports_receipt_lookup=lookup,
    )
    assert adapter_satisfies_prerequisite(adapter) is expected


def test_require_adapter_prerequisite_raises_when_neither_supported():
    adapter = FakeAdapter(
        supports_idempotent_replay=False,
        supports_receipt_lookup=False,
    )
    with pytest.raises(ValueError):
        require_adapter_prerequisite(adapter)


def test_require_adapter_prerequisite_passes_with_one():
    require_adapter_prerequisite(
        FakeAdapter(supports_idempotent_replay=True, supports_receipt_lookup=False)
    )


# ---------------------------------------------------------------------------
# E-2b idempotency key：跨 takeover 稳定（不含 lease_epoch/attempt）
# ---------------------------------------------------------------------------


def test_idempotency_key_stable_across_same_input():
    key1 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    key2 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert key1 == key2
    assert len(key1) == 64


def test_idempotency_key_changes_on_adapter_identity():
    key1 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    key2 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="other-sdk",
        adapter_version=1,
    )
    assert key2 != key1


def test_idempotency_key_changes_on_ref_identity():
    key1 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    key2 = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/2",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    assert key2 != key1


def test_idempotency_key_does_not_include_lease_epoch_or_attempt():
    """E-2b 镜像：idempotency key 派生输入只有 ref + adapter 身份——任意
    lease_epoch/attempt 变化不改变 key（跨 takeover 稳定）。"""
    key = runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )
    # 同一 ref 的两次 takeover（epoch/attempt 不同）必须是同一 key——派生函数
    # 不接受 epoch/attempt 参数，天然满足（变异：给派生函数加 epoch 参数 -> 红）。
    assert key == runtime_destroy_idempotency_key(
        runtime_session_ref="pi://session/1",
        adapter_key="fake-pi-sdk",
        adapter_version=1,
    )


# ---------------------------------------------------------------------------
# E-2b receipt digest：由 adapter evidence 重算（禁自造）
# ---------------------------------------------------------------------------


def test_receipt_digest_is_64hex_and_deterministic():
    digest = runtime_destroy_receipt_digest(
        adapter_key="fake-pi-sdk",
        adapter_version=1,
        idempotency_key="k" * 64,
        adapter_receipt_evidence="ev:abc",
        session_digest="s" * 64,
        destroy_outcome="erased",
    )
    assert len(digest) == 64
    assert digest == runtime_destroy_receipt_digest(
        adapter_key="fake-pi-sdk",
        adapter_version=1,
        idempotency_key="k" * 64,
        adapter_receipt_evidence="ev:abc",
        session_digest="s" * 64,
        destroy_outcome="erased",
    )


def test_receipt_digest_changes_on_tampered_evidence():
    """E-6 伪造本地 outcome 反例镜像：同 envelope 改 evidence -> digest 变化。"""
    digest1 = runtime_destroy_receipt_digest(
        adapter_key="fake-pi-sdk",
        adapter_version=1,
        idempotency_key="k" * 64,
        adapter_receipt_evidence="ev:real",
        session_digest="s" * 64,
        destroy_outcome="erased",
    )
    digest2 = runtime_destroy_receipt_digest(
        adapter_key="fake-pi-sdk",
        adapter_version=1,
        idempotency_key="k" * 64,
        adapter_receipt_evidence="ev:forged",
        session_digest="s" * 64,
        destroy_outcome="erased",
    )
    assert digest2 != digest1


def test_session_identity_digest_covers_stable_binding_identity():
    """session_identity_digest 覆盖完整稳定 binding 身份（receipt envelope 输入）。

    确定性 UUID 精确断言：不同 binding_id（其余相同）-> digest 变化。
    """
    binding_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    binding_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
    tenant = uuid.UUID("00000000-0000-0000-0000-000000000001")
    conv = uuid.UUID("00000000-0000-0000-0000-000000000002")
    profile = uuid.UUID("00000000-0000-0000-0000-000000000003")
    da = runtime_session_identity_digest(
        binding_id=binding_a,
        tenant_id=tenant,
        conversation_id=conv,
        runtime_profile_id=profile,
        runtime_session_ref="pi://session/1",
    )
    db = runtime_session_identity_digest(
        binding_id=binding_b,
        tenant_id=tenant,
        conversation_id=conv,
        runtime_profile_id=profile,
        runtime_session_ref="pi://session/1",
    )
    assert len(da) == 64
    assert db != da
    # 全同输入 -> 稳定（deterministic）。
    assert da == runtime_session_identity_digest(
        binding_id=binding_a,
        tenant_id=tenant,
        conversation_id=conv,
        runtime_profile_id=profile,
        runtime_session_ref="pi://session/1",
    )


# ---------------------------------------------------------------------------
# E-3a 矩阵分类（纯映射）
# ---------------------------------------------------------------------------


def test_classify_erased():
    result = classify_destroy_outcome(RuntimeDestroySuccess("ev"))
    assert result.erase_state == "erased"
    assert result.blocked_reason is None


def test_classify_not_sent_is_blocked_erase_timeout():
    result = classify_destroy_outcome(RuntimeDestroyNotSentError("x"))
    assert result.erase_state == "blocked"
    assert result.blocked_reason == "erase_timeout"


def test_classify_timeout_is_unknown_outcome_unknown():
    result = classify_destroy_outcome(RuntimeDestroyTimeoutError("x"))
    assert result.erase_state == "unknown"
    assert result.blocked_reason == "outcome_unknown"


def test_classify_unknown_outcome_is_unknown():
    result = classify_destroy_outcome(RuntimeDestroyUnknown())
    assert result.erase_state == "unknown"
    assert result.blocked_reason == "outcome_unknown"


def test_classify_failed_is_blocked_adapter_unavailable():
    result = classify_destroy_outcome(RuntimeDestroyFailedError("x"))
    assert result.erase_state == "blocked"
    assert result.blocked_reason == "adapter_unavailable"
